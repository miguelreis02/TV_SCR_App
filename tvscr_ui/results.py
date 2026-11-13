"""
Painel de resultados: resumo, tabela do varrimento, grafico e registo.

A consola continua a existir (separador «Registo») e recebe exactamente o
mesmo texto de antes. Os outros separadores mostram os MESMOS numeros de forma
estruturada, para que o resultado do dimensionamento -- o volume critico --
nao tenha de ser procurado no meio do texto:

* **Resumo** -- volume critico em destaque, indicadores do ciclo com o alvo
  ao lado e, havendo varios resultados (todos os motores, ou varios
  substratos), a tabela que os compara; escolher uma linha muda o resultado
  mostrado em todos os separadores.
* **Modos** -- ponto de operacao de cada modo no volume critico.
* **Varrimento** -- uma linha por volume avaliado.
* **Grafico** -- NOx, slip, alfa e ureia contra o volume, desenhados a medida
  do painel (se houver matplotlib).
* **Registo** -- a consola.

Este modulo nao calcula nada: le objectos :class:`tvscr.VolumeSweepResult`.
"""

from __future__ import annotations

import base64
import io
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .theme import C, F
from .widgets import Console, flat_button

__all__ = ["ResultsPanel"]

TABS = [("resumo", "Resumo"), ("modos", "Modos"), ("varrimento", "Varrimento"),
        ("grafico", "Gráfico"), ("registo", "Registo")]

#: (chave, titulo, texto-tipo) das colunas de cada tabela. A largura minima
#: de cada coluna e a do mais largo entre o titulo e o texto-tipo, medida no
#: tipo de letra em uso; as colunas esticam depois ate a largura do painel.
MODE_COLUMNS = [("carga", "Carga [%]", "100"), ("peso", "Peso [%]", "100"),
                ("alpha", "α [–]", "0.000"), ("xno", "X_NO [%]", "100.00"),
                ("no", "NO [g/kWh]", "00.0000"), ("slip", "Slip [ppm]", "000.000"),
                ("urea", "Ureia [L/h]", "0000.00"), ("tau", "τ [s]", "0.000"),
                ("sit", "Situação", "0")]
SWEEP_COLUMNS = [("v", "V [m³]", "00.000"), ("a", "A [m²]", "00.000"),
                 ("estado", "Estado", "inadmissível"), ("sit", "Sit.", "0"),
                 ("nox", "NOx ciclo [g/kWh]", "00.0000"),
                 ("slip", "Slip ciclo [ppm]", "000.000"),
                 ("xno", "X_NO [%]", "100.00"), ("urea", "Ureia [L/h]", "0000.00"),
                 ("nit", "Iter.", "000"), ("fase", "Fase", "refinamento")]
ENGINE_COLUMNS = [("motor", "Motor", "MOTOR-00"), ("v", "V crítico [m³]", "00.000"),
                  ("a", "A [m²]", "00.000"),
                  ("nox", "NOx ciclo [g/kWh]", "00.0000"),
                  ("slip", "Slip ciclo [ppm]", "000.000"),
                  ("xno", "X_NO [%]", "100.00"), ("urea", "Ureia [L/h]", "0000.00")]
SUBSTRATE_COLUMNS = [("motor", "Motor", "MOTOR-00"), ("cpsi", "CPSI", "000"),
                     ("parede", "Parede [mm]", "0.00"),
                     ("v", "V crítico [m³]", "00.000"), ("a", "A [m²]", "00.000"),
                     ("nox", "NOx ciclo [g/kWh]", "00.0000"),
                     ("slip", "Slip ciclo [ppm]", "000.000"),
                     ("urea", "Ureia [L/h]", "0000.00"),
                     ("obs", "Observação", "★ menor volume")]
#: Colunas de texto (alinhadas a esquerda); as restantes sao numericas.
TEXT_COLUMNS = ("motor", "obs", "estado", "fase")

EMPTY_TITLE = "Ainda sem resultados"
EMPTY_STEPS = (
    "1   Indique os dados do motor: ficheiro CSV ou introdução manual.",
    "2   Confirme a geometria, os alvos e o estado do catalisador "
    "(envelhecimento KK0 e fouling).",
    "3   Prima «Correr dimensionamento» (F5). O volume crítico aparece aqui.",
)


@dataclass
class _Item:
    """Um resultado apresentável: um motor, ou um par (motor, substrato)."""

    title: str
    engine: str
    result: Optional[object] = None      # tvscr.VolumeSweepResult
    reason: str = ""
    substrate: Optional[object] = None   # tvscr.SubstrateGeometry
    best: bool = False

    @property
    def ok(self) -> bool:
        return (self.result is not None
                and bool(np.isfinite(self.result.critical_volume_m3)))


# ====================================================================== #
#  Mosaico de um indicador
# ====================================================================== #
class _Tile(tk.Frame):
    """Legenda, valor em destaque e nota (o alvo, por exemplo)."""

    def __init__(self, parent, caption: str, key: bool = False):
        self._normal_bg = C.TILE_KEY_BG if key else C.TILE_BG
        super().__init__(parent, bg=self._normal_bg, highlightthickness=1,
                         highlightbackground=C.TILE_BORDER,
                         highlightcolor=C.TILE_BORDER)
        self._caption = tk.Label(self, text=caption, bg=self._normal_bg,
                                 fg=C.SHEET_DIM, font=F.SMALL_BOLD, anchor="w")
        self._caption.pack(fill="x", padx=12, pady=(8, 0))
        self._value = tk.Label(self, text="—", bg=self._normal_bg, fg=C.BTN_FG,
                               font=F.KPI if key else F.KPI_SMALL, anchor="w",
                               pady=0)
        self._value.pack(fill="x", padx=12)
        self._note = tk.Label(self, text="", bg=self._normal_bg, fg=C.SHEET_DIM,
                              font=F.SMALL, anchor="nw", justify="left",
                              wraplength=200)
        self._note.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.bind("<Configure>", self._wrap, add="+")

    def _wrap(self, event) -> None:
        if event.widget is self:
            self._note.configure(wraplength=max(90, event.width - 28))

    def set(self, value: str, note: str = "", caption: Optional[str] = None,
            error: bool = False) -> None:
        bg = C.TILE_ERR_BG if error else self._normal_bg
        border = C.TILE_ERR_BORDER if error else C.TILE_BORDER
        self.configure(bg=bg, highlightbackground=border, highlightcolor=border)
        for label in (self._caption, self._value, self._note):
            label.configure(bg=bg)
        if caption is not None:
            self._caption.configure(text=caption)
        self._value.configure(text=value, fg=C.LOG_ERR if error else C.BTN_FG)
        self._note.configure(text=note)

    @property
    def value_text(self) -> str:
        return self._value.cget("text")

    @property
    def note_text(self) -> str:
        return self._note.cget("text")

    @property
    def caption_text(self) -> str:
        return self._caption.cget("text")


# ====================================================================== #
#  Painel
# ====================================================================== #
class ResultsPanel(tk.Frame):
    """Separadores de resultados por baixo do formulario."""

    def __init__(self, parent,
                 on_save_log: Optional[Callable[[], None]] = None):
        super().__init__(parent, bg=C.BG)
        self._items: List[_Item] = []
        self._selected: Optional[int] = None
        self._kind = "volume"
        self._plot_image: Optional[tk.PhotoImage] = None
        self._plot_for: Optional[Tuple[int, int, int]] = None
        self._plot_after: Optional[str] = None
        self._log_unread = False

        bar = tk.Frame(self, bg=C.BG)
        bar.pack(fill="x")
        area = tk.Frame(self, bg=C.SHEET_BG, highlightthickness=1,
                        highlightbackground=C.BORDER, highlightcolor=C.BORDER)
        area.pack(fill="both", expand=True)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)

        self._tabs: Dict[str, Tuple[tk.Button, tk.Frame]] = {}
        self._labels = dict(TABS)
        for key, label in TABS:
            button = tk.Button(bar, text=label, relief="flat", bd=0,
                               font=F.BASE, cursor="hand2", padx=16, pady=6,
                               bg=C.TAB_BG, fg=C.TAB_FG, highlightthickness=0,
                               activebackground=C.TAB_HOVER,
                               activeforeground=C.TAB_FG,
                               command=lambda k=key: self.select(k))
            button.pack(side="left", padx=(0, 2))
            page = tk.Frame(area, bg=C.SHEET_BG)
            page.grid(row=0, column=0, sticky="nsew")
            self._tabs[key] = (button, page)
        self._current = "resumo"

        self._build_summary(self._tabs["resumo"][1])
        self._build_modes(self._tabs["modos"][1])
        self._build_sweep(self._tabs["varrimento"][1])
        self._build_plot(self._tabs["grafico"][1])
        self._build_log(self._tabs["registo"][1], on_save_log)
        self.select("resumo")
        self.clear()

    # ------------------------------------------------------------------ #
    #  Separadores
    # ------------------------------------------------------------------ #
    def select(self, key: str) -> None:
        if key not in self._tabs:
            raise KeyError(f"separador desconhecido: {key}")
        self._current = key
        if key == "registo":
            self._log_unread = False
        for other, (button, page) in self._tabs.items():
            active = other == key
            mark = "  •" if (other == "registo" and self._log_unread) else ""
            button.configure(text=self._labels[other] + mark,
                             bg=C.TAB_ACTIVE_BG if active else C.TAB_BG,
                             fg=C.TAB_ACTIVE_FG if active else C.TAB_FG,
                             activebackground=(C.TAB_ACTIVE_BG if active
                                               else C.TAB_HOVER),
                             activeforeground=(C.TAB_ACTIVE_FG if active
                                               else C.TAB_FG),
                             font=F.BOLD if active else F.BASE)
            if active:
                page.tkraise()
        if key == "grafico":
            self.after_idle(self._render_plot)

    @property
    def current(self) -> str:
        return self._current

    @property
    def log_unread(self) -> bool:
        return self._log_unread

    def page(self, key: str) -> tk.Frame:
        return self._tabs[key][1]

    def mark_log_read(self) -> None:
        """Tira a marca de texto novo do separador do registo."""
        self._log_unread = False
        self._tabs["registo"][0].configure(text=self._labels["registo"])

    def _on_log_write(self) -> None:
        """Ha texto novo no registo: assinala o separador se estiver escondido."""
        if self._current != "registo" and not self._log_unread:
            self._log_unread = True
            self._tabs["registo"][0].configure(text=self._labels["registo"] + "  •")

    # ------------------------------------------------------------------ #
    #  Construcao das paginas
    # ------------------------------------------------------------------ #
    @staticmethod
    def _tree(parent, columns: Sequence[Tuple[str, str, str]],
              height: int = 5) -> Tuple[tk.Frame, ttk.Treeview]:
        """Tabela so de leitura, com barra de rolamento vertical."""
        holder = tk.Frame(parent, bg=C.SHEET_BG, highlightthickness=1,
                          highlightbackground=C.TILE_BORDER,
                          highlightcolor=C.TILE_BORDER)
        tree = ttk.Treeview(holder, show="headings", height=height,
                            style="TVSCR.Treeview", selectmode="browse")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview,
                               style="TVSCR.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        ResultsPanel._set_columns(tree, columns)
        tree.tag_configure("critico", background=C.ROW_CRIT)
        tree.tag_configure("falha", foreground=C.LOG_ERR)
        return holder, tree

    @staticmethod
    def _set_columns(tree: ttk.Treeview,
                     columns: Sequence[Tuple[str, str, str]]) -> None:
        tree.configure(columns=[key for key, _t, _s in columns])
        for key, title, sample in columns:
            content = F.BASE.measure(sample) + 18
            width = max(F.BOLD.measure(title) + 22, content)
            anchor = "w" if key in TEXT_COLUMNS else "e"
            tree.heading(key, text=title, anchor=anchor)
            # Num painel estreito as colunas encolhem ate ao conteudo (o titulo
            # pode ficar cortado, os numeros nao).
            tree.column(key, width=width, minwidth=content, anchor=anchor,
                        stretch=True)

    @staticmethod
    def _caption(parent, text: str = "") -> tk.Label:
        return tk.Label(parent, text=text, bg=C.SHEET_BG, fg=C.SHEET_DIM,
                        font=F.SMALL_BOLD, anchor="w")

    def _build_summary(self, page: tk.Frame) -> None:
        page.rowconfigure(0, weight=1)
        page.columnconfigure(0, weight=1)

        # --- estado inicial: como comecar ---
        self._empty = tk.Frame(page, bg=C.SHEET_BG)
        self._empty.grid(row=0, column=0, sticky="nsew")
        block = tk.Frame(self._empty, bg=C.SHEET_BG)
        block.place(relx=0.5, rely=0.45, anchor="center")
        self._empty_title = tk.Label(block, text=EMPTY_TITLE, bg=C.SHEET_BG,
                                     fg=C.BTN_FG, font=F.KPI_SMALL, anchor="w")
        self._empty_title.pack(fill="x", pady=(0, 8))
        self._empty_steps = tk.Label(block, text="\n".join(EMPTY_STEPS),
                                     bg=C.SHEET_BG, fg=C.SHEET_DIM, font=F.BASE,
                                     justify="left", anchor="w")
        self._empty_steps.pack(fill="x")

        # --- resultados ---
        content = tk.Frame(page, bg=C.SHEET_BG, padx=12, pady=10)
        content.grid(row=0, column=0, sticky="nsew")
        self._content = content
        content.columnconfigure(0, weight=1)

        tiles = tk.Frame(content, bg=C.SHEET_BG)
        tiles.grid(row=0, column=0, sticky="ew")
        self.tile_volume = _Tile(tiles, "VOLUME CRÍTICO", key=True)
        self.tile_nox = _Tile(tiles, "NOx DO CICLO")
        self.tile_slip = _Tile(tiles, "NH₃ SLIP DO CICLO")
        self.tile_conv = _Tile(tiles, "CONVERSÃO DE NO")
        self.tile_urea = _Tile(tiles, "CONSUMO DE UREIA")
        for column, (tile, weight) in enumerate((
                (self.tile_volume, 6), (self.tile_nox, 5), (self.tile_slip, 4),
                (self.tile_conv, 4), (self.tile_urea, 4))):
            tile.grid(row=0, column=column, sticky="nsew",
                      padx=(0 if column == 0 else 8, 0))
            tiles.columnconfigure(column, weight=weight, uniform="mosaicos")
        tiles.rowconfigure(0, weight=1)

        # Doseamento por modo, numa linha (o detalhe esta no separador «Modos»).
        self._alpha_line = tk.Label(content, text="", bg=C.SHEET_BG,
                                    fg=C.SHEET_FG, font=F.BASE, anchor="w",
                                    justify="left")
        self._alpha_line.grid(row=1, column=0, sticky="ew", pady=(9, 0))

        # Comparacao de resultados: so aparece quando ha mais do que um.
        compare = tk.Frame(content, bg=C.SHEET_BG)
        compare.grid(row=2, column=0, sticky="nsew", pady=(9, 0))
        compare.rowconfigure(1, weight=1)
        compare.columnconfigure(0, weight=1)
        content.rowconfigure(2, weight=1)
        self._compare = compare
        self._all_caption = self._caption(compare)
        self._all_caption.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        holder, self.items_tree = self._tree(compare, ENGINE_COLUMNS, height=3)
        holder.grid(row=1, column=0, sticky="nsew")
        self.items_tree.bind("<<TreeviewSelect>>", self._on_item_picked)

    def _build_modes(self, page: tk.Frame) -> None:
        page.configure(padx=12, pady=10)
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        self._modes_caption = self._caption(page)
        self._modes_caption.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        holder, self.modes_tree = self._tree(page, MODE_COLUMNS, height=4)
        holder.grid(row=1, column=0, sticky="nsew")

    def _build_sweep(self, page: tk.Frame) -> None:
        page.configure(padx=12, pady=10)
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        self._sweep_caption = self._caption(page)
        self._sweep_caption.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        holder, self.sweep_tree = self._tree(page, SWEEP_COLUMNS, height=6)
        holder.grid(row=1, column=0, sticky="nsew")

    def _build_plot(self, page: tk.Frame) -> None:
        page.rowconfigure(0, weight=1)
        page.columnconfigure(0, weight=1)
        self._plot_canvas = tk.Canvas(page, bg=C.SHEET_BG, highlightthickness=0)
        self._plot_canvas.grid(row=0, column=0, sticky="nsew")
        self._plot_message = self._plot_canvas.create_text(
            16, 14, anchor="nw", fill=C.SHEET_DIM, font=F.BASE, text="")
        self._plot_item = self._plot_canvas.create_image(0, 0, anchor="nw")
        # O grafico e desenhado a medida do painel: redesenhar quando este muda
        # de tamanho (com um pequeno atraso, para nao o fazer a cada pixel).
        self._plot_canvas.bind("<Configure>", self._on_plot_resize)

    def _on_plot_resize(self, _event=None) -> None:
        if self._plot_after is not None:
            self.after_cancel(self._plot_after)
        self._plot_after = self.after(220, self._render_plot)

    def _build_log(self, page: tk.Frame,
                   on_save_log: Optional[Callable[[], None]]) -> None:
        self.console = Console(page, height=8)
        tools = tk.Frame(page, bg=C.SHEET_BG)
        tools.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(tools, text="Registo do cálculo: a mesma tabela que os scripts "
                             "MATLAB imprimiam.", bg=C.SHEET_BG, fg=C.SHEET_DIM,
                 font=F.SMALL, anchor="w").pack(side="left")
        clear = flat_button(tools, "Limpar", self.console.clear, small=True)
        clear.configure(bg=C.BTN_ACTIVE)
        clear.pack(side="right")
        if on_save_log is not None:
            save = flat_button(tools, "Gravar registo…", on_save_log, small=True)
            save.configure(bg=C.BTN_ACTIVE)
            save.pack(side="right", padx=(0, 6))
        self.console.pack(fill="both", expand=True)
        self.console.on_write = self._on_log_write

    # ------------------------------------------------------------------ #
    #  Conteudo
    # ------------------------------------------------------------------ #
    @property
    def has_results(self) -> bool:
        return bool(self._items)

    @property
    def selected_title(self) -> Optional[str]:
        if self._selected is None:
            return None
        return self._items[self._selected].title

    def clear(self, title: str = EMPTY_TITLE,
              steps: Optional[Sequence[str]] = EMPTY_STEPS) -> None:
        """Volta ao estado sem resultados (a consola nao e tocada)."""
        self._items = []
        self._selected = None
        self._plot_for = None
        self._plot_image = None
        self._plot_canvas.itemconfigure(self._plot_item, image="")
        self._plot_canvas.itemconfigure(
            self._plot_message, text="Sem resultados para representar.")
        self._alpha_line.configure(text="")
        self._modes_caption.configure(text="Sem resultados.")
        self._empty_title.configure(text=title)
        self._empty_steps.configure(text="\n".join(steps or ()))
        for tree in (self.modes_tree, self.items_tree, self.sweep_tree):
            tree.delete(*tree.get_children())
        self._sweep_caption.configure(text="Sem resultados.")
        self._empty.tkraise()

    def show_volume(self, results: Sequence) -> None:
        """Mostra os varrimentos em volume (um por motor)."""
        self._kind = "volume"
        self._show([_Item(title=r.engine, engine=r.engine, result=r,
                          reason=(r.why[0] if getattr(r, "why", None) else ""))
                    for r in results])

    def show_substrates(self, sweep) -> None:
        """Mostra a comparacao de pares CPSI / parede."""
        self._kind = "substratos"
        best = {id(sweep.best_for(engine)) for engine in sweep.engines}
        items = []
        for row in sweep.rows:
            s = row.substrate
            items.append(_Item(
                title=(f"{row.engine} · CPSI {s.cpsi:g} / "
                       f"{s.wall_thickness_m * 1e3:g} mm"),
                engine=row.engine, result=row.result, reason=row.reason,
                substrate=s, best=id(row) in best))
        self._show(items)

    def _show(self, items: List[_Item]) -> None:
        self.clear()
        self._items = items
        if not items:
            return

        columns = SUBSTRATE_COLUMNS if self._kind == "substratos" else ENGINE_COLUMNS
        self._set_columns(self.items_tree, columns)
        for index, item in enumerate(items):
            tags = ("critico",) if item.best else (() if item.ok else ("falha",))
            self.items_tree.insert("", "end", iid=str(index),
                                   values=self._item_values(item), tags=tags)

        several = len(items) > 1
        if several:
            self._all_caption.configure(
                text=("COMPARAÇÃO DE SUBSTRATOS  ·  o menor volume crítico de "
                      "cada motor está realçado  ·  escolha uma linha para ver "
                      "o detalhe" if self._kind == "substratos"
                      else "TODOS OS MOTORES  ·  escolha uma linha para ver o "
                           "detalhe desse motor nos outros separadores"))
            # Com varios resultados a altura vai para a tabela que os compara;
            # o alfa por modo de cada um esta no separador «Modos».
            self._alpha_line.grid_remove()
            self._compare.grid()
        else:
            self._compare.grid_remove()
            self._alpha_line.grid()

        first = next((i for i, item in enumerate(items) if item.best),
                     next((i for i, item in enumerate(items) if item.ok), 0))
        self._content.tkraise()
        self._select_item(first)
        if several:
            self.items_tree.selection_set(str(first))
            self.items_tree.see(str(first))

    def _item_values(self, item: _Item) -> List[str]:
        r = item.result
        if item.ok:
            crit = r.at_critical()
            numbers = [f"{r.critical_volume_m3:.3f}", f"{r.critical_area_m2:.3f}",
                       f"{crit['NOx_ciclo_gkWh']:.4f}",
                       f"{crit['slip_ciclo_ppm']:.3f}",
                       f"{crit['XNO_ciclo_perc']:.2f}",
                       f"{crit['urea_ciclo_Lh']:.2f}"]
        else:
            numbers = ["—"] * 6
        if self._kind != "substratos":
            return [item.engine] + numbers
        del numbers[4]                    # sem X_NO: a tabela ja e larga
        s = item.substrate
        note = ("★ menor volume" if item.best else
                "" if item.ok else (item.reason or "sem volume admissível"))
        return ([item.engine, f"{s.cpsi:g}", f"{s.wall_thickness_m * 1e3:g}"]
                + numbers + [note])

    def _on_item_picked(self, _event=None) -> None:
        picked = self.items_tree.selection()
        if picked and int(picked[0]) != self._selected:
            self._select_item(int(picked[0]))

    # ------------------------------------------------------------------ #
    def _select_item(self, index: int) -> None:
        """Preenche mosaicos, modos, varrimento e grafico com um resultado."""
        self._selected = index
        item = self._items[index]
        r = item.result
        self._fill_tiles(item)
        self._fill_modes(item)
        self._fill_sweep(item)
        self._plot_for = None
        if r is None:
            self._plot_canvas.itemconfigure(self._plot_item, image="")
            self._plot_canvas.itemconfigure(
                self._plot_message, text="Sem varrimento para representar.")
        if self._current == "grafico":
            self.after_idle(self._render_plot)

    def _fill_tiles(self, item: _Item) -> None:
        r = item.result
        caption = f"VOLUME CRÍTICO — {item.engine}"
        s = item.substrate
        substrate = ("" if s is None else
                     f"CPSI {s.cpsi:g} / {s.wall_thickness_m * 1e3:g} mm   ·   ")
        if not item.ok:
            if r is None:
                note = substrate + (item.reason or "Sem resultado para este par.")
            else:
                note = (f"{substrate}Nem o maior volume considerado "
                        f"({r.volume_max_m3:.2f} m³) cumpre os alvos. Suba o "
                        "«Volume máximo», alivie os alvos, ou reduza o fouling "
                        "/ envelhecimento.")
            self.tile_volume.set("Sem solução", note, caption=caption,
                                 error=True)
            for tile in (self.tile_nox, self.tile_slip, self.tile_conv,
                         self.tile_urea):
                tile.set("—", "")
            self._alpha_line.configure(
                text="" if r is None else
                "O separador «Modos» mostra que modo falha no maior volume "
                "avaliado (situação 4: NO e slip acima do alvo ao mesmo α)."
                + (f"\nMotivo: {item.reason}" if item.reason else ""))
            return

        crit = r.at_critical()
        t = r.targets
        self.tile_volume.set(
            f"{r.critical_volume_m3:.3f} m³",
            f"{substrate}A = {r.critical_area_m2:.3f} m²   ·   "
            f"L = {r.length_m:.2f} m", caption=caption)
        self.tile_nox.set(
            f"{crit['NOx_ciclo_gkWh']:.4f} g/kWh",
            f"alvo ≤ {t.cycle_NO_gkWh:.4f}  "
            f"({t.cycle_NO_frac * 100:.0f} % do limite)")
        self.tile_slip.set(
            f"{crit['slip_ciclo_ppm']:.3f} ppm",
            f"alvo ≤ {t.cycle_slip_ppm:g} ppm")
        self.tile_conv.set(f"{crit['XNO_ciclo_perc']:.2f} %", "ciclo ponderado")
        self.tile_urea.set(f"{crit['urea_ciclo_Lh']:.2f} L/h", "ciclo ponderado")
        self._alpha_line.configure(
            text="α por modo (carga → α):   " + "   ·   ".join(
                f"{load:g} % → {alpha:.3f}"
                for load, alpha in zip(r.load_pct, crit["alpha"])))

    def _fill_modes(self, item: _Item) -> None:
        tree = self.modes_tree
        tree.delete(*tree.get_children())
        r = item.result
        if r is None or r.volume_m3.size == 0:
            self._modes_caption.configure(
                text=f"{item.title} — sem varrimento: {item.reason}")
            return
        if item.ok:
            j = r.critical_index
            where = "NO VOLUME CRÍTICO"
        else:
            j = int(np.argmax(r.volume_m3))
            where = f"NO MAIOR VOLUME AVALIADO ({r.volume_m3[j]:.2f} m³)"
        t = r.targets
        self._modes_caption.configure(
            text=f"{item.title} — PONTO DE OPERAÇÃO POR MODO, {where}  ·  alvos "
                 f"por modo: NO ≤ {t.mode_NO_gkWh:.4f} g/kWh, slip ≤ "
                 f"{t.mode_slip_ppm:g} ppm")
        for m, load in enumerate(r.load_pct):
            situation = int(r.sit_mode[j, m])
            tree.insert("", "end", values=(
                f"{load:g}", f"{r.weight[m]:g}", f"{r.alpha[j, m]:.3f}",
                f"{r.X_NO[j, m]:.2f}", f"{r.NO_gkWh[j, m]:.4f}",
                f"{r.slip_ppm[j, m]:.3f}", f"{r.urea_Lh[j, m]:.2f}",
                f"{r.tau_s[j, m]:.3f}", situation),
                tags=("falha",) if situation == 4 else ())

    def _fill_sweep(self, item: _Item) -> None:
        tree = self.sweep_tree
        tree.delete(*tree.get_children())
        r = item.result
        if r is None:
            self._sweep_caption.configure(
                text=f"{item.title} — sem varrimento: {item.reason}")
            return
        self._sweep_caption.configure(
            text=f"{item.title} — UMA LINHA POR VOLUME AVALIADO  ·  o volume "
                 f"crítico está realçado  ·  Sit. (situação) 1 = alvos "
                 f"cumpridos, 4 = janela de α vazia  ·  Iter. = iterações do "
                 f"loop de α")
        critical = r.critical_index
        for j in np.argsort(-r.volume_m3, kind="stable"):
            j = int(j)
            ok = bool(r.ok[j])
            tags = (("critico",) if j == critical else () if ok else ("falha",))
            tree.insert("", "end", tags=tags, values=(
                f"{r.volume_m3[j]:.3f}", f"{r.area_m2[j]:.3f}",
                ("★ crítico" if j == critical else
                 "admissível" if ok else "inadmissível"),
                int(r.situation[j]), f"{r.NO_cycle[j]:.4f}",
                f"{r.slip_cycle[j]:.3f}", f"{r.XNO_cycle[j]:.2f}",
                f"{r.urea_cycle[j]:.2f}", int(r.n_iter[j]),
                "refinamento" if int(r.phase[j]) == 2 else "varrimento"))

    # ------------------------------------------------------------------ #
    #  Grafico
    # ------------------------------------------------------------------ #
    def _render_plot(self) -> None:
        """Desenha o grafico do resultado escolhido, a medida do painel.

        So trabalha quando o separador esta a vista e algo mudou (o resultado
        escolhido ou o tamanho do painel).
        """
        self._plot_after = None
        if self._current != "grafico" or self._selected is None:
            return
        item = self._items[self._selected]
        if item.result is None:
            return
        canvas = self._plot_canvas
        width = max(620, canvas.winfo_width())
        height = max(190, canvas.winfo_height())
        wanted = (self._selected, width, height)
        if self._plot_for == wanted:
            return
        self._plot_for = wanted
        try:
            png = _figure_png(item.result, width, height)
            problem = ("O gráfico precisa do matplotlib, que não está instalado "
                       "(pip install matplotlib).")
        except Exception as exc:          # um grafico falhado nao pode parar a janela
            png = None
            problem = f"Não foi possível desenhar o gráfico: {exc}"
        if png is None:
            canvas.itemconfigure(self._plot_item, image="")
            canvas.itemconfigure(self._plot_message, text=problem)
            return
        self._plot_image = tk.PhotoImage(data=base64.b64encode(png))
        canvas.itemconfigure(self._plot_message, text="")
        canvas.itemconfigure(self._plot_item, image=self._plot_image)


def _figure_png(result, width_px: int, height_px: int) -> Optional[bytes]:
    """PNG com NOx, slip, alfa e ureia contra o volume; ``None`` sem matplotlib.

    Sao os quatro graficos de :func:`tvscr.plotting.plot_volume_sweep`, mas
    dispostos para o painel: numa linha quando este e baixo, em 2x2 quando ha
    altura. Usa a API de objectos do matplotlib (sem ``pyplot``), por isso nao
    mexe no backend nem no estado global usados para gravar as figuras.
    """
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
    except ImportError:
        return None

    dpi = 100.0
    figure = Figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi,
                    facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    grid = (2, 2) if height_px >= 440 else (1, 4)
    ax_nox, ax_slip, ax_alpha, ax_urea = figure.subplots(*grid).ravel()

    order = np.argsort(result.volume_m3)
    volume = result.volume_m3[order]
    ok = result.ok[order].astype(bool)
    green, red, grey = C.LOG_OK, C.LOG_ERR, "#5F6B64"
    critical = (result.critical_volume_m3
                if np.isfinite(result.critical_volume_m3) else None)

    def series(ax, values, marker):
        values = values[order]
        ax.plot(volume[ok], values[ok], marker + "-", color=green, lw=1.4,
                ms=4, label="admissível")
        if (~ok).any():
            ax.plot(volume[~ok], values[~ok], "x", color=red, ms=7, mew=1.6,
                    label="inadmissível")
        if critical is not None:
            j = int(np.argmin(np.abs(volume - critical)))
            ax.plot(volume[j], values[j], "*", ms=11, mfc=C.ACCENT, mec="k",
                    mew=0.6, label="volume crítico", zorder=5)

    series(ax_nox, result.NO_cycle, "o")
    ax_nox.axhline(result.targets.cycle_NO_gkWh, ls="--", color=red, lw=1.1,
                   label="alvo")
    ax_nox.axhline(result.nox_limit_gkWh, ls=":", color=grey, lw=1.1,
                   label="limite")
    ax_nox.set_title("NOx do ciclo [g/kWh]")
    ax_nox.legend(fontsize=7, loc="best", framealpha=0.9)

    series(ax_slip, np.maximum(result.slip_cycle, 1e-3), "s")
    ax_slip.axhline(result.targets.cycle_slip_ppm, ls="--", color=red, lw=1.1)
    ax_slip.set_yscale("log")
    ax_slip.set_title("NH$_3$ slip do ciclo [ppm]")

    for m, load in enumerate(result.load_pct):
        ax_alpha.plot(volume, result.alpha[order, m], "o-", lw=1.2, ms=3,
                      label=f"{load:g} %")
    ax_alpha.set_title(r"$\alpha$ por modo [–]")
    ax_alpha.legend(fontsize=7, loc="best", framealpha=0.9, title="carga",
                    title_fontsize=7)

    ax_urea.plot(volume, result.urea_cycle[order], "d-", color=green, lw=1.4,
                 ms=4)
    ax_urea.set_title("Ureia no ciclo [L/h]")

    for ax in (ax_nox, ax_slip, ax_alpha, ax_urea):
        if critical is not None:
            ax.axvline(critical, ls="-.", lw=1.0, color=grey)
        ax.set_xlabel("V [m³]", fontsize=8)
        ax.title.set_fontsize(9)
        ax.title.set_fontweight("bold")
        ax.tick_params(labelsize=8)
        ax.grid(True, which="both", alpha=0.25)

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi)
    return buffer.getvalue()
