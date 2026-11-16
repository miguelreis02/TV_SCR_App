"""
Separadores (paginas escondidas), botoes de opcao e tabela editavel.

``PagedForm`` substitui o formulario de tres colunas: cada seccao de inputs
passa a ser uma pagina, escondida ate ser escolhida no separador respectivo.
Os separadores sao verticais e agrupados, para caberem numa barra lateral.

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
from .widgets import FieldError, Tooltip, ghost_button

__all__ = ["PagedForm", "NavLink", "Column", "EditableTable", "ModeTable",
           "RadioGroup"]


# ====================================================================== #
#  Separadores
# ====================================================================== #
class PagedForm(tk.Frame):
    """Separadores verticais agrupados + area de paginas, uma visivel de cada vez.

    Os separadores vivem em ``self.tabs``. Por omissao ficam a esquerda das
    paginas; com ``nav_parent`` sao criados dentro de outro contentor (a barra
    lateral da janela), que os posiciona.

    Por cima das paginas ha um cabecalho com o titulo e a descricao da pagina
    activa, e os botoes «Anterior» / «Seguinte» para percorrer as paginas pela
    ordem em que foram criadas.

    So a pagina activa ocupa espaco: as outras sao retiradas da grelha. Assim
    a altura do formulario e a da pagina que se esta a ver, e uma pagina alta
    (a tabela de modos, por exemplo) nao obriga as outras a rolar.
    """

    HEAD_GAP = 12

    def __init__(self, parent, nav_parent=None):
        super().__init__(parent, bg=C.BG)
        own_nav = nav_parent is None
        self.tabs = tk.Frame(self if own_nav else nav_parent, bg=C.NAV_BG)
        if own_nav:
            self.tabs.pack(side="left", fill="y", padx=(0, 12))

        body = tk.Frame(self, bg=C.BG)
        body.pack(side="left", fill="both", expand=True)

        # --- cabecalho da pagina ---
        head = tk.Frame(body, bg=C.BG)
        head.pack(fill="x", pady=(0, self.HEAD_GAP))
        self._head = head
        steps = tk.Frame(head, bg=C.BG)
        steps.pack(side="right", anchor="s")
        self.btn_prev = ghost_button(steps, "◀  Anterior", self.select_previous)
        self.btn_prev.pack(side="left")
        self._counter = tk.Label(steps, text="", bg=C.BG, fg=C.TEXT_DIM,
                                 font=F.BASE, width=7)
        self._counter.pack(side="left")
        self.btn_next = ghost_button(steps, "Seguinte  ▶", self.select_next)
        self.btn_next.pack(side="left")

        text = tk.Frame(head, bg=C.BG)
        text.pack(side="left", fill="x", expand=True)
        self._title = tk.Label(text, text="", bg=C.BG, fg=C.TITLE,
                               font=F.PAGE_TITLE, anchor="w")
        self._title.pack(fill="x")
        self._subtitle = tk.Label(text, text="", bg=C.BG, fg=C.TEXT_DIM,
                                  font=F.BASE, anchor="w")
        self._subtitle.pack(fill="x")

        # --- paginas, empilhadas na mesma celula ---
        self.area = tk.Frame(body, bg=C.BG)
        self.area.pack(fill="both", expand=True)
        self.area.rowconfigure(0, weight=1)
        self.area.columnconfigure(0, weight=1)

        self._pages: Dict[str, _Tab] = {}
        self._order: List[str] = []
        self._current: Optional[str] = None
        self._highlight = True
        self._group_labels: List[tk.Label] = []      # titulos de grupo, menos o 1.o
        self._on_change: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------ #
    def add_group(self, title: str) -> None:
        """Titulo de um grupo de separadores (os que forem criados a seguir)."""
        first = not self.tabs.winfo_children()
        label = tk.Label(self.tabs, text=title, bg=C.NAV_BG, fg=C.NAV_GROUP,
                         font=F.SMALL_BOLD, anchor="w", padx=16)
        label.pack(fill="x", pady=(4 if first else 14, 3))
        if not first:
            self._group_labels.append(label)

    def add_page(self, key: str, label: str, tooltip: str = "") -> tk.Frame:
        """Cria uma pagina e o seu separador; devolve o frame da pagina.

        ``tooltip`` e a descricao curta da pagina: aparece por baixo do titulo
        quando a pagina esta aberta e ao passar o rato sobre o separador.
        """
        row = tk.Frame(self.tabs, bg=C.NAV_BG)
        row.pack(fill="x")
        accent = tk.Frame(row, bg=C.NAV_BG, width=4)
        accent.pack(side="left", fill="y")
        flag = tk.Label(row, text="", bg=C.NAV_BG, fg=C.FLAG, font=F.BOLD,
                        width=2)
        flag.pack(side="right")
        button = tk.Button(row, text=label, relief="flat", bd=0, anchor="w",
                           font=F.BASE, cursor="hand2", padx=12, pady=6,
                           bg=C.NAV_BG, fg=C.NAV_FG, highlightthickness=0,
                           activebackground=C.NAV_ACTIVE_BG,
                           activeforeground=C.NAV_ACTIVE_FG,
                           command=lambda k=key: self.select(k))
        button.pack(side="left", fill="x", expand=True)
        if tooltip:
            Tooltip(button, tooltip, delay_ms=700)

        page = tk.Frame(self.area, bg=C.BG)
        page.grid(row=0, column=0, sticky="nsew")

        tab = _Tab(key, label, tooltip, row, accent, button, flag, page)
        self._pages[key] = tab
        self._order.append(key)
        for widget in (row, button, flag):
            widget.bind("<Enter>", lambda _e, t=tab: self._paint(t, hover=True),
                        add="+")
            widget.bind("<Leave>", lambda _e, t=tab: self._paint(t), add="+")

        if self._current is None:
            self.select(key)
        else:
            # A pagina acabada de criar fica por cima e na grelha: devolver o
            # lugar a pagina activa, senao a ultima criada aparecia sob o
            # separador da primeira.
            page.grid_remove()
            self._pages[self._current].page.tkraise()
            self._refresh_steps()
        return page

    def _paint(self, tab: "_Tab", hover: bool = False) -> None:
        active = tab.key == self._current and self._highlight
        bg = (C.NAV_ACTIVE_BG if active else C.NAV_HOVER if hover else C.NAV_BG)
        tab.row.configure(bg=bg)
        tab.flag.configure(bg=bg)
        tab.accent.configure(bg=C.ACCENT if active else bg)
        tab.button.configure(bg=bg,
                             fg=C.NAV_ACTIVE_FG if active else C.NAV_FG,
                             font=F.BOLD if active else F.BASE)

    def _refresh_steps(self) -> None:
        index = self._order.index(self._current)
        self._counter.configure(text=f"{index + 1} / {len(self._order)}")
        self.btn_prev.configure(state="normal" if index > 0 else "disabled")
        self.btn_next.configure(
            state="normal" if index < len(self._order) - 1 else "disabled")

    def select(self, key: str) -> None:
        if key not in self._pages:
            raise KeyError(f"pagina desconhecida: {key}")
        self._current = key
        self._highlight = True
        for tab in self._pages.values():
            self._paint(tab)
            if tab.key != key:
                tab.page.grid_remove()
        tab = self._pages[key]
        tab.page.grid()
        tab.page.tkraise()
        self._title.configure(text=tab.label)
        self._subtitle.configure(text=tab.description)
        self._refresh_steps()
        if self._on_change:
            self._on_change(key)

    def select_next(self) -> None:
        index = self._order.index(self._current)
        if index < len(self._order) - 1:
            self.select(self._order[index + 1])

    def select_previous(self) -> None:
        index = self._order.index(self._current)
        if index > 0:
            self.select(self._order[index - 1])

    def set_compact(self, on: bool) -> None:
        """Aperta (ou repoe) o espaco entre separadores, para janelas baixas."""
        for tab in self._pages.values():
            tab.button.configure(pady=2 if on else 6)
        for label in self._group_labels:
            label.pack_configure(pady=(7 if on else 14, 2 if on else 3))

    def set_highlight(self, on: bool) -> None:
        """Mostra ou esconde a marca do separador activo.

        A janela esconde-a enquanto mostra outra coisa no lugar das paginas (a
        documentacao); escolher um separador volta a mostra-la.
        """
        self._highlight = on
        for tab in self._pages.values():
            self._paint(tab)

    # ------------------------------------------------------------------ #
    def flag(self, key: str, on: bool = True) -> None:
        """Assinala (ou deixa de assinalar) um separador com um campo invalido."""
        self._pages[key].flag.configure(text="●" if on else "")

    def clear_flags(self) -> None:
        for tab in self._pages.values():
            tab.flag.configure(text="")

    def is_flagged(self, key: str) -> bool:
        return bool(self._pages[key].flag.cget("text"))

    def tallest_height(self) -> int:
        """Altura pedida pela pagina mais alta, com o cabecalho [px].

        Serve para reservar ao formulario um espaco que nao mude ao trocar de
        separador, embora so a pagina activa esteja na grelha.
        """
        pages = max((tab.page.winfo_reqheight() for tab in self._pages.values()),
                    default=0)
        return self._head.winfo_reqheight() + self.HEAD_GAP + pages

    def key_of(self, widget) -> Optional[str]:
        """Chave da pagina a que ``widget`` pertence (``None`` se a nenhuma)."""
        by_page = {tab.page: key for key, tab in self._pages.items()}
        node = widget
        while node is not None:
            if node in by_page:
                return by_page[node]
            node = getattr(node, "master", None)
        return None

    @property
    def current(self) -> Optional[str]:
        return self._current

    @property
    def keys(self) -> List[str]:
        return list(self._order)

    def on_change(self, callback: Callable[[str], None]) -> None:
        self._on_change = callback

    def page(self, key: str) -> tk.Frame:
        return self._pages[key].page


class NavLink(tk.Frame):
    """Entrada da barra lateral que nao e uma pagina do formulario.

    Tem o aspecto de um separador (marca a esquerda quando activa), mas apenas
    chama ``command``: e a janela que decide o que mostrar.
    """

    def __init__(self, parent, label: str, command: Callable[[], None],
                 tooltip: str = ""):
        super().__init__(parent, bg=C.NAV_BG)
        self._active = False
        self.accent = tk.Frame(self, bg=C.NAV_BG, width=4)
        self.accent.pack(side="left", fill="y")
        self.button = tk.Button(self, text=label, relief="flat", bd=0,
                                anchor="w", font=F.BASE, cursor="hand2",
                                padx=12, pady=6, bg=C.NAV_BG, fg=C.NAV_FG,
                                highlightthickness=0,
                                activebackground=C.NAV_ACTIVE_BG,
                                activeforeground=C.NAV_ACTIVE_FG,
                                command=command)
        self.button.pack(side="left", fill="x", expand=True)
        if tooltip:
            Tooltip(self.button, tooltip, delay_ms=700)
        for widget in (self, self.button):
            widget.bind("<Enter>", lambda _e: self._paint(hover=True), add="+")
            widget.bind("<Leave>", lambda _e: self._paint(), add="+")

    @property
    def active(self) -> bool:
        return self._active

    def set_active(self, on: bool) -> None:
        self._active = on
        self._paint()

    def set_compact(self, on: bool) -> None:
        self.button.configure(pady=2 if on else 6)

    def _paint(self, hover: bool = False) -> None:
        bg = (C.NAV_ACTIVE_BG if self._active
              else C.NAV_HOVER if hover else C.NAV_BG)
        self.configure(bg=bg)
        self.accent.configure(bg=C.ACCENT if self._active else bg)
        self.button.configure(bg=bg,
                              fg=C.NAV_ACTIVE_FG if self._active else C.NAV_FG,
                              font=F.BOLD if self._active else F.BASE)


class _Tab:
    """Um separador e a sua pagina."""

    __slots__ = ("key", "label", "description", "row", "accent", "button",
                 "flag", "page")

    def __init__(self, key, label, description, row, accent, button, flag, page):
        self.key = key
        self.label = label
        self.description = description
        self.row = row
        self.accent = accent
        self.button = button
        self.flag = flag
        self.page = page


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
    DOT = C.NAVY

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
                               fill=C.FIELD_BG, outline=C.FIELD_BORDER, width=1)
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
                             highlightbackground=C.FIELD_BORDER,
                             highlightcolor=C.FOCUS)
            entry.grid(row=grid_row, column=i + 1, padx=2, pady=1, sticky="ew",
                       ipady=1)
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
                            f"ficar em branco.", widget=entry)
                    record[col.key] = None
                    continue
                try:
                    record[col.key] = float(raw)
                except ValueError:
                    entry.configure(bg=C.ERROR_FIELD)
                    raise FieldError(
                        f'{self.row_noun} {index}, "{col.label}": '
                        f'"{var.get().strip()}" não é um número.', widget=entry)
            out.append(record)
        if not out and not allow_empty:
            first = next(iter(self._rows[0][1].values()))[1]
            raise FieldError(f"Introduza pelo menos uma linha "
                             f"({self.row_noun.lower()} 1).", widget=first)
        return out


class ModeTable(EditableTable):
    """Tabela dos modos do ciclo de ensaio."""

    ROW_NOUN = "Modo"
