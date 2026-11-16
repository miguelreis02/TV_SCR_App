"""
Janela principal da aplicacao de dimensionamento SCR.

A interface NAO calcula nada: recolhe os inputs, monta um
:class:`tvscr.RunScenario` e chama :meth:`~tvscr.RunScenario.run` /
:meth:`~tvscr.RunScenario.run_one`. Todo o modelo esta no pacote ``tvscr``.

As oito seccoes de inputs sao paginas escondidas, mostradas uma de cada vez
pelos separadores da barra lateral, agrupados em tres blocos (dados do
projeto, modelo do catalisador, calculo). Os dados do motor podem vir de um
ficheiro CSV ou ser introduzidos a mao numa tabela.

Por baixo do formulario, separado por um divisor arrastavel, fica o painel de
resultados (:mod:`tvscr_ui.results`): resumo com o volume critico em destaque,
tabela do varrimento, grafico e registo (a consola).

O varrimento corre numa thread separada; a consola e alimentada por uma fila,
para a janela nunca bloquear.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tvscr import (AlphaLoopOptions, EmissionTargets, EngineDataset,
                   KineticParameters, KineticTuning, RunScenario,
                   SolverOptions, SubstrateGeometry, VolumeSweepOptions)

from .docs import DOC_PATH, DocsView
from .paged import (Column, EditableTable, ModeTable, NavLink, PagedForm,
                    RadioGroup)
from .results import ResultsPanel
from .theme import C, F, init_fonts
from .widgets import (CheckField, ChoiceField, FieldError, FloatField,
                      IntField, PathField, Section, TextField, Tooltip,
                      flat_button, ghost_button)

__all__ = ["MainWindow", "launch"]

APP_TITLE = "TECNOVERITAS SCR DIMENSIONING TOOL"
APP_SUBTITLE = "Dimensionamento de reatores SCR-deNOx · "\
               "varrimento em volume com α adaptativo"

LOGO = Path(__file__).with_name("assets") / "tecnoveritas.png"

FUELS = ["HFO", "MDO", "MGO", "LSFO"]
TIERS = ["III", "II", "I"]

RUN_LABEL = "▶  Correr dimensionamento"
SHORTCUTS_HINT = ("F1  documentação   ·   F5  correr   ·   Ctrl+O / Ctrl+S  "
                  "carregar / gravar cenário   ·   Ctrl+PgUp / PgDn  separador")

#: Secção da documentação que explica cada página de inputs (âncora do título
#: em INSTRUCOES.md): é onde o F1 abre a documentação.
PAGE_HELP = {
    "motor": "1--dados-do-motor",
    "geometria": "2--geometria-do-monolito",
    "alvos": "3--alvos-de-emissão",
    "cinetica": "4--cinética-e-transporte",
    "calibracao": "5--calibração-multiplicadores",
    "varrimento": "6--varrimento-em-volume",
    "alpha": "7--loop-de-α",
    "saida": "8--numérico-e-saída",
}
NO_DATASET_INFO = ("Nenhum ficheiro carregado. Escolha o CSV em «Procurar…»: os "
                   "motores que ele trouxer aparecem na lista «Motor».")

SIDEBAR_WIDTH = 232          # largura minima da barra lateral [px]
SIDEBAR_PADDING = 54         # margens verticais entre os blocos da barra lateral
CARD_GAP = 12                # espaco entre cartoes [px]
#: Como o conteudo ocupa a area principal (dimensionamento ou documentacao).
MAIN_PACK = dict(fill="both", expand=True, padx=(14, 12), pady=(12, 8))
# Altura [px] que o ajuste automatico do divisor reserva ao painel de
# resultados: pouca enquanto esta vazio (a prioridade e o formulario), mais
# quando ha um calculo a correr ou resultados para ler.
RESULTS_IDLE_HEIGHT = 170
RESULTS_MIN_HEIGHT = 270
RESULTS_ROW_HEIGHT = 26      # por cada resultado a mais na tabela de comparacao
RESULTS_START_HEIGHT = 330   # altura dos resultados quando a janela abre
FORM_START_HEIGHT = 540      # a pagina mais alta (tabela manual de 4 modos)
SMALL_SCREEN_HEIGHT = 900    # abaixo disto [px de ecra] a janela abre maximizada

#: Colunas da tabela de varrimento de substratos.
SUBSTRATE_COLUMNS = [
    Column("cpsi", "CPSI", "cél/in²", 10,
           tooltip="Densidade celular. passo de célula = 1 in / √(CPSI)."),
    Column("wall_mm", "Parede", "mm", 10,
           tooltip="Espessura TOTAL da parede, em milímetros."),
]

#: Colunas da tabela de introducao manual dos modos do ciclo.
MODE_COLUMNS = [
    Column("load_pct", "Carga", "%", 8,
           tooltip="Carga de travão do modo."),
    Column("weight", "Peso", "%", 8,
           tooltip="Peso do modo no ciclo. Só a razão entre pesos conta."),
    Column("power_kW", "Potência", "kW", 9,
           tooltip="Potência de travão neste modo."),
    Column("T_in_C", "T entrada", "°C", 9,
           tooltip="Temperatura dos gases à entrada do SCR."),
    Column("NO_in_ppm", "NO entrada", "ppm", 10,
           tooltip="NO à entrada do SCR (engine-out). O NO à saída não é um "
                   "input: é o que o modelo calcula."),
    Column("sfoc_g_per_kWh", "SFOC", "g/kWh", 9, required=False,
           tooltip="Consumo específico. Com λ, dá o caudal de escape."),
    Column("lambda_", "λ", "-", 7, required=False,
           tooltip="Excesso de ar. Com o SFOC, dá o caudal de escape."),
    Column("exhaust_mass_flow_kgs", "Caudal esc.", "kg/s", 13, required=False,
           tooltip="Caudal mássico de escape. Se o preencher em TODOS os modos, "
                   "é usado directamente e SFOC + λ passam a ser dispensáveis."),
]


class MainWindow(tk.Tk):
    """Janela unica: separadores a esquerda, inputs em cima, resultados em baixo."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x860")
        self.minsize(1040, 640)
        self.configure(bg=C.BG)

        init_fonts(self)
        self._init_styles()

        self._queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self._running = False
        self._run_started = 0.0
        self._dataset: Optional[EngineDataset] = None
        self._logo_image: Optional[tk.PhotoImage] = None
        self._sash_moved = False          # o utilizador arrastou o divisor?
        self._sidebar_compact = False     # barra lateral apertada (janela baixa)?
        self._sidebar_need = 0            # altura que ela pede sem apertar [px]

        self._build_header()
        self._build_statusbar()
        self._build_body()
        self._bind_shortcuts()

        self.console.write(APP_TITLE, "titulo")
        self.console.write("Escolha a origem dos dados do motor, percorra os "
                           "separadores e prima «Correr dimensionamento».")
        self.results.mark_log_read()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._update_source_state()
        self._fit_to_screen()

    # ------------------------------------------------------------------ #
    #  Aspecto
    # ------------------------------------------------------------------ #
    def _init_styles(self) -> None:
        style = ttk.Style(self)
        with contextlib.suppress(tk.TclError):
            style.theme_use("clam")
        style.configure("TVSCR.TCombobox",
                        fieldbackground=C.FIELD_BG, background=C.FIELD_BG,
                        foreground=C.FIELD_FG, arrowcolor=C.NAVY,
                        bordercolor=C.FIELD_BORDER, lightcolor=C.FIELD_BG,
                        darkcolor=C.FIELD_BG, padding=3)
        style.map("TVSCR.TCombobox",
                  fieldbackground=[("readonly", C.FIELD_BG),
                                   ("disabled", C.FIELD_DISABLED)],
                  selectbackground=[("readonly", C.FIELD_BG)],
                  selectforeground=[("readonly", C.FIELD_FG)])
        self.option_add("*TCombobox*Listbox.background", C.FIELD_BG)
        self.option_add("*TCombobox*Listbox.foreground", C.FIELD_FG)
        self.option_add("*TCombobox*Listbox.selectBackground", C.SELECT_BG)
        self.option_add("*TCombobox*Listbox.selectForeground", C.SELECT_FG)
        self.option_add("*TCombobox*Listbox.font", F.BASE)

        # --- tabelas de resultados ---
        style.configure("TVSCR.Treeview", background=C.SHEET_BG,
                        fieldbackground=C.SHEET_BG, foreground=C.SHEET_FG,
                        font=F.BASE, borderwidth=0, relief="flat",
                        rowheight=F.BASE.metrics("linespace") + 8)
        style.configure("TVSCR.Treeview.Heading", background=C.HEAD_BG,
                        foreground=C.TITLE, font=F.BOLD, relief="flat",
                        padding=(6, 4))
        # So o estado "selected" no mapa: assim as cores das etiquetas (linha do
        # volume critico, linhas inadmissiveis) nao sao tapadas pelo tema.
        style.map("TVSCR.Treeview",
                  background=[("selected", C.SELECT_BG)],
                  foreground=[("selected", C.SELECT_FG)])
        style.map("TVSCR.Treeview.Heading", background=[("active", C.HEAD_BG)])

        # --- barras de rolamento ---
        for orient in ("Vertical", "Horizontal"):
            name = f"TVSCR.{orient}.TScrollbar"
            style.configure(name, background=C.SCROLL,
                            troughcolor=C.SCROLL_TROUGH,
                            bordercolor=C.SCROLL_TROUGH, lightcolor=C.SCROLL,
                            darkcolor=C.SCROLL, arrowcolor=C.NAVY,
                            relief="flat", arrowsize=13)
            style.map(name, background=[("disabled", C.SCROLL_TROUGH),
                                        ("active", C.FIELD_BORDER)])

        style.configure("TVSCR.Horizontal.TProgressbar", troughcolor=C.BG_PANEL,
                        background=C.PROGRESS, bordercolor=C.BORDER,
                        lightcolor=C.PROGRESS, darkcolor=C.PROGRESS)

    def _button(self, parent, text, command, primary: bool = False, **kw):
        if not primary:
            return flat_button(parent, text, command, **kw)
        button = tk.Button(parent, text=text, command=command, relief="flat",
                           font=F.BOLD, cursor="hand2", padx=14, pady=9, bd=0,
                           bg=C.RUN_BG, fg=C.RUN_FG, highlightthickness=0,
                           activebackground=C.RUN_ACTIVE,
                           activeforeground=C.RUN_FG,
                           disabledforeground=C.RUN_DISABLED_FG, **kw)
        button.bind("<Enter>", lambda _e: str(button.cget("state")) != "disabled"
                    and button.configure(bg=C.RUN_ACTIVE), add="+")
        button.bind("<Leave>", lambda _e: button.configure(bg=C.RUN_BG), add="+")
        return button

    def _small_button(self, parent, text, command, **kw):
        return flat_button(parent, text, command, small=True, **kw)

    # ------------------------------------------------------------------ #
    #  Cabecalho, com o logotipo a direita
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=C.BG_HEADER)
        self._header_bar = bar
        bar.pack(fill="x")

        if LOGO.is_file():
            try:
                self._logo_image = tk.PhotoImage(file=str(LOGO))
                tk.Label(bar, image=self._logo_image, bg=C.BG_HEADER,
                         bd=0).pack(side="right", padx=16, pady=8)
            except tk.TclError:                    # imagem ilegivel: segue sem ela
                self._logo_image = None

        text = tk.Frame(bar, bg=C.BG_HEADER)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=APP_TITLE, bg=C.BG_HEADER, fg=C.TITLE,
                 font=F.TITLE, anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(text, text=APP_SUBTITLE, bg=C.BG_HEADER, fg=C.TEXT_DIM,
                 font=F.SUBTITLE, anchor="w").pack(fill="x", padx=16, pady=(2, 12))

        # Filete com o vermelho do logotipo, a separar o titulo do resto.
        self._header_rule = tk.Frame(self, bg=C.RED, height=3)
        self._header_rule.pack(fill="x")

    # ------------------------------------------------------------------ #
    #  Barra de estado (fundo da janela)
    # ------------------------------------------------------------------ #
    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=C.STATUS_BG)
        self._status_bar = bar
        bar.pack(side="bottom", fill="x")
        tk.Frame(self, bg=C.BORDER, height=1).pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=150,
                                        style="TVSCR.Horizontal.TProgressbar")
        self.status = tk.Label(bar, text="Pronto", bg=C.STATUS_BG, fg=C.TEXT,
                               font=F.SMALL, anchor="w")
        self.status.pack(side="left", padx=(16, 10), pady=5)
        tk.Label(bar, text=SHORTCUTS_HINT, bg=C.STATUS_BG, fg=C.NAV_GROUP,
                 font=F.SMALL, anchor="e").pack(side="right", padx=16)

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    # ------------------------------------------------------------------ #
    #  Corpo: barra lateral | (formulario / resultados)
    # ------------------------------------------------------------------ #
    def _build_body(self) -> None:
        body = tk.Frame(self, bg=C.BG)
        body.pack(fill="both", expand=True)

        # Largura medida no tipo de letra, para o botao de correr caber seja
        # qual for a fonte ou a escala do ecra.
        self._sidebar = tk.Frame(
            body, bg=C.NAV_BG,
            width=max(SIDEBAR_WIDTH, F.BOLD.measure(RUN_LABEL) + 46))
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        tk.Frame(body, bg=C.BORDER, width=1).pack(side="left", fill="y")

        # Area principal: o dimensionamento (formulario + resultados) ou, no
        # seu lugar, a documentacao.
        self._main = tk.Frame(body, bg=C.BG)
        self._main.pack(side="left", fill="both", expand=True)
        self.docs: Optional[DocsView] = None       # criada quando for pedida

        # Divisor arrastavel entre o formulario e os resultados.
        paned = tk.PanedWindow(self._main, orient="vertical", bg=C.BG, bd=0,
                               sashwidth=10, sashrelief="flat",
                               opaqueresize=True,
                               sashcursor="sb_v_double_arrow")
        paned.pack(**MAIN_PACK)
        self._paned = paned
        paned.bind("<B1-Motion>", self._on_sash_drag, add="+")
        paned.bind("<Double-Button-1>", self._on_sash_reset, add="+")
        paned.bind("<Configure>", lambda _e: self._sync_form_height(), add="+")

        self._build_pages(paned)
        self._build_results(paned)
        self._build_sidebar_actions()
        self._sidebar.bind("<Configure>", self._fit_sidebar, add="+")

    # ------------------------------------------------------------------ #
    #  Paginas de inputs
    # ------------------------------------------------------------------ #
    def _build_pages(self, paned: tk.PanedWindow) -> None:
        holder = tk.Frame(paned, bg=C.BG)
        paned.add(holder, minsize=150, stretch="never")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        # A coluna da barra de rolamento existe sempre, mesmo com a barra
        # escondida: assim a largura do formulario nao muda quando ela aparece.
        holder.columnconfigure(1, minsize=16)

        canvas = tk.Canvas(holder, bg=C.BG, highlightthickness=0, height=420)
        vbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview,
                             style="TVSCR.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        vbar.grid_remove()
        self._form_canvas = canvas
        self._form_scrollbar = vbar        # so aparece se o conteudo nao couber

        inner = tk.Frame(canvas, bg=C.BG)
        self._form_inner = inner
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", self._sync_form_height)
        canvas.bind("<Configure>",
                    lambda e: (canvas.itemconfigure(window, width=e.width),
                               self._update_form_scrollbar()))
        # A roda do rato so mexe o formulario se o ponteiro estiver SOBRE ele.
        # Sem esta verificacao, rolar na consola mexia tambem o formulario.
        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        # No X11 a roda chega como botoes 4 e 5.
        self.bind_all("<Button-4>", lambda e: self._on_wheel_button(e, 120),
                      add="+")
        self.bind_all("<Button-5>", lambda e: self._on_wheel_button(e, -120),
                      add="+")

        self.form = PagedForm(inner, nav_parent=self._sidebar)
        self.form.tabs.pack(fill="x", pady=(12, 0))
        self.form.pack(fill="both", expand=True)

        self.form.add_group("DADOS DO PROJETO")
        self._build_engine_page(self.form.add_page(
            "motor", "1 · Dados do motor",
            "Ficheiro CSV ou introdução manual dos modos do ciclo"))
        self._build_geometry_page(self.form.add_page(
            "geometria", "2 · Geometria", "Substrato e monolito a instalar"))
        self._build_targets_page(self.form.add_page(
            "alvos", "3 · Alvos", "Limites de NOx e de NH₃ slip"))
        self.form.add_group("MODELO DO CATALISADOR")
        self._build_kinetics_page(self.form.add_page(
            "cinetica", "4 · Cinética",
            "Parâmetros do modelo de Tronconi, envelhecimento e fouling"))
        self._build_tuning_page(self.form.add_page(
            "calibracao", "5 · Calibração", "Multiplicadores sobre a cinética"))
        self.form.add_group("CÁLCULO")
        self._build_sweep_page(self.form.add_page(
            "varrimento", "6 · Varrimento", "Malha de volumes e refinamento"))
        self._build_alpha_page(self.form.add_page(
            "alpha", "7 · Loop de α", "Procura do doseamento admissível"))
        self._build_output_page(self.form.add_page(
            "saida", "8 · Numérico e saída", "Malha do solver e ficheiros"))
        self.form.on_change(self._on_page_change)

    def _on_page_change(self, _key: str) -> None:
        """Escolher um separador mostra a pagina no topo -- e o dimensionamento,
        se a documentacao estiver a ocupar o lugar dele."""
        self._form_canvas.yview_moveto(0)
        self.show_work()

    def _sync_form_height(self, _event=None) -> None:
        """Ajusta o divisor ao conteudo do formulario, ate um tecto razoavel.

        Assim nao sobra area verde vazia por baixo da pagina, e a barra de
        rolamento so aparece quando o conteudo nao cabe mesmo (uma tabela
        manual com muitas linhas, por exemplo). Deixa de o fazer assim que o
        utilizador arrasta o divisor: a partir dai manda ele.
        """
        canvas = self._form_canvas
        canvas.configure(scrollregion=canvas.bbox("all"))
        if not self._sash_moved:
            self._place_sash()
        self._update_form_scrollbar()

    def _place_sash(self) -> None:
        """Poe o divisor logo abaixo do formulario, deixando espaco aos resultados."""
        total = self._paned.winfo_height()
        if total <= 1:                              # janela ainda por desenhar
            return
        # A pagina MAIS ALTA, e nao a que esta a vista: o divisor nao salta
        # ao trocar de separador.
        needed = self.form.tallest_height() + 2
        if self._running or self.results.has_results:
            # Com varios resultados, mais altura: uma linha da tabela de
            # comparacao por cada um (ate cinco).
            extra = min(max(self.results.n_results - 1, 0), 4)
            reserve = RESULTS_MIN_HEIGHT + extra * RESULTS_ROW_HEIGHT
        else:
            reserve = RESULTS_IDLE_HEIGHT
        limit = max(int(total * 0.45), total - reserve)
        with contextlib.suppress(tk.TclError):
            self._paned.sash_place(0, 0, max(150, min(needed, limit)))

    def _on_sash_drag(self, _event=None) -> None:
        self._sash_moved = True

    def _on_sash_reset(self, _event=None) -> None:
        """Duplo clique no divisor: volta ao ajuste automatico."""
        self._sash_moved = False
        self._sync_form_height()

    def _form_overflows(self) -> bool:
        return (self._form_inner.winfo_reqheight()
                > self._form_canvas.winfo_height() + 1)

    def _update_form_scrollbar(self) -> None:
        if self._form_overflows():
            self._form_scrollbar.grid()
        else:
            self._form_scrollbar.grid_remove()
            self._form_canvas.yview_moveto(0)

    def _scroll_into_view(self, widget) -> None:
        """Rola o formulario o necessario para ``widget`` ficar a vista."""
        canvas, inner = self._form_canvas, self._form_inner
        if not self._form_overflows():
            return
        top = widget.winfo_rooty() - canvas.winfo_rooty()
        if 0 <= top and top + widget.winfo_height() <= canvas.winfo_height():
            return                                  # ja esta a vista
        offset = widget.winfo_rooty() - inner.winfo_rooty()
        canvas.yview_moveto(max(0.0, (offset - 60) / max(1, inner.winfo_height())))

    def _is_inside_form(self, widget) -> bool:
        """``True`` se ``widget`` pertencer a arvore do formulario."""
        node = widget
        while node is not None:
            if node is self._form_canvas:
                return True
            node = getattr(node, "master", None)
        return False

    def _on_mousewheel(self, event):
        """Rola o formulario apenas quando o ponteiro esta dentro dele.

        A ligacao e feita com ``bind_all``, logo chega aqui a roda de toda a
        janela. Sem esta verificacao, rolar na consola rolava tambem o
        formulario -- a consola ja tratou o evento na sua ligacao de classe.
        """
        if not self._is_inside_form(self.winfo_containing(event.x_root, event.y_root)):
            return None                            # deixa o widget tratar
        if self._form_overflows():
            self._form_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _on_wheel_button(self, event, delta: int):
        event.delta = delta
        return self._on_mousewheel(event)

    @staticmethod
    def _columns(page: tk.Frame, count: int, weights=None,
                 stack_below: int = 0) -> List[tk.Frame]:
        """Divide uma pagina em colunas.

        Sem ``weights``, as colunas tem todas a mesma largura. Com
        ``stack_below``, passam a ficar umas por baixo das outras quando a
        pagina e mais estreita do que esse valor [px], em vez de se cortarem.
        Cada cartao deve ser posto na sua coluna com ``_fill``, para os cartoes
        da mesma linha ficarem com a mesma altura.
        """
        frames = [tk.Frame(page, bg=C.BG) for _ in range(count)]
        for i in range(count):
            if weights:
                page.columnconfigure(i, weight=weights[i])
            else:
                page.columnconfigure(i, weight=1, uniform="colunas")

        state = {"stacked": None}

        def arrange(stacked: bool) -> None:
            if state["stacked"] == stacked:
                return
            state["stacked"] = stacked
            for i, frame in enumerate(frames):
                if stacked:
                    frame.grid(row=i, column=0, columnspan=count, sticky="new",
                               padx=0, pady=(0 if i == 0 else CARD_GAP, 0))
                else:
                    frame.grid(row=0, column=i, columnspan=1, sticky="nsew",
                               padx=(0 if i == 0 else CARD_GAP, 0), pady=0)

        arrange(False)
        if stack_below:
            page.bind("<Configure>",
                      lambda e: e.widget is page and arrange(e.width < stack_below),
                      add="+")
        return frames

    @staticmethod
    def _fill(card: Section) -> Section:
        """Poe o cartao a ocupar a coluna toda (largura e altura)."""
        card.pack(fill="both", expand=True)
        return card

    # -- 1. dados do motor ----------------------------------------------- #
    def _build_engine_page(self, page: tk.Frame) -> None:
        # Grelha propria (e nao _columns): a esquerda, a origem dos dados e o
        # cartao que dela depende; a direita, a toda a altura, o que e comum as
        # duas origens; por baixo, a toda a largura, a tabela dos modos.
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        # --- origem dos dados ---
        origin = Section(page, "")
        origin.grid(row=0, column=0, sticky="ew")
        chooser = tk.Frame(origin.body, bg=C.BG_PANEL)
        chooser.grid(row=origin.next_row(), column=0, columnspan=5, sticky="w")
        tk.Label(chooser, text="ORIGEM DOS DADOS", bg=C.BG_PANEL, fg=C.TITLE,
                 font=F.BOLD).pack(side="left", padx=(0, 18))
        self.source = tk.StringVar(value="csv")
        self.source_radio = RadioGroup(
            chooser, self.source,
            [("csv", "Ficheiro CSV"), ("manual", "Introdução manual")],
            command=self._update_source_state)
        self.source_radio.pack(side="left")
        self.source.trace_add("write", lambda *_: self._update_source_state())

        # --- area que muda conforme a origem ---
        area = tk.Frame(page, bg=C.BG)
        area.grid(row=1, column=0, sticky="nsew", pady=(CARD_GAP, 0))
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)

        self._csv_frame = tk.Frame(area, bg=C.BG)
        self._csv_frame.grid(row=0, column=0, sticky="nsew")
        self._manual_frame = tk.Frame(area, bg=C.BG)
        self._manual_frame.grid(row=0, column=0, sticky="nsew")

        self._build_csv_source(self._csv_frame)
        self._build_manual_source(self._manual_frame)

        # --- comum as duas origens ---
        common = Section(page, "MOTOR E COMBUSTÍVEL", note_wrap=260,
                         note="Aplica-se seja qual for a origem dos dados.")
        common.grid(row=0, column=1, rowspan=2, sticky="nsew",
                    padx=(CARD_GAP, 0))
        self.f_fuel = ChoiceField(common, "Combustível", FUELS, "HFO",
                                  tooltip="Define o AFR estequiométrico usado para "
                                          "converter SFOC + λ em caudal de escape.")
        self.f_pressure = FloatField(common, "Pressão", 101325.0, "Pa", minimum=1.0)
        self.f_tier = ChoiceField(common, "Limite MARPOL", TIERS, "III",
                                  tooltip="O limite em g/kWh sai da rotação nominal "
                                          "do motor.")
        self.f_power_law = CheckField(
            common, "Lei de potência em toda a gama", False,
            tooltip="Aplica 9·n^-0.2 sem os patamares de n < 130 e n ≥ 2000 rpm, "
                    "como o MATLAB. Coincide com a regra completa entre 130 e "
                    "2000 rpm.")

        # --- tabela dos modos (so em introducao manual), a toda a largura ---
        self._modes_card = Section(
            page, "MODOS DO CICLO DE ENSAIO", note_wrap=760,
            note="Um modo por linha. Linhas em branco são ignoradas. Para o "
                 "caudal de escape, preencha SFOC + λ ou, em alternativa, a "
                 "coluna «Caudal esc.» em todos os modos.")
        self._modes_card.grid(row=2, column=0, columnspan=2, sticky="ew",
                              pady=(CARD_GAP, 0))
        self._build_mode_table(self._modes_card)

    def _build_csv_source(self, parent: tk.Frame) -> None:
        s = Section(parent, "FICHEIRO DE INPUTS", note_wrap=520,
                    note="Uma linha por modo do ciclo e por motor. As condições de "
                         "operação — carga, peso, potência, temperatura, NO à "
                         "entrada, SFOC e λ — vêm todas daqui.")
        s.pack(fill="both", expand=True)
        self.f_dataset = PathField(
            s, "Ficheiro (CSV)", mode="open",
            on_pick=lambda _p: self._load_dataset(),
            tooltip="Separador ';' e vírgula decimal, por omissão.")
        self.f_engine = ChoiceField(
            s, "Motor", [""], tooltip="Etiqueta do motor na coluna 'Engine'.")
        self.f_engine.on_change(self._on_engine_change)
        self.f_all_engines = CheckField(
            s, "Correr todos os motores do ficheiro", False,
            tooltip="Corre o varrimento para cada motor e produz a tabela-resumo "
                    "dos volumes críticos.")
        self.f_all_engines.var.trace_add("write",
                                         lambda *_: self._update_engine_state())

        # O que o ficheiro / motor escolhido traz, logo por baixo da escolha.
        info = s.add_block()
        self.engine_info = tk.Label(info, text=NO_DATASET_INFO, bg=C.BG_PANEL,
                                    fg=C.TEXT_DIM, font=F.SMALL, anchor="w",
                                    justify="left", wraplength=560)
        self.engine_info.pack(fill="x")
        info.bind("<Configure>", lambda e: self.engine_info.configure(
            wraplength=max(200, e.width - 4)))

    def _build_manual_source(self, parent: tk.Frame) -> None:
        s = Section(parent, "IDENTIFICAÇÃO DO MOTOR")
        s.pack(fill="both", expand=True)
        self.f_manual_name = TextField(s, "Nome do motor", "DG1", width=16)
        self.f_manual_rpm = FloatField(s, "Rotação nominal", 513.0, "rpm",
                                       minimum=1.0,
                                       tooltip="Define o limite MARPOL em g/kWh.")
        self.f_manual_rated = FloatField(s, "Potência nominal", None, "kW",
                                         minimum=0.0, allow_empty=True,
                                         tooltip="Opcional: só entra no relatório.")

    def _build_mode_table(self, card: Section) -> None:
        block = card.add_block()
        self.mode_table = ModeTable(block, MODE_COLUMNS, initial_rows=4)
        self.mode_table.pack(anchor="w")

        buttons = tk.Frame(block, bg=C.BG_PANEL)
        buttons.pack(fill="x", pady=(9, 0))
        self._small_button(buttons, "+ Adicionar modo",
                           self.mode_table.add_row).pack(side="left")
        self._small_button(buttons, "− Remover último",
                           self.mode_table.remove_last_row).pack(side="left", padx=6)
        self._small_button(buttons, "Limpar tabela",
                           lambda: self.mode_table.clear()).pack(side="left")
        flow_btn = self._small_button(buttons, "Calcular caudal de escape",
                                      self._fill_exhaust_flow)
        flow_btn.pack(side="left", padx=6)
        Tooltip(flow_btn, "Preenche a coluna «Caudal esc.» a partir do SFOC, do λ "
                          "e do combustível escolhido:\n"
                          "m_fuel = SFOC·P/3.6e6 ;  m_exh = m_fuel·(1 + AFR_st·λ)")
        copy_btn = self._small_button(buttons, "Copiar do ficheiro CSV",
                                      self._copy_from_dataset)
        copy_btn.pack(side="left")
        Tooltip(copy_btn, "Preenche a tabela com o motor escolhido no ficheiro "
                          "CSV, para depois o editar à mão.")

    def _fill_exhaust_flow(self) -> None:
        """Preenche a coluna do caudal de escape a partir de SFOC, λ e combustível.

        É o cálculo de ``get_mass_dot_v3.m``, agora em
        :func:`tvscr.exhaust_flow`. Serve para o utilizador ver os caudais que
        o modelo vai usar, em vez de os ter de aceitar às cegas.
        """
        from tvscr import exhaust_flow

        try:
            rows = self.mode_table.rows()
        except FieldError as exc:
            self._reveal_error(exc)
            messagebox.showerror("Input inválido", str(exc))
            return

        em_falta = [i for i, r in enumerate(rows, start=1)
                    if r.get("sfoc_g_per_kWh") is None or r.get("lambda_") is None]
        if em_falta:
            messagebox.showinfo(
                "Faltam dados",
                "Para calcular o caudal de escape são precisos o SFOC e o λ em "
                f"todos os modos.\nEm falta no(s) modo(s): "
                f"{', '.join(str(i) for i in em_falta)}.")
            return

        flow = exhaust_flow([r["sfoc_g_per_kWh"] for r in rows],
                            [r["power_kW"] for r in rows],
                            [r["lambda_"] for r in rows],
                            fuel=self.f_fuel.value(),
                            load_pct=[r["load_pct"] for r in rows])

        for row, mdot in zip(rows, flow.exhaust_mass_flow_kgs):
            row["exhaust_mass_flow_kgs"] = float(mdot)
        self.mode_table.set_rows(rows)

        self.console.write(f"Caudal de escape calculado ({flow.fuel.name}, "
                           f"AFR estequiométrico = {flow.afr_stoich:.3f}):", "ok")
        for line in flow.describe().splitlines()[1:]:
            self.console.write(line)
        # Os caudais de combustivel, ar e escape ficam no registo: mostra-lo.
        self.results.select("registo")
        self._set_status("Caudal de escape calculado: detalhe por modo no registo.")

    # -- 2. geometria ----------------------------------------------------- #
    def _build_geometry_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "SUBSTRATO", note_wrap=420,
                    note="Escolha de projeto: não vem do ficheiro de inputs. "
                         "Pode comparar vários pares num só cálculo.")
        self._fill(s)
        self.f_sweep_substrate = CheckField(
            s, "Comparar vários pares CPSI / parede", False,
            tooltip="Corre o varrimento em volume uma vez por par e põe os "
                    "volumes críticos lado a lado. O tempo de cálculo é "
                    "multiplicado pelo número de pares.")
        self.f_sweep_substrate.var.trace_add(
            "write", lambda *_: self._update_substrate_state())

        area = s.add_block()
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self._single_substrate = tk.Frame(area, bg=C.BG_PANEL)
        self._single_substrate.grid(row=0, column=0, sticky="nsew")
        self._multi_substrate = tk.Frame(area, bg=C.BG_PANEL)
        self._multi_substrate.grid(row=0, column=0, sticky="nsew")

        one = Section(self._single_substrate, "", flat=True)
        one.pack(fill="x")
        self.f_cpsi = FloatField(one, "Densidade celular", 46.0, "cél/in²",
                                 minimum=0.1,
                                 tooltip="passo de célula = 1 in / √(CPSI)")
        self.f_wall = FloatField(one, "Espessura de parede", 0.43e-3, "m",
                                 minimum=0.0,
                                 tooltip="Espessura TOTAL. A semi-espessura é a "
                                         "dimensão característica da difusão "
                                         "intraporo.")

        self.substrate_table = EditableTable(
            self._multi_substrate, SUBSTRATE_COLUMNS, initial_rows=3,
            row_noun="Substrato")
        self.substrate_table.pack(anchor="w")
        self.substrate_table.set_rows([
            {"cpsi": 46, "wall_mm": 0.43},
            {"cpsi": 64, "wall_mm": 0.35},
            {"cpsi": 100, "wall_mm": 0.25},
        ])
        buttons = tk.Frame(self._multi_substrate, bg=C.BG_PANEL)
        buttons.pack(fill="x", pady=(9, 0))
        self._small_button(buttons, "+ Adicionar par",
                           self.substrate_table.add_row).pack(side="left")
        self._small_button(buttons, "− Remover último",
                           self.substrate_table.remove_last_row).pack(side="left",
                                                                      padx=6)
        self._small_button(buttons, "Limpar tabela",
                           lambda: self.substrate_table.clear(3)).pack(side="left")

        g = Section(right, "MONOLITO", note_wrap=400,
                    note="O comprimento fica FIXO durante o varrimento e a área "
                         "frontal sai do volume: A = V / L. É o volume que o "
                         "cálculo procura, não a área.")
        self._fill(g)
        self.f_length = FloatField(g, "Comprimento L", 1.2, "m", minimum=1e-6,
                                   tooltip="Comprimento do monolito a instalar. "
                                           "Fica fixo; o varrimento faz variar a "
                                           "área frontal (A = V / L).")
        self._update_substrate_state()

    def _update_substrate_state(self) -> None:
        """Mostra a tabela de pares ou os dois campos únicos."""
        if self.f_sweep_substrate.value():
            self._multi_substrate.tkraise()
        else:
            self._single_substrate.tkraise()

    # -- 3. alvos --------------------------------------------------------- #
    def _build_targets_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "NOx", note_wrap=380,
                    note="Frações do limite MARPOL calculado para a rotação do "
                         "motor. O ciclo ponderado é mais apertado que cada modo.")
        self._fill(s)
        self.f_cyc_frac = FloatField(s, "NOx do ciclo (fração)", 0.60, "-",
                                     minimum=0.0, maximum=1.0)
        self.f_mode_frac = FloatField(s, "NOx por modo (fração)", 0.80, "-",
                                      minimum=0.0, maximum=1.0)

        t = Section(right, "NH₃ SLIP", note_wrap=380,
                    note="Amoníaco não reagido à saída do reator.")
        self._fill(t)
        self.f_cyc_slip = FloatField(t, "Slip do ciclo", 10.0, "ppm", minimum=0.0)
        self.f_mode_slip = FloatField(t, "Slip por modo", 20.0, "ppm", minimum=0.0)

    # -- 4. cinetica ------------------------------------------------------ #
    def _build_kinetics_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "REAÇÃO", note_wrap=380,
                    note="Valores por omissão: Tabela 2 de Tronconi 1998 "
                         "(catalisador 1). Energias de ativação em cal/mol.")
        self._fill(s)
        self.f_k0ads = FloatField(s, "k0 adsorção NH₃", 8.5e6, "-", minimum=0.0)
        self.f_Eads = FloatField(s, "E adsorção NH₃", 9.0e3, "cal/mol")
        self.f_k0NO = FloatField(s, "k0 redução NO", 2.5e10, "-", minimum=0.0)
        self.f_ENO = FloatField(s, "E redução NO", 18.6e3, "cal/mol")
        self.f_k0d = FloatField(s, "k0 dessorção NH₃", 8.0e8, "-", minimum=0.0)
        self.f_E0d = FloatField(s, "E dessorção (θ=0)", 2.6e4, "cal/mol")
        self.f_beta = FloatField(s, "β (Temkin)", 0.32, "-")

        t = Section(right, "TRANSPORTE E ESTADO DO CATALISADOR",
                    note_wrap=380,
                    note="Envelhecimento e fouling são o que separa um reator que "
                         "cumpre no primeiro dia de um que cumpre ao fim da vida.")
        self._fill(t)
        self.f_KK0 = FloatField(t, "Envelhecimento KK0", 0.80, "-", minimum=1e-6,
                                tooltip="k0NO efetivo = k0NO · KK0². "
                                        "1 = catalisador novo; 0.8 = fim de vida.")
        self.f_fouling = FloatField(t, "Fouling", 0.15, "-", minimum=0.0,
                                    maximum=0.99,
                                    tooltip="Fracção da área frontal perdida por "
                                            "obstrução dos canais: a área efetiva "
                                            "passa a A·(1−fouling). Dimensionar com "
                                            "fouling = 0 dá um reator que deixa de "
                                            "cumprir mal o catalisador suja.")
        self.f_Deff = FloatField(t, "Difusividade efetiva", 1e-6, "m²/s", minimum=0.0)
        self.f_Dmol = FloatField(t, "Difusividade molecular", 8e-5, "m²/s",
                                 minimum=0.0)
        self.f_Mbar = FloatField(t, "Massa molar do gás", 0.02896, "kg/mol",
                                 minimum=1e-6)
        self.f_f = FloatField(t, "f (fronteira ativa)", 0.01, "-", minimum=0.0,
                              tooltip="Critério NUMÉRICO de x*, não um parâmetro "
                                      "cinético.")

    # -- 5. calibracao ---------------------------------------------------- #
    def _build_tuning_page(self, page: tk.Frame) -> None:
        left, _right = self._columns(page, 2)
        s = Section(left, "MULTIPLICADORES DE CALIBRAÇÃO", note_wrap=380,
                    note="Aplicados por cima da cinética já calculada, para ajustar "
                         "o modelo a um catalisador concreto sem mexer nos "
                         "parâmetros físicos. Tudo a 1 reproduz a referência.")
        self._fill(s)
        self.f_t_kNO = FloatField(s, "× kNO", 1.0, "-", minimum=0.0)
        self.f_t_kads = FloatField(s, "× kads", 1.0, "-", minimum=0.0)
        self.f_t_Deff = FloatField(s, "× Deff", 1.0, "-", minimum=0.0)
        self.f_t_k0d = FloatField(s, "× k0d", 1.0, "-", minimum=0.0)

    # -- 6. varrimento ---------------------------------------------------- #
    def _build_sweep_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "MALHA DE VOLUMES", note_wrap=380,
                    note="Desce em volume até ao primeiro volume inadmissível — "
                         "esse é o volume crítico. L fica fixo e a área varia "
                         "(A = V / L).")
        self._fill(s)
        self.f_v_max = FloatField(s, "Volume máximo", 3.50, "m³", minimum=1e-6,
                                  tooltip="Maior volume a considerar; o varrimento "
                                          "começa aqui e desce. Se o maior volume "
                                          "já não cumprir os alvos, não há solução "
                                          "no intervalo.")
        self.f_v_step = FloatField(s, "Decremento de volume", 0.20, "m³",
                                   minimum=1e-6)
        self.f_v_min = FloatField(s, "Volume mínimo", 0.20, "m³", minimum=1e-6)

        t = Section(right, "REFINAMENTO", note_wrap=380,
                    note="Bisseção em V entre o último volume admissível e o "
                         "primeiro que falhou, para afinar o volume crítico para "
                         "além da resolução do passo.")
        self._fill(t)
        self.f_refine = CheckField(t, "Refinar por bisseção em V", True)
        self.f_refine_tol = FloatField(t, "Tolerância do refinamento", 0.02, "m³",
                                       minimum=1e-9)

    # -- 7. loop de alpha ------------------------------------------------- #
    def _build_alpha_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "PROCURA DE α", note_wrap=380,
                    note="Procura, por modo, o α que cumpre NO_out e slip nos dois "
                         "níveis. Bracketing + bisseção geométrica contra "
                         "oscilação.")
        self._fill(s)
        self.f_alpha0 = FloatField(s, "α de arranque", 0.80, "-", minimum=0.0)
        self.f_dalpha = FloatField(s, "Passo de α", 0.02, "-", minimum=1e-9)
        self.f_alpha_min = FloatField(s, "α mínimo", 0.30, "-", minimum=0.0)
        self.f_alpha_max = FloatField(s, "α máximo", 1.20, "-", minimum=0.0)

        t = Section(right, "CONVERGÊNCIA", note_wrap=380)
        self._fill(t)
        self.f_max_iter = IntField(t, "Máximo de iterações", 200, "-", minimum=1)
        self.f_bracket_tol = FloatField(t, "Tolerância de bracketing", 1e-4, "-",
                                        minimum=0.0)
        self.f_minimize = CheckField(
            t, "Minimizar α após cumprir os alvos", False,
            tooltip="Devolve o α mínimo admissível (mínimo de ureia e de slip). "
                    "Não altera o volume crítico, só o ponto de operação "
                    "reportado.")

    # -- 8. numerico e saida ---------------------------------------------- #
    def _build_output_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "SOLVER", note_wrap=380,
                    note="Malha axial do modelo 1-D. 120 é o valor validado; "
                         "alterar muda o resultado ao nível da discretização.")
        self._fill(s)
        self.f_nodes = IntField(s, "Nós axiais", 120, "-", minimum=10)

        t = Section(right, "FICHEIROS", note_wrap=380,
                    note="Sem pasta indicada, nada é gravado em disco — os "
                         "resultados ficam só no painel de resultados.")
        self._fill(t)
        self.f_outdir = PathField(t, "Pasta de resultados", mode="dir")
        self.f_save_csv = CheckField(t, "Gravar CSV", True)
        self.f_save_png = CheckField(t, "Gravar figuras (PNG)", True)

    # ------------------------------------------------------------------ #
    #  Resultados e accoes
    # ------------------------------------------------------------------ #
    def _build_results(self, paned: tk.PanedWindow) -> None:
        self.results = ResultsPanel(paned, on_save_log=self._on_save_log)
        paned.add(self.results, minsize=170, stretch="always")
        self.console = self.results.console

    def _build_sidebar_actions(self) -> None:
        """Accoes sobre o cenario e, sempre visivel, o botao de correr."""
        scenario = tk.Frame(self._sidebar, bg=C.NAV_BG)
        scenario.pack(fill="x", pady=(14, 0))
        self._side_boxes = [scenario]
        self._side_buttons: List[tk.Button] = []
        tk.Label(scenario, text="CENÁRIO", bg=C.NAV_BG, fg=C.NAV_GROUP,
                 font=F.SMALL_BOLD, anchor="w", padx=16).pack(fill="x",
                                                              pady=(0, 3))
        for text, command, tip in (
                ("Carregar cenário…", self._on_load_scenario,
                 "Repõe o formulário a partir de um .json gravado (Ctrl+O)."),
                ("Gravar cenário…", self._on_save_scenario,
                 "Escreve um .json com todos os inputs do formulário (Ctrl+S)."),
                ("Repor omissões", self._on_reset,
                 "Volta aos valores por omissão, sem perder o ficheiro nem o "
                 "motor escolhidos.")):
            button = ghost_button(scenario, text, command, anchor="w")
            button.configure(bg=C.NAV_BG, padx=16)
            button.bind("<Leave>", lambda _e, b=button: b.configure(bg=C.NAV_BG),
                        add="+")
            button.pack(fill="x")
            self._side_buttons.append(button)
            Tooltip(button, tip, delay_ms=700)

        help_box = tk.Frame(self._sidebar, bg=C.NAV_BG)
        help_box.pack(fill="x", pady=(14, 0))
        self._side_boxes.append(help_box)
        tk.Label(help_box, text="AJUDA", bg=C.NAV_BG, fg=C.NAV_GROUP,
                 font=F.SMALL_BOLD, anchor="w", padx=16).pack(fill="x",
                                                              pady=(0, 3))
        self.docs_link = NavLink(
            help_box, "Documentação", self.show_docs,
            tooltip="Documentação do programa: utilização, parâmetros, modelo, "
                    "ficheiros de entrada e de saída (F1 abre-a na secção do "
                    "separador em que está).")
        self.docs_link.pack(fill="x")

        run = tk.Frame(self._sidebar, bg=C.NAV_BG)
        self._actions_bar = run
        run.pack(side="bottom", fill="x", padx=14, pady=(0, 14))
        self.btn_run = self._button(run, RUN_LABEL, self._on_run, primary=True)
        self.btn_run.pack(fill="x")
        Tooltip(self.btn_run, "Corre o varrimento em volume com os inputs de "
                              "todos os separadores (F5).", delay_ms=700)

    def _fit_sidebar(self, _event=None) -> None:
        """Aperta a barra lateral quando a janela e baixa de mais para ela.

        Num portatil de 768 px de altura os separadores, as accoes do cenario,
        a documentacao e o botao de correr nao cabiam todos: o botao ficava por
        cima da ultima entrada. Com o espaco entre entradas reduzido, cabem.
        """
        height = self._sidebar.winfo_height()
        if height <= 1:
            return
        if not self._sidebar_compact:
            needed = SIDEBAR_PADDING + sum(
                child.winfo_reqheight() for child in self._sidebar.winfo_children())
            if needed <= height:
                return
            self._sidebar_need = needed
            compact = True
        elif height >= self._sidebar_need + 8:
            compact = False
        else:
            return
        self._sidebar_compact = compact
        self.form.set_compact(compact)
        self.docs_link.set_compact(compact)
        for button in self._side_buttons:
            button.configure(pady=1 if compact else 5)
        for box in self._side_boxes:
            box.pack_configure(pady=(7 if compact else 14, 0))

    def _bind_shortcuts(self) -> None:
        def call(action):
            def handler(_event=None):
                action()
                return "break"
            return handler

        self.bind("<F1>", call(self._on_help_key))
        self.bind("<Escape>", lambda _e: self.show_work())
        for key in ("f", "F"):
            self.bind(f"<Control-{key}>", call(self._on_find_key))
        self.bind("<F5>", call(self._on_run))
        self.bind("<Control-Return>", call(self._on_run))
        for key in ("o", "O"):                       # com e sem Caps Lock
            self.bind(f"<Control-{key}>", call(self._on_load_scenario))
        for key in ("s", "S"):
            self.bind(f"<Control-{key}>", call(self._on_save_scenario))
        self.bind("<Control-Next>", call(self.form.select_next))
        self.bind("<Control-Prior>", call(self.form.select_previous))

    # ------------------------------------------------------------------ #
    #  Documentacao
    # ------------------------------------------------------------------ #
    @property
    def docs_visible(self) -> bool:
        return self.docs is not None and bool(self.docs.winfo_manager())

    def show_docs(self, anchor: Optional[str] = None) -> None:
        """Mostra a documentacao no lugar do dimensionamento.

        ``anchor`` e a ancora do titulo a por no topo; sem ela, a documentacao
        abre onde tinha ficado. O calculo, se estiver a correr, continua.
        """
        if self.docs is None:
            self.docs = DocsView(self._main, DOC_PATH, on_close=self.show_work)
        elif anchor and self.docs.path != self.docs.home:
            self.docs.load(self.docs.home)
        elif not self.docs_visible:
            self.docs.reload_if_changed()      # o ficheiro pode ter sido editado
        if not self.docs_visible:
            self._paned.pack_forget()
            self.docs.pack(**MAIN_PACK)
            self.form.set_highlight(False)
            self.docs_link.set_active(True)
        if anchor:
            self.update_idletasks()
            self.docs.goto(anchor)

    def show_work(self) -> None:
        """Volta ao dimensionamento (formulario e resultados)."""
        if not self.docs_visible:
            return
        self.docs.pack_forget()
        self._paned.pack(**MAIN_PACK)
        self.form.set_highlight(True)
        self.docs_link.set_active(False)

    def _on_help_key(self) -> None:
        """F1: a documentacao, na seccao do separador em que se esta."""
        self.show_docs(PAGE_HELP.get(self.form.current))

    def _on_find_key(self) -> None:
        """Ctrl+F: procura na documentacao (abre-a, se for preciso)."""
        self.show_docs()
        self.docs.focus_search()

    def _fit_to_screen(self) -> None:
        """Ajusta a janela ao conteudo, sem passar dos limites do ecra."""
        self.update_idletasks()
        chrome = 20 + 14                 # margens verticais do divisor + folga
        needed = (self._header_bar.winfo_reqheight()
                  + self._status_bar.winfo_reqheight()
                  + max(self.form.tallest_height(), FORM_START_HEIGHT)
                  + RESULTS_START_HEIGHT + chrome)
        height = min(needed, int(self.winfo_screenheight() * 0.90))
        width = min(1280, int(self.winfo_screenwidth() * 0.95))
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        if self.winfo_screenheight() < SMALL_SCREEN_HEIGHT:
            # Ecra baixo (portatil): a janela abre maximizada, para o formulario
            # e os resultados caberem com o minimo de rolamento.
            with contextlib.suppress(tk.TclError):
                self.state("zoomed")
        self.update_idletasks()
        self._sync_form_height()

    # ------------------------------------------------------------------ #
    #  Origem dos dados
    # ------------------------------------------------------------------ #
    def _update_source_state(self) -> None:
        """Mostra a area da origem escolhida e esconde a outra.

        Esconde mesmo (``grid_remove``), em vez de so tapar: assim a pagina
        fica com a altura do que esta a vista, e a tabela dos modos -- que so
        existe em introducao manual -- nao ocupa espaco no modo CSV.
        """
        if self.source.get() == "manual":
            self._csv_frame.grid_remove()
            self._manual_frame.grid()
            self._modes_card.grid()
        else:
            self._manual_frame.grid_remove()
            self._modes_card.grid_remove()
            self._csv_frame.grid()
        self._update_engine_state()

    def _load_dataset(self) -> None:
        path = self.f_dataset.value()
        if not path:
            return
        try:
            self._dataset = EngineDataset.from_csv(path)
            engines = self._dataset.engines()
        except Exception as exc:
            self._dataset = None
            self.f_engine.set_options([""])
            self.engine_info.configure(
                text="Não foi possível ler o ficheiro escolhido.")
            messagebox.showerror("Não consegui ler o ficheiro", str(exc))
            self.console.write(f"ERRO ao ler {path}: {exc}", "erro")
            return

        self.f_engine.set_options(engines)
        self.console.write(f"Ficheiro carregado: {path}")
        self.console.write(f"Motores encontrados ({len(engines)}): "
                           f"{', '.join(engines)}", "ok")
        self._set_status(f"Ficheiro carregado: {len(engines)} motores.")
        self._on_engine_change()

    def _on_engine_change(self) -> None:
        """Preenche L e A com a geometria instalada do motor escolhido."""
        self._update_engine_state()
        if (self._dataset is None or self.f_all_engines.value()
                or self.source.get() != "csv"):
            return
        engine = self.f_engine.value()
        if not engine:
            return
        from_file = True
        try:
            try:
                case = self._dataset.build_case(engine)
            except ValueError:
                # Ficheiro sem colunas de geometria: e valido. O comprimento
                # vem do separador da Geometria; aqui so se leem as condicoes
                # de operacao, que nao dependem dele.
                from_file = False
                case = self._dataset.build_case(engine, length_m=1.0,
                                                frontal_area_m2=1.0)
        except Exception as exc:
            self.console.write(f"Aviso ao ler o motor {engine}: {exc}", "erro")
            self.engine_info.configure(
                text=f"Não foi possível ler o motor {engine}: {exc}")
            return
        if from_file:
            self.f_length.set(f"{case.geometry.length_m:g}")
            length_note = (f"L sugerido pelo ficheiro = "
                           f"{case.geometry.length_m:.3f} m")
        else:
            length_note = ("o ficheiro não traz o comprimento: indique-o no "
                           "separador 2 · Geometria")
        self.console.write(
            f"{engine}: {case.n_modes} modos · {length_note} · "
            f"limite = {case.nox_limit_gkWh:.4f} g/kWh")
        self.console.write(
            f"    caudal de escape: {case.mass_flow_kgs.min():.3f} a "
            f"{case.mass_flow_kgs.max():.3f} kg/s · "
            f"NO à entrada: {case.NO_in_ppm.min():.0f} a "
            f"{case.NO_in_ppm.max():.0f} ppm")
        self.engine_info.configure(
            text=f"{engine}: {case.n_modes} modos  ·  limite NOx = "
                 f"{case.nox_limit_gkWh:.4f} g/kWh  ·  caudal de escape "
                 f"{case.mass_flow_kgs.min():.3f} a "
                 f"{case.mass_flow_kgs.max():.3f} kg/s  ·  NO à entrada "
                 f"{case.NO_in_ppm.min():.0f} a {case.NO_in_ppm.max():.0f} ppm"
                 f"  ·  {length_note}")

    def _update_engine_state(self) -> None:
        """Com «todos os motores», a escolha do motor fica inerte."""
        all_engines = self.f_all_engines.value() and self.source.get() == "csv"
        self.f_engine.combo.configure(
            state="disabled" if all_engines else "readonly")
        if self._dataset is None:
            self.engine_info.configure(text=NO_DATASET_INFO)
        elif all_engines:
            engines = self._dataset.engines()
            self.engine_info.configure(
                text=f"Serão corridos os {len(engines)} motores do ficheiro: "
                     f"{', '.join(engines)}. A geometria e a malha de volumes "
                     f"dos outros separadores aplicam-se a todos.")

    def _copy_from_dataset(self) -> None:
        """Preenche a tabela manual com o motor escolhido no ficheiro CSV."""
        if self._dataset is None:
            messagebox.showinfo(
                "Sem ficheiro",
                "Escolha primeiro um ficheiro CSV no separador «Ficheiro CSV».")
            return
        engine = self.f_engine.value()
        if not engine:
            messagebox.showinfo("Sem motor", "Escolha primeiro um motor.")
            return
        try:
            case = self._dataset.build_case(engine)
        except Exception as exc:
            messagebox.showerror("Não consegui ler o motor", str(exc))
            return

        self.mode_table.set_rows([
            {"load_pct": m.load_pct, "weight": m.weight, "power_kW": m.power_kW,
             "T_in_C": m.T_in_K - 273.15, "NO_in_ppm": m.NO_in_ppm,
             "sfoc_g_per_kWh": m.sfoc_g_per_kWh, "lambda_": m.lambda_}
            for m in case.modes])
        self.f_manual_name.set(case.name)
        if case.engine_speed_rpm is not None:
            self.f_manual_rpm.set(f"{case.engine_speed_rpm:g}")
        if case.rated_power_kW is not None:
            self.f_manual_rated.set(f"{case.rated_power_kW:g}")
        self.f_length.set(f"{case.geometry.length_m:g}")
        self.console.write(f"Tabela preenchida com {case.n_modes} modos "
                           f"do motor {case.name}.", "ok")
        self._set_status(f"Tabela preenchida com {case.n_modes} modos do motor "
                         f"{case.name}.")

    # ------------------------------------------------------------------ #
    #  Formulario  <->  RunScenario
    # ------------------------------------------------------------------ #
    def _collect_or_report(self) -> Optional[Tuple[RunScenario, Optional[str]]]:
        """Le o formulario; se houver um valor invalido, leva o utilizador a ele.

        Devolve ``None`` quando o formulario nao esta em condicoes de correr.
        """
        self.form.clear_flags()
        try:
            return self._collect()
        except FieldError as exc:
            self._reveal_error(exc)
            messagebox.showerror("Input inválido", str(exc))
        except Exception as exc:
            messagebox.showerror("Erro", f"{type(exc).__name__}: {exc}")
        return None

    def _reveal_error(self, exc: FieldError) -> None:
        """Abre o separador do campo invalido, da-lhe o foco e assinala-o.

        Sem isto a mensagem dizia o nome do parametro, mas era o utilizador que
        tinha de descobrir em que separador ele estava.
        """
        widget = getattr(exc, "widget", None)
        key = self.form.key_of(widget) if widget is not None else None
        if key is not None:
            self.form.select(key)
            self.update_idletasks()
            self._scroll_into_view(widget)
            with contextlib.suppress(tk.TclError):
                widget.focus_set()
        key = key or self.form.current
        self.form.flag(key)
        self._set_status("Input inválido: corrija o campo assinalado a vermelho.")

    def _collect(self) -> Tuple[RunScenario, Optional[str]]:
        """Le o formulario e devolve o cenario + o motor unico (ou ``None``)."""
        manual = self.source.get() == "manual"

        substrate, substrate_specs = self._collect_substrates()

        kinetics = KineticParameters(
            k0ads=self.f_k0ads.value(), Eads=self.f_Eads.value(),
            k0NO=self.f_k0NO.value(), ENO=self.f_ENO.value(),
            aging_KK0=self.f_KK0.value(),
            k0d=self.f_k0d.value(), E0d=self.f_E0d.value(),
            beta=self.f_beta.value(), f=self.f_f.value(),
            Deff=self.f_Deff.value(), Dmol=self.f_Dmol.value(),
            M_bar_kg_mol=self.f_Mbar.value())

        alpha_min = self.f_alpha_min.value()
        alpha_max = self.f_alpha_max.value()
        if alpha_min >= alpha_max:
            self.form.select("alpha")
            raise FieldError('"α mínimo" tem de ser menor que "α máximo".')

        length = self.f_length.value()
        v_max = self.f_v_max.value()
        v_min = self.f_v_min.value()
        if v_min >= v_max:
            self.form.select("varrimento")
            raise FieldError('"Volume mínimo" tem de ser menor que '
                             'o "Volume máximo".')
        # A geometria de referencia do caso e o MAIOR volume do varrimento: e o
        # ponto de partida, nao um reator instalado.
        area_seed = v_max / length

        common = dict(
            fuel=self.f_fuel.value(),
            substrate=substrate,
            substrates=substrate_specs,
            kinetics=kinetics,
            tuning=KineticTuning(kNO=self.f_t_kNO.value(), kads=self.f_t_kads.value(),
                                 Deff=self.f_t_Deff.value(), k0d=self.f_t_k0d.value()),
            targets=EmissionTargets(
                cycle_NO_frac=self.f_cyc_frac.value(),
                mode_NO_frac=self.f_mode_frac.value(),
                cycle_slip_ppm=self.f_cyc_slip.value(),
                mode_slip_ppm=self.f_mode_slip.value()),
            sweep=VolumeSweepOptions(
                volume_max_m3=v_max,
                volume_step_m3=self.f_v_step.value(),
                volume_min_m3=v_min,
                length_m=length,
                refine=self.f_refine.value(),
                refine_tol_m3=self.f_refine_tol.value(),
                fouling=self.f_fouling.value(),
                aging_KK0=None,          # já vai na cinética
                verbose=True),
            alpha_loop=AlphaLoopOptions(
                alpha0=self.f_alpha0.value(), dalpha=self.f_dalpha.value(),
                alpha_min=alpha_min, alpha_max=alpha_max,
                max_iter=self.f_max_iter.value(),
                bracket_tol=self.f_bracket_tol.value(),
                minimize_alpha=self.f_minimize.value()),
            solver=SolverOptions(n_nodes=self.f_nodes.value()),
            pressure_Pa=self.f_pressure.value(),
            tier=self.f_tier.value(),
            tier_power_law_only=self.f_power_law.value(),
            output_dir=None,             # a gravação é feita pela janela
        )

        if manual:
            spec = self._collect_manual_engine(length, area_seed)
            return RunScenario(inline_engines=[spec], length_m=length,
                               frontal_area_m2=area_seed, **common), spec["name"]

        dataset = self.f_dataset.value()
        if not dataset:
            self.form.select("motor")
            raise FieldError("Escolha o ficheiro de inputs (CSV), ou passe a "
                             "«Introdução manual».")
        if not Path(dataset).is_file():
            self.form.select("motor")
            raise FieldError(f"O ficheiro de inputs não existe:\n{dataset}")

        run_all = self.f_all_engines.value()
        engine = None if run_all else self.f_engine.value()
        if not run_all and not engine:
            self.form.select("motor")
            raise FieldError("Escolha o motor, ou ligue «Correr todos os motores».")

        scenario = RunScenario(
            dataset_path=dataset,
            engines=None if run_all else [engine],
            length_m=length,
            frontal_area_m2=area_seed,
            **common)
        return scenario, engine

    def _collect_substrates(self):
        """Devolve ``(substrato_base, lista_de_pares_ou_None)``.

        Em modo de comparação, um par impossível (``dh <= 0``) não é fatal: o
        varrimento regista-o com o motivo e segue para os outros. Só é erro se
        NENHUM par for possível.
        """
        if not self.f_sweep_substrate.value():
            substrate = SubstrateGeometry(cpsi=self.f_cpsi.value(),
                                          wall_thickness_m=self.f_wall.value())
            if not substrate.is_valid:
                self.form.select("geometria")
                raise FieldError(
                    "Geometria da célula inválida: a parede consome todo o passo "
                    f"(dh = {substrate.hydraulic_diameter_m * 1e3:.3f} mm ≤ 0). "
                    "Reduza a espessura de parede ou o CPSI.")
            return substrate, None

        try:
            pairs = self.substrate_table.rows()
        except FieldError:
            self.form.select("geometria")
            raise

        subs = [SubstrateGeometry(cpsi=row["cpsi"],
                                  wall_thickness_m=row["wall_mm"] / 1000.0)
                for row in pairs]
        usable = [s for s in subs if s.is_valid]
        if not usable:
            self.form.select("geometria")
            raise FieldError(
                "Nenhum dos pares CPSI / parede dá um canal possível (dh ≤ 0): "
                "a parede consome todo o passo de célula em todos eles.")

        specs = [{"cpsi": s.cpsi, "wall_thickness_m": s.wall_thickness_m}
                 for s in subs]
        return usable[0], specs

    def _collect_manual_engine(self, length: float, area_seed: float) -> Dict:
        """Monta o dicionario de motor a partir da tabela de introdução manual."""
        try:
            rows = self.mode_table.rows()
        except FieldError:
            self.form.select("motor")
            raise

        modes = []
        for index, row in enumerate(rows, start=1):
            has_flow = row.get("exhaust_mass_flow_kgs") is not None
            has_fuel = (row.get("sfoc_g_per_kWh") is not None
                        and row.get("lambda_") is not None)
            if not (has_flow or has_fuel):
                self.form.select("motor")
                raise FieldError(
                    f"Modo {index}: falta o caudal de escape. Preencha «SFOC» e "
                    f"«λ», ou então «Caudal esc.» directamente.")
            mode = dict(row)
            mode["T_in_K"] = mode.pop("T_in_C") + 273.15
            modes.append(mode)

        # Se o caudal não for dado em TODOS os modos, é calculado de SFOC + λ.
        if any(m.get("exhaust_mass_flow_kgs") is None for m in modes):
            for m in modes:
                m["exhaust_mass_flow_kgs"] = None

        return {
            "name": self.f_manual_name.value() or "motor",
            "engine_speed_rpm": self.f_manual_rpm.value(),
            "rated_power_kW": self.f_manual_rated.value(),
            "length_m": length,
            "frontal_area_m2": area_seed,
            "modes": modes,
        }

    def _apply(self, scn: RunScenario) -> None:
        """Preenche o formulario a partir de um cenario."""
        self.f_dataset.set(scn.dataset_path)
        self.f_fuel.set(scn.fuel)
        self.f_pressure.set(scn.pressure_Pa)
        self.f_tier.set(scn.tier)
        self.f_power_law.set(scn.tier_power_law_only)

        self.f_cpsi.set(scn.substrate.cpsi)
        self.f_wall.set(scn.substrate.wall_thickness_m)
        self.f_sweep_substrate.set(bool(scn.substrates))
        if scn.substrates:
            self.substrate_table.set_rows([
                {"cpsi": s["cpsi"], "wall_mm": s["wall_thickness_m"] * 1e3}
                for s in scn.substrates])
        self._update_substrate_state()
        if scn.length_m is not None:
            self.f_length.set(scn.length_m)
        self.f_fouling.set(scn.sweep.fouling if scn.sweep.fouling is not None else 0.0)

        k = scn.kinetics
        for fld, val in ((self.f_k0ads, k.k0ads), (self.f_Eads, k.Eads),
                         (self.f_k0NO, k.k0NO), (self.f_ENO, k.ENO),
                         (self.f_KK0, k.aging_KK0), (self.f_k0d, k.k0d),
                         (self.f_E0d, k.E0d), (self.f_beta, k.beta),
                         (self.f_f, k.f), (self.f_Deff, k.Deff),
                         (self.f_Dmol, k.Dmol), (self.f_Mbar, k.M_bar_kg_mol)):
            fld.set(val)

        t = scn.sweep.tuning if not scn.sweep.tuning.is_identity else scn.tuning
        self.f_t_kNO.set(t.kNO)
        self.f_t_kads.set(t.kads)
        self.f_t_Deff.set(t.Deff)
        self.f_t_k0d.set(t.k0d)

        g = scn.targets
        self.f_cyc_frac.set(g.cycle_NO_frac)
        self.f_mode_frac.set(g.mode_NO_frac)
        self.f_cyc_slip.set(g.cycle_slip_ppm)
        self.f_mode_slip.set(g.mode_slip_ppm)

        w = scn.sweep
        if w.volume_max_m3 is not None:
            self.f_v_max.set(w.volume_max_m3)
        self.f_v_step.set(w.volume_step_m3)
        self.f_v_min.set(w.volume_min_m3)
        self.f_refine.set(w.refine)
        self.f_refine_tol.set(w.refine_tol_m3)

        a = scn.alpha_loop
        self.f_alpha0.set(a.alpha0)
        self.f_dalpha.set(a.dalpha)
        self.f_alpha_min.set(a.alpha_min)
        self.f_alpha_max.set(a.alpha_max)
        self.f_max_iter.set(a.max_iter)
        self.f_bracket_tol.set(a.bracket_tol)
        self.f_minimize.set(a.minimize_alpha)

        self.f_nodes.set(scn.solver.n_nodes)
        self.f_outdir.set(scn.output_dir)

        if scn.inline_engines:
            spec = scn.inline_engines[0]
            self.source.set("manual")
            self.f_manual_name.set(spec.get("name", ""))
            self.f_manual_rpm.set(spec.get("engine_speed_rpm"))
            self.f_manual_rated.set(spec.get("rated_power_kW"))
            if spec.get("length_m") is not None:
                self.f_length.set(spec["length_m"])
            self.mode_table.set_rows([
                {**{k2: v for k2, v in mode.items() if k2 != "T_in_K"},
                 "T_in_C": (mode["T_in_K"] - 273.15
                            if mode.get("T_in_K") is not None else None)}
                for mode in spec.get("modes", [])])
        else:
            self.source.set("csv")
            if scn.dataset_path and Path(str(scn.dataset_path)).is_file():
                self._load_dataset()
                if scn.engines:
                    self.f_all_engines.set(False)
                    self.f_engine.set(scn.engines[0])
                    self._on_engine_change()
                    if scn.length_m is not None:
                        self.f_length.set(scn.length_m)
                else:
                    self.f_all_engines.set(True)
        self._update_source_state()

    # ------------------------------------------------------------------ #
    #  Accoes
    # ------------------------------------------------------------------ #
    def _on_reset(self) -> None:
        if not messagebox.askyesno(
                "Repor omissões",
                "Repor todos os parâmetros nos valores por omissão?\n"
                "O ficheiro de inputs e o motor escolhido não mudam."):
            return
        dataset, engine, all_engines = (self.f_dataset.value(),
                                        self.f_engine.value(),
                                        self.f_all_engines.value())
        source = self.source.get()
        default = RunScenario(dataset_path=dataset,
                              sweep=VolumeSweepOptions(fouling=0.15),
                              kinetics=KineticParameters(aging_KK0=0.80))
        self._apply(default)
        self.source.set(source)
        self.f_all_engines.set(all_engines)
        if engine:
            self.f_engine.set(engine)
            self._on_engine_change()
        self._update_source_state()
        self.form.clear_flags()
        self.console.write("Parâmetros repostos nos valores por omissão.", "ok")
        self._set_status("Parâmetros repostos nos valores por omissão.")

    def _on_save_scenario(self) -> None:
        collected = self._collect_or_report()
        if collected is None:
            return
        scenario, _ = collected
        path = filedialog.asksaveasfilename(
            title="Gravar cenário", defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("Todos", "*.*")))
        if not path:
            return
        data = scenario.to_dict()
        data["output_dir"] = self.f_outdir.value()
        Path(path).write_text(json.dumps(data, indent=2, default=str),
                              encoding="utf-8")
        self.console.write(f"Cenário gravado: {path}", "ok")
        self._set_status(f"Cenário gravado: {path}")

    def _on_load_scenario(self) -> None:
        path = filedialog.askopenfilename(
            title="Carregar cenário",
            filetypes=(("JSON", "*.json"), ("Todos", "*.*")))
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            scenario = RunScenario.from_dict(data)
        except Exception as exc:
            messagebox.showerror("Cenário inválido", str(exc))
            return
        self._apply(scenario)
        self.form.clear_flags()
        self.console.write(f"Cenário carregado: {path}", "ok")
        self._set_status(f"Cenário carregado: {path}")

    def _on_save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Gravar registo", defaultextension=".txt",
            filetypes=(("Texto", "*.txt"), ("Todos", "*.*")))
        if not path:
            return
        Path(path).write_text(self.console.dump(), encoding="utf-8")
        self.console.write(f"Registo gravado: {path}", "ok")
        self._set_status(f"Registo gravado: {path}")

    # ------------------------------------------------------------------ #
    #  Corrida
    # ------------------------------------------------------------------ #
    def _on_run(self) -> None:
        if self._running:
            return
        collected = self._collect_or_report()
        if collected is None:
            return
        scenario, engine = collected

        outdir = self.f_outdir.value()
        save_csv = self.f_save_csv.value()
        save_png = self.f_save_png.value()
        if (save_csv or save_png) and not outdir:
            if not messagebox.askyesno(
                    "Sem pasta de resultados",
                    "Não indicou pasta de resultados: nada será gravado em disco.\n"
                    "Continuar mesmo assim?"):
                self.form.select("saida")
                return
            save_csv = save_png = False

        self._set_running(True)
        self.console.clear()
        self.console.write(APP_TITLE, "titulo")
        # Durante o calculo ve-se o registo a encher; no fim passa-se ao resumo.
        self.results.clear(title="A calcular…", steps=(
            "O progresso de cada volume aparece no separador «Registo».",))
        self.results.select("registo")
        self._sync_form_height()         # da espaco ao painel de resultados
        args = (scenario, engine, outdir if (save_csv or save_png) else None,
                save_csv, save_png)
        threading.Thread(target=self._worker, args=args, daemon=True).start()
        self.after(80, self._drain)

    def _worker(self, scenario: RunScenario, engine: Optional[str],
                outdir: Optional[str], save_csv: bool, save_png: bool) -> None:
        """Corre o dimensionamento (thread separada) e alimenta a consola."""
        writer = _QueueWriter(self._queue)
        try:
            with contextlib.redirect_stdout(writer):
                if scenario.substrates:
                    payload = self._run_substrate_sweep(scenario, outdir,
                                                        save_csv, save_png)
                else:
                    payload = self._run_volume_sweep(scenario, engine, outdir,
                                                     save_csv, save_png)
            writer.flush()
            self._queue.put(("done", payload))
        except Exception:
            writer.flush()
            self._queue.put(("error", traceback.format_exc()))

    @staticmethod
    def _run_volume_sweep(scenario, engine, outdir, save_csv, save_png) -> Dict:
        if engine is None:
            batch = scenario.run()
            results = list(batch.sweeps.values())
            summary = batch.summary
        else:
            results = [scenario.run_one(engine)]
            summary = None

        written: List[str] = []
        if outdir:
            base = Path(outdir)
            if save_csv:
                from tvscr import write_sweep_outputs
                for r in results:
                    for path in write_sweep_outputs(r, base).values():
                        if path:
                            written.append(str(path))
                if summary is not None:
                    summary.to_csv(base / "resumo_volumes_criticos.csv", index=False)
                    written.append(str(base / "resumo_volumes_criticos.csv"))
            if save_png:
                written += _save_figures(results, summary, base)
        return {"kind": "volume", "results": results, "summary": summary,
                "written": written, "sweep": None}

    @staticmethod
    def _run_substrate_sweep(scenario, outdir, save_csv, save_png) -> Dict:
        sweep = scenario.run_substrate_sweep()

        written: List[str] = []
        if outdir:
            base = Path(outdir)
            base.mkdir(parents=True, exist_ok=True)
            if save_csv:
                path = base / "resumo_substratos.csv"
                sweep.summary.to_csv(path, index=False)
                written.append(str(path))
            for row in sweep.rows:
                if row.result is None:
                    continue
                folder = (f"{row.engine}_CPSI{row.substrate.cpsi:g}"
                          f"_w{row.substrate.wall_thickness_m * 1e3:g}mm")
                if save_csv:
                    from tvscr import write_sweep_outputs
                    for path in write_sweep_outputs(row.result, base,
                                                    subdir=folder).values():
                        if path:
                            written.append(str(path))
                if save_png:
                    written += _save_figures([row.result], None, base / folder,
                                             subdir_per_engine=False)
        return {"kind": "substratos", "results": [], "summary": sweep.summary,
                "written": written, "sweep": sweep}

    def _drain(self) -> None:
        """Passa a fila para a consola (corre na thread da interface)."""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self.console.write(str(payload))
                elif kind == "done":
                    elapsed = time.monotonic() - self._run_started
                    self._on_finished(payload)
                    self._set_running(False,
                                      status=f"Concluído em {elapsed:.1f} s.")
                    return
                elif kind == "error":
                    self.console.write("\nERRO durante o cálculo:", "erro")
                    for line in str(payload).rstrip().splitlines():
                        self.console.write(line, "erro")
                    self.results.clear(title="O cálculo falhou", steps=(
                        "A mensagem de erro está no separador «Registo».",))
                    self.results.select("registo")
                    self._set_running(False, status="O cálculo falhou: ver o "
                                                    "registo.")
                    messagebox.showerror(
                        "Erro durante o cálculo",
                        str(payload).rstrip().splitlines()[-1])
                    return
        except queue.Empty:
            pass
        if self._running:
            self.after(80, self._drain)

    def _on_finished(self, payload: Dict) -> None:
        self.console.write("")
        if payload["kind"] == "substratos":
            self._report_substrate_sweep(payload["sweep"])
        else:
            self._report_volume_sweep(payload["results"])

        written = payload["written"]
        if written:
            self.console.write("")
            self.console.write(f"Gravados {len(written)} ficheiros:")
            for path in written:
                self.console.write(f"  {path}")
        self.console.write("")
        self.console.write("Concluído.", "ok")

        # Os mesmos numeros, agora de forma estruturada no painel de resultados.
        if payload["kind"] == "substratos":
            self.results.show_substrates(payload["sweep"])
        else:
            self.results.show_volume(payload["results"])
        self.results.select("resumo")
        self._sync_form_height()

    def _report_volume_sweep(self, results) -> None:
        self.console.write("RESULTADO", "titulo")
        for r in results:
            if r.critical_volume_m3 == r.critical_volume_m3:      # não é NaN
                crit = r.at_critical()
                self.console.write(
                    f"  {r.engine}: VOLUME CRÍTICO = {r.critical_volume_m3:.3f} m³ "
                    f"(A = {r.critical_area_m2:.3f} m², L = {r.length_m:.2f} m)", "ok")
                self.console.write(
                    f"      nesse volume: NOx = {crit['NOx_ciclo_gkWh']:.4f} g/kWh · "
                    f"slip = {crit['slip_ciclo_ppm']:.3f} ppm · "
                    f"X_NO = {crit['XNO_ciclo_perc']:.2f} % · "
                    f"ureia = {crit['urea_ciclo_Lh']:.2f} L/h")
                self.console.write(
                    "      α por modo: "
                    + "  ".join(f"{load:.0f}%={a:.3f}"
                                for load, a in zip(r.load_pct, crit["alpha"])))
            else:
                self.console.write(
                    f"  {r.engine}: nenhum volume admissível entre "
                    f"{r.volume_m3.min():.2f} e {r.volume_max_m3:.2f} m³. "
                    f"Motivo no maior volume: {r.why[0] if r.why else 'n/d'}", "erro")
                self.console.write(
                    "      Suba o «Volume máximo», alivie os alvos, ou reduza "
                    "o fouling / envelhecimento.", "erro")

    def _report_substrate_sweep(self, sweep) -> None:
        self.console.write("RESULTADO — comparação de substratos", "titulo")
        for engine in sweep.engines:
            best = sweep.best_for(engine)
            if best is None:
                self.console.write(
                    f"  {engine}: nenhum par CPSI / parede deu um volume "
                    f"admissível.", "erro")
                continue
            s = best.substrate
            self.console.write(
                f"  {engine}: melhor par = CPSI {s.cpsi:g} / parede "
                f"{s.wall_thickness_m * 1e3:.2f} mm  ·  "
                f"V crítico = {best.result.critical_volume_m3:.3f} m³  "
                f"(A = {best.result.critical_area_m2:.3f} m²)", "ok")
        for row in sweep.rows:
            if not row.ok and row.reason:
                s = row.substrate
                self.console.write(
                    f"  {row.engine} · CPSI {s.cpsi:g} / "
                    f"{s.wall_thickness_m * 1e3:.2f} mm: {row.reason}", "erro")

    def _set_running(self, running: bool, status: str = "Pronto") -> None:
        self._running = running
        self.btn_run.configure(state="disabled" if running else "normal",
                               text="A correr…" if running else RUN_LABEL,
                               bg=C.RUN_BG)
        self.configure(cursor="watch" if running else "")
        if running:
            self._run_started = time.monotonic()
            self.progress.pack(side="left", padx=(16, 0), pady=5,
                               before=self.status)
            self.progress.start(14)
            self._tick()
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self._set_status(status)

    def _tick(self) -> None:
        """Actualiza o tempo decorrido na barra de estado enquanto corre."""
        if not self._running:
            return
        elapsed = time.monotonic() - self._run_started
        self._set_status(f"A calcular… {elapsed:.0f} s  (tipicamente 4 a 5 s "
                         f"por motor e por substrato)")
        self.after(250, self._tick)

    def _on_close(self) -> None:
        if self._running and not messagebox.askyesno(
                "Sair", "Há um cálculo a decorrer. Sair mesmo assim?"):
            return
        self.destroy()


# ====================================================================== #
#  Auxiliares
# ====================================================================== #
class _QueueWriter:
    """Ficheiro de escrita que envia linhas completas para a fila da consola."""

    def __init__(self, q: "queue.Queue") -> None:
        self._queue = q
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._queue.put(("log", line))
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._queue.put(("log", self._buffer))
            self._buffer = ""


def _save_figures(results, summary, base: Path,
                  subdir_per_engine: bool = True) -> List[str]:
    """Grava as figuras; devolve os caminhos escritos (vazio se faltar matplotlib)."""
    try:
        from tvscr.plotting import plot_critical_volumes, plot_volume_sweep
    except ImportError:
        print("(matplotlib não disponível: figuras ignoradas)")
        return []

    written: List[str] = []
    for r in results:
        folder = base / r.engine if subdir_per_engine else base
        path = folder / f"volume_sweep_{r.engine}.png"
        plot_volume_sweep(r, path)
        written.append(str(path))
    if summary is not None and len(summary) > 1:
        from tvscr import BatchResult
        path = base / "resumo_volumes_criticos.png"
        plot_critical_volumes(BatchResult(summary=summary), path)
        written.append(str(path))
    return written


def launch() -> None:
    """Abre a janela principal."""
    MainWindow().mainloop()
