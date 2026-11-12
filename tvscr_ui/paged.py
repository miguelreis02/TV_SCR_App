"""
Separadores (paginas escondidas), botoes de opcao e tabela editavel.

``PagedForm`` substitui o formulario de tres colunas: cada seccao de inputs
passa a ser uma pagina, escondida ate ser escolhida no separador respectivo.

``RadioGroup`` desenha o proprio indicador -- circulo branco com ponto preto
quando escolhido -- porque o ``tk.Radiobutton`` nativo pinta o interior todo
com uma so cor e, sobre verde, fica ilegivel.

``EditableTable`` e a grelha de introducao manual. Cabecalho e celulas vivem
na MESMA grelha, para que as colunas fiquem alinhadas por construcao.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .theme import C, F
from .widgets import FieldError, Tooltip

__all__ = ["PagedForm", "Column", "EditableTable", "ModeTable", "RadioGroup"]


# ====================================================================== #
#  Separadores
# ====================================================================== #
class PagedForm(tk.Frame):
    """Barra de separadores + area de paginas, uma visivel de cada vez."""

    def __init__(self, parent):
        super().__init__(parent, bg=C.BG)
        self.tabs = tk.Frame(self, bg=C.BG)
        self.tabs.pack(fill="x")
        self.area = tk.Frame(self, bg=C.BG_PANEL, highlightbackground=C.BORDER,
                             highlightthickness=1)
        self.area.pack(fill="both", expand=True)
        self.area.rowconfigure(0, weight=1)
        self.area.columnconfigure(0, weight=1)

        self._pages: Dict[str, Tuple[tk.Button, tk.Frame]] = {}
        self._order: List[str] = []
        self._current: Optional[str] = None
        self._on_change: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------ #
    def add_page(self, key: str, label: str, tooltip: str = "") -> tk.Frame:
        """Cria uma pagina e o seu separador; devolve o frame da pagina."""
        button = tk.Button(self.tabs, text=label, relief="flat", bd=0,
                           font=F.BASE, cursor="hand2", padx=13, pady=6,
                           bg=C.TAB_BG, fg=C.TAB_FG,
                           activebackground=C.TAB_HOVER, activeforeground=C.TAB_FG,
                           command=lambda k=key: self.select(k))
        button.pack(side="left", padx=(0, 2))
        if tooltip:
            Tooltip(button, tooltip)

        page = tk.Frame(self.area, bg=C.BG_PANEL, padx=12, pady=10)
        page.grid(row=0, column=0, sticky="nsew")

        self._pages[key] = (button, page)
        self._order.append(key)
        if self._current is None:
            self.select(key)
        else:
            # As paginas estao empilhadas na mesma celula: a que acaba de ser
            # criada fica por cima. Devolver o lugar a pagina activa, senao a
            # ultima criada aparecia sob o separador da primeira.
            self._pages[self._current][1].tkraise()
        return page

    def select(self, key: str) -> None:
        if key not in self._pages:
            raise KeyError(f"pagina desconhecida: {key}")
        for other, (button, page) in self._pages.items():
            active = other == key
            button.configure(bg=C.TAB_ACTIVE_BG if active else C.TAB_BG,
                             fg=C.TAB_ACTIVE_FG if active else C.TAB_FG,
                             font=F.BOLD if active else F.BASE)
            if active:
                page.tkraise()
        self._current = key
        if self._on_change:
            self._on_change(key)

    @property
    def current(self) -> Optional[str]:
        return self._current

    @property
    def keys(self) -> List[str]:
        return list(self._order)

    def on_change(self, callback: Callable[[str], None]) -> None:
        self._on_change = callback

    def page(self, key: str) -> tk.Frame:
        return self._pages[key][1]


# ====================================================================== #
#  Botoes de opcao com indicador desenhado
# ====================================================================== #
class RadioGroup(tk.Frame):
    """Opcoes exclusivas com indicador proprio: circulo branco, ponto preto.

    O ``tk.Radiobutton`` nativo pinta o indicador inteiro com ``selectcolor``,
    o que sobre fundo verde nao se distingue. Aqui o indicador e desenhado num
    pequeno ``Canvas``, com o mesmo aspecto em qualquer plataforma.
    """

    SIZE = 15
    DOT = "#10281A"

    def __init__(self, parent, variable: tk.StringVar,
                 options: Sequence[Tuple[str, str]],
                 command: Optional[Callable[[], None]] = None,
                 bg: str = C.BG_PANEL, gap: int = 16):
        super().__init__(parent, bg=bg)
        self.variable = variable
        self.command = command
        self._indicators: Dict[str, tk.Canvas] = {}

        for index, (value, label) in enumerate(options):
            holder = tk.Frame(self, bg=bg, cursor="hand2")
            holder.pack(side="left", padx=(0 if index == 0 else gap, 0))

            canvas = tk.Canvas(holder, width=self.SIZE, height=self.SIZE, bg=bg,
                               highlightthickness=0, bd=0, cursor="hand2")
            canvas.pack(side="left")
            text = tk.Label(holder, text=label, bg=bg, fg=C.TEXT, font=F.BASE,
                            cursor="hand2")
            text.pack(side="left", padx=(6, 0))

            for widget in (holder, canvas, text):
                widget.bind("<Button-1>", lambda _e, v=value: self._pick(v))

            self._indicators[value] = canvas

        variable.trace_add("write", lambda *_a: self._redraw())
        self._redraw()

    def _pick(self, value: str) -> None:
        if self.variable.get() != value:
            self.variable.set(value)
        if self.command:
            self.command()

    def _redraw(self) -> None:
        current = self.variable.get()
        for value, canvas in self._indicators.items():
            canvas.delete("all")
            canvas.create_oval(1, 1, self.SIZE - 2, self.SIZE - 2,
                               fill=C.FIELD_BG, outline=C.BORDER, width=1)
            if value == current:
                canvas.create_oval(5, 5, self.SIZE - 6, self.SIZE - 6,
                                   fill=self.DOT, outline=self.DOT)


# ====================================================================== #
#  Tabela editavel
# ====================================================================== #
class Column:
    """Definicao de uma coluna da :class:`EditableTable`."""

    def __init__(self, key: str, label: str, unit: str = "", width: int = 9,
                 required: bool = True, tooltip: str = ""):
        self.key = key
        self.label = label
        self.unit = unit
        self.width = width
        self.required = required
        self.tooltip = tooltip


class EditableTable(tk.Frame):
    """Grelha de campos brancos, uma linha por registo.

    Cabecalho (nome + unidade) e celulas partilham a MESMA grelha, para as
    colunas ficarem alinhadas sem depender das larguras em caracteres de duas
    fontes diferentes.

    ``rows()`` devolve uma lista de dicionarios ja validada; as celulas em
    falta ou invalidas ficam assinaladas, e a mensagem de erro diz o numero da
    linha e o nome da coluna. Linhas completamente vazias sao ignoradas.
    """

    #: Como se chama uma linha nas mensagens de erro ("Modo 3", "Substrato 2").
    ROW_NOUN = "Linha"

    def __init__(self, parent, columns: Sequence[Column], initial_rows: int = 4,
                 row_noun: Optional[str] = None):
        super().__init__(parent, bg=C.BG_PANEL)
        self.columns = list(columns)
        self.row_noun = row_noun or self.ROW_NOUN
        self._rows: List[Tuple[List[tk.Widget],
                               Dict[str, Tuple[tk.StringVar, tk.Entry]]]] = []
        self._first_data_row = 2

        tk.Label(self, text="#", bg=C.BG_PANEL, fg=C.TEXT_DIM, font=F.SMALL,
                 width=3).grid(row=0, column=0, rowspan=2, padx=(0, 4))
        for i, col in enumerate(self.columns):
            name = tk.Label(self, text=col.label, bg=C.BG_PANEL, fg=C.TEXT,
                            font=F.BOLD)
            name.grid(row=0, column=i + 1, padx=2, sticky="ew")
            tk.Label(self, text=col.unit or "–", bg=C.BG_PANEL, fg=C.TEXT_DIM,
                     font=F.SMALL).grid(row=1, column=i + 1, padx=2, sticky="ew")
            if col.tooltip:
                Tooltip(name, col.tooltip)

        for _ in range(initial_rows):
            self.add_row()

    # ------------------------------------------------------------------ #
    @property
    def n_rows(self) -> int:
        return len(self._rows)

    def add_row(self, values: Optional[dict] = None) -> None:
        index = len(self._rows)
        grid_row = self._first_data_row + index

        widgets: List[tk.Widget] = []
        number = tk.Label(self, text=str(index + 1), bg=C.BG_PANEL,
                          fg=C.TEXT_DIM, font=F.SMALL, width=3)
        number.grid(row=grid_row, column=0, padx=(0, 4))
        widgets.append(number)

        cells: Dict[str, Tuple[tk.StringVar, tk.Entry]] = {}
        for i, col in enumerate(self.columns):
            var = tk.StringVar()
            if values is not None and values.get(col.key) is not None:
                raw = values[col.key]
                # .12g e nao .6g: copiar de um ficheiro nao pode perder digitos,
                # senao o caminho manual deixa de reproduzir o do ficheiro.
                var.set(f"{raw:.12g}" if isinstance(raw, (int, float)) else str(raw))
            entry = tk.Entry(self, textvariable=var, width=col.width,
                             bg=C.FIELD_BG, fg=C.FIELD_FG, font=F.BASE,
                             relief="flat", justify="right",
                             insertbackground=C.FIELD_FG, highlightthickness=1,
                             highlightbackground=C.BORDER, highlightcolor=C.RUN_BG)
            entry.grid(row=grid_row, column=i + 1, padx=2, pady=1, sticky="ew")
            var.trace_add("write", lambda *_a, w=entry: w.configure(bg=C.FIELD_BG))
            cells[col.key] = (var, entry)
            widgets.append(entry)

        self._rows.append((widgets, cells))

    def remove_last_row(self) -> None:
        if len(self._rows) <= 1:
            return
        widgets, _cells = self._rows.pop()
        for widget in widgets:
            widget.destroy()

    def set_rows(self, records: Sequence[dict]) -> None:
        """Substitui todo o conteudo pelos registos dados."""
        while self._rows:
            widgets, _cells = self._rows.pop()
            for widget in widgets:
                widget.destroy()
        for record in records:
            self.add_row(record)
        if not self._rows:
            self.add_row()

    def clear(self, rows: int = 4) -> None:
        self.set_rows([{} for _ in range(rows)])

    def is_blank(self) -> bool:
        """``True`` se nenhuma celula tiver conteudo."""
        return all(not var.get().strip()
                   for _w, cells in self._rows for var, _e in cells.values())

    def rows(self, allow_empty: bool = False) -> List[dict]:
        """Valida e devolve as linhas. Levanta :class:`FieldError` com contexto."""
        out: List[dict] = []
        for index, (_widgets, cells) in enumerate(self._rows, start=1):
            if all(not var.get().strip() for var, _e in cells.values()):
                continue                                  # linha vazia: ignorada
            record: dict = {}
            for col in self.columns:
                var, entry = cells[col.key]
                raw = var.get().strip().replace(",", ".")
                if not raw:
                    if col.required:
                        entry.configure(bg=C.ERROR_FIELD)
                        raise FieldError(
                            f'{self.row_noun} {index}: "{col.label}" não pode '
                            f"ficar em branco.")
                    record[col.key] = None
                    continue
                try:
                    record[col.key] = float(raw)
                except ValueError:
                    entry.configure(bg=C.ERROR_FIELD)
                    raise FieldError(
                        f'{self.row_noun} {index}, "{col.label}": '
                        f'"{var.get().strip()}" não é um número.')
            out.append(record)
        if not out and not allow_empty:
            raise FieldError(f"Introduza pelo menos uma linha "
                             f"({self.row_noun.lower()} 1).")
        return out


class ModeTable(EditableTable):
    """Tabela dos modos do ciclo de ensaio."""

    ROW_NOUN = "Modo"
