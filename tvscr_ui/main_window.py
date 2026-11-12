"""
Janela principal da aplicacao de dimensionamento SCR.

A interface NAO calcula nada: recolhe os inputs, monta um
:class:`tvscr.RunScenario` e chama :meth:`~tvscr.RunScenario.run` /
:meth:`~tvscr.RunScenario.run_one`. Todo o modelo esta no pacote ``tvscr``.

As oito seccoes de inputs sao paginas escondidas, mostradas uma de cada vez
pelos separadores no topo. Os dados do motor podem vir de um ficheiro CSV ou
ser introduzidos a mao numa tabela.

O varrimento corre numa thread separada; a consola e alimentada por uma fila,
para a janela nunca bloquear.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tvscr import (AlphaLoopOptions, EmissionTargets, EngineDataset,
                   KineticParameters, KineticTuning, RunScenario,
                   SolverOptions, SubstrateGeometry, VolumeSweepOptions)

from .paged import Column, EditableTable, ModeTable, PagedForm, RadioGroup
from .theme import C, F, init_fonts
from .widgets import (CheckField, ChoiceField, Console, FieldError, FloatField,
                      IntField, PathField, Section, TextField, Tooltip)

__all__ = ["MainWindow", "launch"]

APP_TITLE = "TECNOVERITAS SCR DIMENSIONING TOOL"
APP_SUBTITLE = "Dimensionamento de reatores SCR-deNOx · "\
               "varrimento em volume com α adaptativo"

LOGO = Path(__file__).with_name("assets") / "tecnoveritas.png"

FUELS = ["HFO", "MDO", "MGO", "LSFO"]
TIERS = ["III", "II", "I"]

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
    Column("lambda_", "λ", "-", 8, required=False,
           tooltip="Excesso de ar. Com o SFOC, dá o caudal de escape."),
    Column("exhaust_mass_flow_kgs", "Caudal esc.", "kg/s", 10, required=False,
           tooltip="Caudal mássico de escape. Se o preencher em TODOS os modos, "
                   "é usado directamente e SFOC + λ passam a ser dispensáveis."),
]


class MainWindow(tk.Tk):
    """Janela unica: separadores de inputs em cima, consola em baixo."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1210x880")
        self.minsize(1000, 640)
        self.configure(bg=C.BG)

        init_fonts(self)
        self._init_styles()

        self._queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self._running = False
        self._dataset: Optional[EngineDataset] = None
        self._logo_image: Optional[tk.PhotoImage] = None

        self._build_header()
        self._build_pages()
        self._build_actions()
        self._build_console()

        self.console.write(APP_TITLE, "titulo")
        self.console.write("Escolha a origem dos dados do motor, percorra os "
                           "separadores e prima «Correr dimensionamento».")
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
                        foreground=C.FIELD_FG, arrowcolor=C.BTN_FG,
                        bordercolor=C.BORDER, lightcolor=C.FIELD_BG,
                        darkcolor=C.FIELD_BG, padding=2)
        style.map("TVSCR.TCombobox",
                  fieldbackground=[("readonly", C.FIELD_BG),
                                   ("disabled", C.FIELD_DISABLED)],
                  selectbackground=[("readonly", C.FIELD_BG)],
                  selectforeground=[("readonly", C.FIELD_FG)])
        self.option_add("*TCombobox*Listbox.background", C.FIELD_BG)
        self.option_add("*TCombobox*Listbox.foreground", C.FIELD_FG)
        self.option_add("*TCombobox*Listbox.selectBackground", C.BG_PANEL)
        self.option_add("*TCombobox*Listbox.selectForeground", C.TEXT)

    def _button(self, parent, text, command, primary: bool = False, **kw):
        colours = dict(bg=C.RUN_BG, fg=C.RUN_FG, activebackground=C.RUN_ACTIVE) \
            if primary else dict(bg=C.BTN_BG, fg=C.BTN_FG, activebackground=C.BTN_ACTIVE)
        return tk.Button(parent, text=text, command=command, relief="flat",
                         font=F.BOLD if primary else F.BASE, cursor="hand2",
                         padx=14, pady=6, bd=0, **colours, **kw)

    def _small_button(self, parent, text, command, **kw):
        return tk.Button(parent, text=text, command=command, relief="flat",
                         font=F.SMALL, cursor="hand2", padx=9, pady=3, bd=0,
                         bg=C.BTN_BG, fg=C.BTN_FG, activebackground=C.BTN_ACTIVE,
                         **kw)

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
                         bd=0).pack(side="right", padx=16, pady=10)
            except tk.TclError:                    # imagem ilegivel: segue sem ela
                self._logo_image = None

        text = tk.Frame(bar, bg=C.BG_HEADER)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=APP_TITLE, bg=C.BG_HEADER, fg=C.TITLE,
                 font=F.TITLE, anchor="w").pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(text, text=APP_SUBTITLE, bg=C.BG_HEADER, fg=C.TEXT_DIM,
                 font=F.SUBTITLE, anchor="w").pack(fill="x", padx=16, pady=(2, 14))

    # ------------------------------------------------------------------ #
    #  Paginas de inputs
    # ------------------------------------------------------------------ #
    def _build_pages(self) -> None:
        holder = tk.Frame(self, bg=C.BG)
        # fill="x" e nao "both": o formulario fica com a altura do seu conteudo
        # e a folga sobrante vai toda para a consola.
        holder.pack(fill="x", padx=12, pady=(10, 0))

        canvas = tk.Canvas(holder, bg=C.BG, highlightthickness=0)
        vbar = tk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        self._form_canvas = canvas
        self._form_scrollbar = vbar        # so aparece se o conteudo nao couber

        inner = tk.Frame(canvas, bg=C.BG)
        self._form_inner = inner
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", self._sync_form_height)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(window, width=e.width))
        # A roda do rato so mexe o formulario se o ponteiro estiver SOBRE ele.
        # Sem esta verificacao, rolar na consola mexia tambem o formulario.
        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        self.form = PagedForm(inner)
        self.form.pack(fill="both", expand=True)

        self._build_engine_page(self.form.add_page(
            "motor", "1 · Dados do motor",
            "Ficheiro CSV ou introdução manual dos modos do ciclo"))
        self._build_geometry_page(self.form.add_page(
            "geometria", "2 · Geometria", "Substrato e monolito instalado"))
        self._build_targets_page(self.form.add_page(
            "alvos", "3 · Alvos", "Limites de NOx e de NH₃ slip"))
        self._build_kinetics_page(self.form.add_page(
            "cinetica", "4 · Cinética", "Parâmetros do modelo de Tronconi"))
        self._build_tuning_page(self.form.add_page(
            "calibracao", "5 · Calibração", "Multiplicadores sobre a cinética"))
        self._build_sweep_page(self.form.add_page(
            "varrimento", "6 · Varrimento", "Malha de volumes e refinamento"))
        self._build_alpha_page(self.form.add_page(
            "alpha", "7 · Loop de α", "Procura do doseamento admissível"))
        self._build_output_page(self.form.add_page(
            "saida", "8 · Numérico e saída", "Malha do solver e ficheiros"))

    def _sync_form_height(self, _event=None) -> None:
        """Da ao formulario a altura do seu conteudo, ate um tecto razoavel.

        Assim nao sobra area verde vazia por baixo da pagina, e a barra de
        rolamento so aparece quando o conteudo nao cabe mesmo (uma tabela
        manual com muitas linhas, por exemplo).
        """
        canvas, inner = self._form_canvas, self._form_inner
        needed = inner.winfo_reqheight()
        cap = int(self.winfo_screenheight() * 0.52)
        canvas.configure(height=min(needed, cap),
                         scrollregion=canvas.bbox("all"))
        if needed > cap:
            if not self._form_scrollbar.winfo_ismapped():
                self._form_scrollbar.pack(side="right", fill="y")
        elif self._form_scrollbar.winfo_ismapped():
            self._form_scrollbar.pack_forget()

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
        self._form_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    @staticmethod
    def _columns(page: tk.Frame, count: int, weights=None) -> List[tk.Frame]:
        """Divide uma pagina em colunas."""
        frames = []
        weights = weights or [1] * count
        for i in range(count):
            frame = tk.Frame(page, bg=C.BG_PANEL)
            frame.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 14, 0))
            page.columnconfigure(i, weight=weights[i])
            frames.append(frame)
        page.rowconfigure(0, weight=1)
        return frames

    # -- 1. dados do motor ----------------------------------------------- #
    def _build_engine_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2, weights=[4, 1])

        # --- origem dos dados ---
        chooser = tk.Frame(left, bg=C.BG_PANEL)
        chooser.pack(fill="x", pady=(0, 6))
        tk.Label(chooser, text="ORIGEM DOS DADOS", bg=C.BG_PANEL, fg=C.TITLE,
                 font=F.BOLD).pack(side="left", padx=(0, 14))
        self.source = tk.StringVar(value="csv")
        self.source_radio = RadioGroup(
            chooser, self.source,
            [("csv", "Ficheiro CSV"), ("manual", "Introdução manual")],
            command=self._update_source_state)
        self.source_radio.pack(side="left")
        self.source.trace_add("write", lambda *_: self._update_source_state())

        # --- area que muda conforme a origem ---
        area = tk.Frame(left, bg=C.BG_PANEL)
        area.pack(fill="both", expand=True)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)

        self._csv_frame = tk.Frame(area, bg=C.BG_PANEL)
        self._csv_frame.grid(row=0, column=0, sticky="nsew")
        self._manual_frame = tk.Frame(area, bg=C.BG_PANEL)
        self._manual_frame.grid(row=0, column=0, sticky="nsew")

        self._build_csv_source(self._csv_frame)
        self._build_manual_source(self._manual_frame)

        # --- comum as duas origens ---
        common = Section(right, "MOTOR E COMBUSTÍVEL", flat=True, note_wrap=260,
                         note="Aplica-se seja qual for a origem dos dados.")
        common.pack(fill="x")
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

    def _build_csv_source(self, parent: tk.Frame) -> None:
        s = Section(parent, "FICHEIRO DE INPUTS", flat=True, note_wrap=520,
                    note="Uma linha por modo do ciclo e por motor. As condições de "
                         "operação — carga, peso, potência, temperatura, NO à "
                         "entrada, SFOC e λ — vêm todas daqui.")
        s.pack(fill="x")
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

    def _build_manual_source(self, parent: tk.Frame) -> None:
        s = Section(parent, "INTRODUÇÃO MANUAL", flat=True, note_wrap=760,
                    note="Um modo por linha. Linhas em branco são ignoradas. Para o "
                         "caudal de escape, preencha SFOC + λ ou, em alternativa, a "
                         "coluna «Caudal esc.» em todos os modos.")
        s.pack(fill="x")
        self.f_manual_name = TextField(s, "Nome do motor", "DG1", width=16)
        self.f_manual_rpm = FloatField(s, "Rotação nominal", 513.0, "rpm",
                                       minimum=1.0,
                                       tooltip="Define o limite MARPOL em g/kWh.")
        self.f_manual_rated = FloatField(s, "Potência nominal", None, "kW",
                                         minimum=0.0, allow_empty=True,
                                         tooltip="Opcional: só entra no relatório.")

        table_holder = tk.Frame(parent, bg=C.BG_PANEL)
        table_holder.pack(fill="both", expand=True, pady=(6, 0))
        self.mode_table = ModeTable(table_holder, MODE_COLUMNS, initial_rows=4)
        self.mode_table.pack(anchor="w")

        buttons = tk.Frame(parent, bg=C.BG_PANEL)
        buttons.pack(fill="x", pady=(8, 0))
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

    # -- 2. geometria ----------------------------------------------------- #
    def _build_geometry_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "SUBSTRATO", flat=True, note_wrap=420,
                    note="Escolha de projeto: não vem do ficheiro de inputs. "
                         "Pode comparar vários pares num só cálculo.")
        s.pack(fill="x")
        self.f_sweep_substrate = CheckField(
            s, "Comparar vários pares CPSI / parede", False,
            tooltip="Corre o varrimento em volume uma vez por par e põe os "
                    "volumes críticos lado a lado. O tempo de cálculo é "
                    "multiplicado pelo número de pares.")
        self.f_sweep_substrate.var.trace_add(
            "write", lambda *_: self._update_substrate_state())

        area = tk.Frame(left, bg=C.BG_PANEL)
        area.pack(fill="x", pady=(4, 0))
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
        buttons.pack(fill="x", pady=(8, 0))
        self._small_button(buttons, "+ Adicionar par",
                           self.substrate_table.add_row).pack(side="left")
        self._small_button(buttons, "− Remover último",
                           self.substrate_table.remove_last_row).pack(side="left",
                                                                      padx=6)
        self._small_button(buttons, "Limpar tabela",
                           lambda: self.substrate_table.clear(3)).pack(side="left")

        g = Section(right, "MONOLITO", flat=True, note_wrap=400,
                    note="O comprimento fica FIXO durante o varrimento e a área "
                         "frontal sai do volume: A = V / L. É o volume que o "
                         "cálculo procura, não a área.")
        g.pack(fill="x")
        self.f_length = FloatField(g, "Comprimento L", 1.2, "m", minimum=1e-6,
                                   tooltip="Comprimento do monolito a instalar. "
                                           "Fica fixo; o varrimento faz variar a "
                                           "área frontal (A = V / L).")

    def _update_substrate_state(self) -> None:
        """Mostra a tabela de pares ou os dois campos únicos."""
        if self.f_sweep_substrate.value():
            self._multi_substrate.tkraise()
        else:
            self._single_substrate.tkraise()

    # -- 3. alvos --------------------------------------------------------- #
    def _build_targets_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "NOx", flat=True, note_wrap=380,
                    note="Frações do limite MARPOL calculado para a rotação do "
                         "motor. O ciclo ponderado é mais apertado que cada modo.")
        s.pack(fill="x")
        self.f_cyc_frac = FloatField(s, "NOx do ciclo (fração)", 0.60, "-",
                                     minimum=0.0, maximum=1.0)
        self.f_mode_frac = FloatField(s, "NOx por modo (fração)", 0.80, "-",
                                      minimum=0.0, maximum=1.0)

        t = Section(right, "NH₃ SLIP", flat=True, note_wrap=380,
                    note="Amoníaco não reagido à saída do reator.")
        t.pack(fill="x")
        self.f_cyc_slip = FloatField(t, "Slip do ciclo", 10.0, "ppm", minimum=0.0)
        self.f_mode_slip = FloatField(t, "Slip por modo", 20.0, "ppm", minimum=0.0)

    # -- 4. cinetica ------------------------------------------------------ #
    def _build_kinetics_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "REAÇÃO", flat=True, note_wrap=380,
                    note="Valores por omissão: Tabela 2 de Tronconi 1998 "
                         "(catalisador 1). Energias de ativação em cal/mol.")
        s.pack(fill="x")
        self.f_k0ads = FloatField(s, "k0 adsorção NH₃", 8.5e6, "-", minimum=0.0)
        self.f_Eads = FloatField(s, "E adsorção NH₃", 9.0e3, "cal/mol")
        self.f_k0NO = FloatField(s, "k0 redução NO", 2.5e10, "-", minimum=0.0)
        self.f_ENO = FloatField(s, "E redução NO", 18.6e3, "cal/mol")
        self.f_k0d = FloatField(s, "k0 dessorção NH₃", 8.0e8, "-", minimum=0.0)
        self.f_E0d = FloatField(s, "E dessorção (θ=0)", 2.6e4, "cal/mol")
        self.f_beta = FloatField(s, "β (Temkin)", 0.32, "-")

        t = Section(right, "TRANSPORTE E ESTADO DO CATALISADOR", flat=True,
                    note_wrap=380,
                    note="Envelhecimento e fouling são o que separa um reator que "
                         "cumpre no primeiro dia de um que cumpre ao fim da vida.")
        t.pack(fill="x")
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
        s = Section(left, "MULTIPLICADORES DE CALIBRAÇÃO", flat=True, note_wrap=380,
                    note="Aplicados por cima da cinética já calculada, para ajustar "
                         "o modelo a um catalisador concreto sem mexer nos "
                         "parâmetros físicos. Tudo a 1 reproduz a referência.")
        s.pack(fill="x")
        self.f_t_kNO = FloatField(s, "× kNO", 1.0, "-", minimum=0.0)
        self.f_t_kads = FloatField(s, "× kads", 1.0, "-", minimum=0.0)
        self.f_t_Deff = FloatField(s, "× Deff", 1.0, "-", minimum=0.0)
        self.f_t_k0d = FloatField(s, "× k0d", 1.0, "-", minimum=0.0)

    # -- 6. varrimento ---------------------------------------------------- #
    def _build_sweep_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "MALHA DE VOLUMES", flat=True, note_wrap=380,
                    note="Desce em volume até ao primeiro volume inadmissível — "
                         "esse é o volume crítico. L fica fixo e a área varia "
                         "(A = V / L).")
        s.pack(fill="x")
        self.f_v_max = FloatField(s, "Volume máximo", 3.50, "m³", minimum=1e-6,
                                  tooltip="Maior volume a considerar; o varrimento "
                                          "começa aqui e desce. Se o maior volume "
                                          "já não cumprir os alvos, não há solução "
                                          "no intervalo.")
        self.f_v_step = FloatField(s, "Decremento de volume", 0.20, "m³",
                                   minimum=1e-6)
        self.f_v_min = FloatField(s, "Volume mínimo", 0.20, "m³", minimum=1e-6)

        t = Section(right, "REFINAMENTO", flat=True, note_wrap=380,
                    note="Bisseção em V entre o último volume admissível e o "
                         "primeiro que falhou, para afinar o volume crítico para "
                         "além da resolução do passo.")
        t.pack(fill="x")
        self.f_refine = CheckField(t, "Refinar por bisseção em V", True)
        self.f_refine_tol = FloatField(t, "Tolerância do refinamento", 0.02, "m³",
                                       minimum=1e-9)

    # -- 7. loop de alpha ------------------------------------------------- #
    def _build_alpha_page(self, page: tk.Frame) -> None:
        left, right = self._columns(page, 2)

        s = Section(left, "PROCURA DE α", flat=True, note_wrap=380,
                    note="Procura, por modo, o α que cumpre NO_out e slip nos dois "
                         "níveis. Bracketing + bisseção geométrica contra "
                         "oscilação.")
        s.pack(fill="x")
        self.f_alpha0 = FloatField(s, "α de arranque", 0.80, "-", minimum=0.0)
        self.f_dalpha = FloatField(s, "Passo de α", 0.02, "-", minimum=1e-9)
        self.f_alpha_min = FloatField(s, "α mínimo", 0.30, "-", minimum=0.0)
        self.f_alpha_max = FloatField(s, "α máximo", 1.20, "-", minimum=0.0)

        t = Section(right, "CONVERGÊNCIA", flat=True, note_wrap=380)
        t.pack(fill="x")
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

        s = Section(left, "SOLVER", flat=True, note_wrap=380,
                    note="Malha axial do modelo 1-D. 120 é o valor validado; "
                         "alterar muda o resultado ao nível da discretização.")
        s.pack(fill="x")
        self.f_nodes = IntField(s, "Nós axiais", 120, "-", minimum=10)

        t = Section(right, "FICHEIROS", flat=True, note_wrap=380,
                    note="Sem pasta indicada, nada é gravado em disco — os "
                         "resultados ficam só na consola.")
        t.pack(fill="x")
        self.f_outdir = PathField(t, "Pasta de resultados", mode="dir")
        self.f_save_csv = CheckField(t, "Gravar CSV", True)
        self.f_save_png = CheckField(t, "Gravar figuras (PNG)", True)

    # ------------------------------------------------------------------ #
    #  Barra de accoes e consola
    # ------------------------------------------------------------------ #
    def _build_actions(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        self._actions_bar = bar
        bar.pack(fill="x", padx=12, pady=(5, 6))

        self.btn_run = self._button(bar, "▶  Correr dimensionamento",
                                    self._on_run, primary=True)
        self.btn_run.pack(side="left")
        self._button(bar, "Repor omissões", self._on_reset).pack(side="left",
                                                                 padx=(8, 0))
        self._button(bar, "Carregar cenário…", self._on_load_scenario).pack(
            side="left", padx=(8, 0))
        self._button(bar, "Gravar cenário…", self._on_save_scenario).pack(
            side="left", padx=(8, 0))
        self._button(bar, "Gravar registo…", self._on_save_log).pack(
            side="left", padx=(8, 0))
        self._button(bar, "Limpar consola",
                     lambda: self.console.clear()).pack(side="left", padx=(8, 0))

        self.status = tk.Label(bar, text="pronto", bg=C.BG, fg=C.TEXT_DIM,
                               font=F.BASE, anchor="e")
        self.status.pack(side="right")

    def _build_console(self) -> None:
        self.console = Console(self, height=12)
        # expand=True: toda a folga da janela vai para a consola.
        self.console.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _fit_to_screen(self) -> None:
        """Ajusta a janela ao conteudo, sem passar dos limites do ecra."""
        self.update_idletasks()
        chrome = 65
        # Alvo: consola com 20 linhas. Se nao couber, o clamp ao ecra encarrega-se.
        console_target = F.MONO.metrics("linespace") * 20 + 24
        needed = (self._header_bar.winfo_reqheight()
                  + self._form_canvas.winfo_reqheight()
                  + self._actions_bar.winfo_reqheight()
                  + console_target + chrome)
        height = min(needed, int(self.winfo_screenheight() * 0.90))
        width = min(1210, int(self.winfo_screenwidth() * 0.95))
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ------------------------------------------------------------------ #
    #  Origem dos dados
    # ------------------------------------------------------------------ #
    def _update_source_state(self) -> None:
        """Mostra a area da origem escolhida e esconde a outra."""
        if self.source.get() == "manual":
            self._manual_frame.tkraise()
        else:
            self._csv_frame.tkraise()
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
            messagebox.showerror("Não consegui ler o ficheiro", str(exc))
            self.console.write(f"ERRO ao ler {path}: {exc}", "erro")
            return

        self.f_engine.set_options(engines)
        self.console.write(f"Ficheiro carregado: {path}")
        self.console.write(f"Motores encontrados ({len(engines)}): "
                           f"{', '.join(engines)}", "ok")
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
        try:
            case = self._dataset.build_case(engine)
        except Exception as exc:
            self.console.write(f"Aviso ao ler o motor {engine}: {exc}", "erro")
            return
        self.f_length.set(f"{case.geometry.length_m:g}")
        self.console.write(
            f"{engine}: {case.n_modes} modos · L sugerido pelo ficheiro = "
            f"{case.geometry.length_m:.3f} m · "
            f"limite = {case.nox_limit_gkWh:.4f} g/kWh")
        self.console.write(
            f"    caudal de escape: {case.mass_flow_kgs.min():.3f} a "
            f"{case.mass_flow_kgs.max():.3f} kg/s · "
            f"NO à entrada: {case.NO_in_ppm.min():.0f} a "
            f"{case.NO_in_ppm.max():.0f} ppm")

    def _update_engine_state(self) -> None:
        """Com «todos os motores», a escolha do motor fica inerte."""
        all_engines = self.f_all_engines.value() and self.source.get() == "csv"
        self.f_engine.combo.configure(
            state="disabled" if all_engines else "readonly")

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

    # ------------------------------------------------------------------ #
    #  Formulario  <->  RunScenario
    # ------------------------------------------------------------------ #
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
        self.console.write("Parâmetros repostos nos valores por omissão.", "ok")

    def _on_save_scenario(self) -> None:
        try:
            scenario, _ = self._collect()
        except FieldError as exc:
            messagebox.showerror("Input inválido", str(exc))
            return
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
        self.console.write(f"Cenário carregado: {path}", "ok")

    def _on_save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Gravar registo", defaultextension=".txt",
            filetypes=(("Texto", "*.txt"), ("Todos", "*.*")))
        if not path:
            return
        Path(path).write_text(self.console.dump(), encoding="utf-8")
        self.console.write(f"Registo gravado: {path}", "ok")

    # ------------------------------------------------------------------ #
    #  Corrida
    # ------------------------------------------------------------------ #
    def _on_run(self) -> None:
        if self._running:
            return
        try:
            scenario, engine = self._collect()
        except FieldError as exc:
            messagebox.showerror("Input inválido", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Erro", f"{type(exc).__name__}: {exc}")
            return

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
                    self._on_finished(payload)
                    self._set_running(False)
                    return
                elif kind == "error":
                    self.console.write("\nERRO durante o cálculo:", "erro")
                    for line in str(payload).rstrip().splitlines():
                        self.console.write(line, "erro")
                    messagebox.showerror(
                        "Erro durante o cálculo",
                        str(payload).rstrip().splitlines()[-1])
                    self._set_running(False)
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

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.btn_run.configure(state="disabled" if running else "normal",
                               text="A correr…" if running
                               else "▶  Correr dimensionamento")
        self.status.configure(
            text="a correr — pode demorar alguns segundos por motor" if running
            else "pronto")
        self.configure(cursor="watch" if running else "")

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
