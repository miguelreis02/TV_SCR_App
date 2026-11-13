"""
Widgets base da interface: cartoes verdes e campos brancos rotulados.

Cada campo sabe ler-se a si proprio (``value()``) e assinalar-se quando o valor
e invalido, para que a janela principal so tenha de tratar do que e especifico
do dimensionamento.

Dentro de um cartao (:class:`Section`) os campos partilham UMA grelha de
colunas fixas -- rotulo | ajuda | campo | unidade -- para que os campos e as
unidades fiquem alinhados na vertical, seja qual for o comprimento do rotulo.
"""

from __future__ import annotations

import math
import tkinter as tk
from decimal import Decimal
from tkinter import ttk
from typing import Callable, Iterable, Optional, Sequence

from .theme import C, F

__all__ = ["Section", "FloatField", "IntField", "TextField", "ChoiceField",
           "CheckField", "PathField", "FieldError", "Console", "Tooltip",
           "HelpMark", "format_number", "flat_button", "ghost_button"]

# Colunas da grelha de um cartao.
COL_LABEL, COL_HELP, COL_FIELD, COL_UNIT, COL_SPACER = range(5)


class FieldError(ValueError):
    """Valor invalido num campo; a mensagem ja identifica o parametro.

    ``widget`` e o campo em causa (quando se sabe qual e), para a janela poder
    abrir o separador onde ele esta e dar-lhe o foco.
    """

    def __init__(self, message: str, widget=None):
        super().__init__(message)
        self.widget = widget


def format_number(value) -> str:
    """Texto de um numero para mostrar num campo.

    Notacao cientifica curta fora de ``[1e-4, 1e6[`` -- ``2.5e10`` em vez de
    ``25000000000.0``, onde seria preciso contar zeros -- e decimal simples
    dentro dessa gama. Parte de ``repr``, por isso o valor lido de volta com
    ``float`` e exactamente o mesmo.
    """
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        return str(value)
    if value == 0:
        return "0"
    number = Decimal(repr(float(value)))
    exponent = number.adjusted()
    if -4 <= exponent < 6:
        text = format(number, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    sign, digits, _ = number.normalize().as_tuple()
    mantissa = str(digits[0])
    if len(digits) > 1:
        mantissa += "." + "".join(str(d) for d in digits[1:])
    return f"{'-' if sign else ''}{mantissa}e{exponent}"


# ====================================================================== #
#  Botoes
# ====================================================================== #
def _hover(button: tk.Button, normal: str, hover: str) -> None:
    """Realca o botao quando o rato passa por cima (o Tk so o faz ao premir)."""
    def enter(_event):
        if str(button.cget("state")) != "disabled":
            button.configure(bg=hover)

    button.bind("<Enter>", enter, add="+")
    button.bind("<Leave>", lambda _e: button.configure(bg=normal), add="+")


def flat_button(parent, text: str, command, small: bool = False, **kw) -> tk.Button:
    """Botao branco, para accoes secundarias."""
    button = tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                       font=F.SMALL if small else F.BASE, cursor="hand2",
                       padx=9 if small else 14, pady=3 if small else 6,
                       bg=C.BTN_BG, fg=C.BTN_FG, activebackground=C.BTN_ACTIVE,
                       activeforeground=C.BTN_FG, highlightthickness=0, **kw)
    _hover(button, C.BTN_BG, C.BTN_ACTIVE)
    return button


def ghost_button(parent, text: str, command, **kw) -> tk.Button:
    """Botao discreto sobre verde, para accoes de apoio (navegacao, cenario)."""
    button = tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                       font=F.BASE, cursor="hand2", padx=12, pady=5,
                       bg=C.GHOST_BG, fg=C.GHOST_FG,
                       activebackground=C.GHOST_ACTIVE,
                       activeforeground=C.GHOST_FG,
                       disabledforeground=C.GHOST_DISABLED,
                       highlightthickness=0, **kw)
    _hover(button, C.GHOST_BG, C.GHOST_ACTIVE)
    return button


# ====================================================================== #
#  Seccao
# ====================================================================== #
class Section(tk.Frame):
    """Cartao com titulo, para agrupar campos do mesmo tema.

    ``flat=True`` tira o contorno e a margem: serve para um grupo de campos
    dentro de outro cartao.
    """

    PAD = 12

    def __init__(self, parent, title: str, note: str = "", flat: bool = False,
                 note_wrap: int = 330):
        # highlightcolor igual ao contorno: um Frame desenha-o quando o foco
        # esta num campo la dentro, e por omissao seria preto.
        super().__init__(parent, bg=C.BG_PANEL, highlightbackground=C.BORDER,
                         highlightcolor=C.BORDER,
                         highlightthickness=0 if flat else 1, bd=0)
        self._pad = 0 if flat else self.PAD
        self._note: Optional[tk.Label] = None
        # O titulo e usado tal e qual (sem .upper()): maiusculizar estragaria o
        # "alfa" de "Loop de alfa", que passaria a Alfa maiusculo grego.
        if title:
            tk.Label(self, text=title, bg=C.BG_PANEL, fg=C.TITLE, font=F.BOLD,
                     anchor="w", padx=self._pad).pack(fill="x", pady=(9, 0))
        if note:
            self._note = tk.Label(self, text=note, bg=C.BG_PANEL, fg=C.TEXT_DIM,
                                  font=F.SMALL, anchor="w", justify="left",
                                  padx=self._pad, wraplength=note_wrap)
            self._note.pack(fill="x", pady=(2, 0))
            # A nota quebra a largura do cartao, nao a um valor fixo.
            self.bind("<Configure>", self._wrap_note, add="+")
        self.body = tk.Frame(self, bg=C.BG_PANEL)
        self.body.pack(fill="x", padx=self._pad,
                       pady=(7 if (title or note) else self._pad, self._pad))
        self.body.columnconfigure(COL_SPACER, weight=1)
        self._row = 0

    def _wrap_note(self, event) -> None:
        if event.widget is self and self._note is not None:
            self._note.configure(
                wraplength=max(160, event.width - 2 * self._pad - 4))

    def next_row(self) -> int:
        row = self._row
        self._row += 1
        return row

    def add_block(self) -> tk.Frame:
        """Area livre por baixo dos campos, ainda dentro do cartao."""
        block = tk.Frame(self, bg=C.BG_PANEL)
        block.pack(fill="x", padx=self._pad, pady=(0, self._pad))
        return block


# ====================================================================== #
#  Campos
# ====================================================================== #
class _BaseField:
    """Rotulo, marcador de ajuda, widget branco e unidade, em colunas fixas."""

    ROW_PADY = 2

    def __init__(self, section: Section, label: str, unit: str = "",
                 tooltip: str = ""):
        self.section = section
        self.label_text = label
        self.unit = unit
        self.row = section.next_row()
        body = section.body

        self.label = tk.Label(body, text=label, bg=C.BG_PANEL, fg=C.TEXT,
                              font=F.BASE, anchor="w", justify="left",
                              wraplength=230)
        self.label.grid(row=self.row, column=COL_LABEL, sticky="w",
                        pady=self.ROW_PADY)
        self.help: Optional[HelpMark] = None
        if tooltip:
            Tooltip(self.label, tooltip)
            self.help = HelpMark(body, tooltip)
            self.help.grid(row=self.row, column=COL_HELP, padx=(5, 0))
        body.columnconfigure(COL_HELP, minsize=HelpMark.SIZE + 14)

        self.unit_label: Optional[tk.Label] = None
        if unit:
            self.unit_label = tk.Label(body, text="–" if unit == "-" else unit,
                                       bg=C.BG_PANEL, fg=C.TEXT_DIM,
                                       font=F.BASE, anchor="w")
            self.unit_label.grid(row=self.row, column=COL_UNIT, sticky="w",
                                 padx=(6, 0))

    @property
    def name(self) -> str:
        return self.label_text


class _EntryField(_BaseField):
    """Campo de texto branco."""

    def __init__(self, section: Section, label: str, default="", unit: str = "",
                 width: int = 16, tooltip: str = ""):
        super().__init__(section, label, unit, tooltip)
        self.var = tk.StringVar(value=format_number(default))
        self.entry = tk.Entry(
            section.body, textvariable=self.var, width=width,
            bg=C.FIELD_BG, fg=C.FIELD_FG, font=F.BASE, relief="flat",
            insertbackground=C.FIELD_FG, highlightthickness=1,
            highlightbackground=C.BORDER, highlightcolor=C.RUN_BG,
            disabledbackground=C.FIELD_DISABLED)
        self.entry.grid(row=self.row, column=COL_FIELD, sticky="w",
                        pady=self.ROW_PADY, ipady=2)
        self.var.trace_add("write", lambda *_: self.clear_error())

    def raw(self) -> str:
        return self.var.get().strip()

    def set(self, value) -> None:
        self.var.set(format_number(value))
        self.clear_error()

    def mark_error(self) -> None:
        self.entry.configure(bg=C.ERROR_FIELD)

    def clear_error(self) -> None:
        self.entry.configure(bg=C.FIELD_BG)


class TextField(_EntryField):
    """Texto livre. ``value()`` devolve ``None`` se estiver vazio."""

    def value(self) -> Optional[str]:
        raw = self.raw()
        return raw or None


class FloatField(_EntryField):
    """Numero real, com limites opcionais.

    ``allow_empty=True`` permite deixar em branco (``value()`` devolve
    ``None``), para inputs que sao "usa o valor do ficheiro".
    """

    def __init__(self, section: Section, label: str, default=None,
                 unit: str = "", minimum: Optional[float] = None,
                 maximum: Optional[float] = None, allow_empty: bool = False,
                 width: int = 16, tooltip: str = ""):
        super().__init__(section, label, default, unit, width, tooltip)
        self.minimum = minimum
        self.maximum = maximum
        self.allow_empty = allow_empty

    def value(self) -> Optional[float]:
        raw = self.raw().replace(",", ".")
        if not raw:
            if self.allow_empty:
                return None
            raise self._error(f'"{self.name}" nao pode ficar em branco.')
        try:
            v = float(raw)
        except ValueError:
            raise self._error(f'"{self.name}": "{self.raw()}" nao e um numero.')
        if self.minimum is not None and v < self.minimum:
            raise self._error(f'"{self.name}" tem de ser >= {self.minimum:g}.')
        if self.maximum is not None and v > self.maximum:
            raise self._error(f'"{self.name}" tem de ser <= {self.maximum:g}.')
        return v

    def _error(self, message: str) -> FieldError:
        """Assinala o campo e devolve o erro, ja com o campo associado."""
        self.mark_error()
        return FieldError(message, widget=self.entry)


class IntField(FloatField):
    """Numero inteiro."""

    def value(self) -> Optional[int]:
        v = super().value()
        if v is None:
            return None
        if v != int(v):
            raise self._error(f'"{self.name}" tem de ser um numero inteiro.')
        return int(v)


class ChoiceField(_BaseField):
    """Lista de opcoes (combobox de leitura)."""

    def __init__(self, section: Section, label: str, options: Sequence[str],
                 default: str = "", unit: str = "", tooltip: str = ""):
        super().__init__(section, label, unit, tooltip)
        self.var = tk.StringVar(value=default or (options[0] if options else ""))
        self.combo = ttk.Combobox(section.body, textvariable=self.var,
                                  values=list(options), state="readonly",
                                  width=14, style="TVSCR.TCombobox", font=F.BASE)
        self.combo.grid(row=self.row, column=COL_FIELD, sticky="w",
                        pady=self.ROW_PADY)

    def value(self) -> str:
        return self.var.get()

    def set(self, value) -> None:
        self.var.set("" if value is None else str(value))

    def set_options(self, options: Iterable[str], select: Optional[str] = None) -> None:
        options = list(options)
        self.combo.configure(values=options)
        if select is not None and select in options:
            self.var.set(select)
        elif options and self.var.get() not in options:
            self.var.set(options[0])

    def on_change(self, callback: Callable[[], None]) -> None:
        self.combo.bind("<<ComboboxSelected>>", lambda _e: callback())


class CheckField:
    """Caixa de verificacao com indicador desenhado.

    Como no :class:`~tvscr_ui.paged.RadioGroup`, o indicador e desenhado num
    ``Canvas``: o ``tk.Checkbutton`` nativo pinta a marca com a cor do texto,
    que aqui e branca -- sobre a caixa branca ficaria invisivel.
    """

    SIZE = 15
    MARK = "#10281A"

    def __init__(self, section: Section, label: str, default: bool = False,
                 tooltip: str = ""):
        self.label_text = label
        self.var = tk.BooleanVar(value=default)
        row = section.next_row()

        holder = tk.Frame(section.body, bg=C.BG_PANEL, cursor="hand2")
        holder.grid(row=row, column=COL_LABEL, columnspan=COL_SPACER + 1,
                    sticky="w", pady=3)
        self.check = holder

        self.box = tk.Canvas(holder, width=self.SIZE, height=self.SIZE,
                             bg=C.BG_PANEL, highlightthickness=0, bd=0,
                             cursor="hand2")
        self.box.pack(side="left")
        self.label = tk.Label(holder, text=label, bg=C.BG_PANEL, fg=C.TEXT,
                              font=F.BASE, cursor="hand2")
        self.label.pack(side="left", padx=(6, 0))

        for widget in (holder, self.box, self.label):
            widget.bind("<Button-1>", lambda _e: self.toggle())
        if tooltip:
            Tooltip(self.label, tooltip)
            HelpMark(holder, tooltip).pack(side="left", padx=(6, 0))

        self.var.trace_add("write", lambda *_a: self._redraw())
        self._redraw()

    @property
    def name(self) -> str:
        return self.label_text

    def toggle(self) -> None:
        self.var.set(not self.var.get())

    def _redraw(self) -> None:
        box = self.box
        box.delete("all")
        box.create_rectangle(1, 1, self.SIZE - 2, self.SIZE - 2,
                             fill=C.FIELD_BG, outline=C.BORDER, width=1)
        if self.var.get():
            box.create_line(4, 8, 6, 11, width=2, fill=self.MARK,
                            capstyle="round")
            box.create_line(6, 11, 11, 4, width=2, fill=self.MARK,
                            capstyle="round")

    def value(self) -> bool:
        return bool(self.var.get())

    def set(self, value) -> None:
        self.var.set(bool(value))


class PathField(_BaseField):
    """Caminho de ficheiro/pasta, com botao de procura."""

    def __init__(self, section: Section, label: str, default: str = "",
                 mode: str = "open", filetypes=(("CSV", "*.csv"), ("Todos", "*.*")),
                 tooltip: str = "", on_pick: Optional[Callable[[str], None]] = None):
        super().__init__(section, label, "", tooltip)
        self.mode = mode
        self.filetypes = filetypes
        self.on_pick = on_pick

        holder = tk.Frame(section.body, bg=C.BG_PANEL)
        holder.grid(row=self.row, column=COL_FIELD,
                    columnspan=COL_SPACER - COL_FIELD + 1, sticky="ew",
                    pady=self.ROW_PADY)
        holder.columnconfigure(0, weight=1)

        self.var = tk.StringVar(value=default)
        self.entry = tk.Entry(holder, textvariable=self.var, bg=C.FIELD_BG,
                              fg=C.FIELD_FG, font=F.BASE, relief="flat",
                              insertbackground=C.FIELD_FG, highlightthickness=1,
                              highlightbackground=C.BORDER, highlightcolor=C.RUN_BG)
        self.entry.grid(row=0, column=0, sticky="ew", ipady=2)
        self.button = flat_button(holder, "Procurar…", self._browse, small=True)
        self.button.grid(row=0, column=1, padx=(6, 0), sticky="ns")

    def _browse(self) -> None:
        from tkinter import filedialog
        if self.mode == "dir":
            picked = filedialog.askdirectory(title=self.label_text)
        else:
            picked = filedialog.askopenfilename(title=self.label_text,
                                                filetypes=self.filetypes)
        if picked:
            self.var.set(picked)
            if self.on_pick:
                self.on_pick(picked)

    def value(self) -> Optional[str]:
        raw = self.var.get().strip()
        return raw or None

    def set(self, value) -> None:
        self.var.set("" if value is None else str(value))


# ====================================================================== #
#  Consola de resultados
# ====================================================================== #
class Console(tk.Frame):
    """Area de texto branca, so de leitura, para o registo da corrida."""

    def __init__(self, parent, height: int = 14):
        super().__init__(parent, bg=C.LOG_BG)
        #: Chamado depois de cada linha escrita (o painel de resultados usa-o
        #: para assinalar o separador do registo quando este esta escondido).
        self.on_write: Optional[Callable[[], None]] = None
        self.text = tk.Text(self, height=height, bg=C.LOG_BG, fg=C.LOG_FG,
                            font=F.MONO, relief="flat", wrap="none",
                            state="disabled", padx=10, pady=8,
                            highlightthickness=0)
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview,
                                style="TVSCR.Vertical.TScrollbar")
        xscroll = ttk.Scrollbar(self, orient="horizontal",
                                command=self.text.xview,
                                style="TVSCR.Horizontal.TScrollbar")
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.text.tag_configure("erro", foreground=C.LOG_ERR)
        self.text.tag_configure("ok", foreground=C.LOG_OK)
        self.text.tag_configure("titulo", foreground=C.BTN_FG, font=F.MONO)
        self.text.tag_configure("nota", foreground=C.SHEET_DIM)

    def write(self, message: str, tag: str = "") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", message if message.endswith("\n") else message + "\n",
                         tag or ())
        self.text.see("end")
        self.text.configure(state="disabled")
        if self.on_write is not None:
            self.on_write()

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def dump(self) -> str:
        return self.text.get("1.0", "end-1c")


# ====================================================================== #
#  Ajuda contextual
# ====================================================================== #
class HelpMark(tk.Canvas):
    """Pequeno «i» num circulo: assinala que o parametro tem explicacao.

    Sem ele, a ajuda so se descobria passando o rato por acaso sobre o rotulo.
    Desenhado num ``Canvas``, como os outros indicadores da interface, para
    nao depender de um simbolo que a fonte do sistema pode nao ter.
    """

    SIZE = 15

    def __init__(self, parent, text: str, bg: str = C.BG_PANEL):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, bg=bg,
                         highlightthickness=0, bd=0, cursor="question_arrow")
        self.create_oval(1, 1, self.SIZE - 2, self.SIZE - 2,
                         outline=C.TEXT_DIM, width=1)
        self.create_text(self.SIZE // 2, self.SIZE // 2, text="i",
                         fill=C.TEXT_DIM, font=F.SMALL_BOLD)
        Tooltip(self, text, delay_ms=120)


class Tooltip:
    """Balao de ajuda ao passar o rato."""

    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay = delay_ms
        self._after = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:
        if self._window is not None:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        tk.Label(self._window, text=self.text, bg="#FFFDE7", fg="#10281A",
                 font=F.SMALL, justify="left", wraplength=360, padx=8, pady=6,
                 relief="solid", bd=1).pack()
        # Nao deixar o balao sair do ecra (campos junto a margem direita).
        self._window.update_idletasks()
        x = max(0, min(x, self.widget.winfo_screenwidth()
                       - self._window.winfo_reqwidth() - 4))
        self._window.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None
