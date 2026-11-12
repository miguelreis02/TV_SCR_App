"""
Widgets base da interface: seccoes verdes e campos brancos rotulados.

Cada campo sabe ler-se a si proprio (``value()``) e assinalar-se quando o valor
e invalido, para que a janela principal so tenha de tratar do que e especifico
do dimensionamento.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Optional, Sequence

from .theme import C, F

__all__ = ["Section", "FloatField", "IntField", "TextField", "ChoiceField",
           "CheckField", "PathField", "FieldError", "Console", "Tooltip"]


class FieldError(ValueError):
    """Valor invalido num campo; a mensagem ja identifica o parametro."""


# ====================================================================== #
#  Seccao
# ====================================================================== #
class Section(tk.Frame):
    """Painel com titulo, para agrupar campos do mesmo tema."""

    def __init__(self, parent, title: str, note: str = "", flat: bool = False,
                 note_wrap: int = 330):
        super().__init__(parent, bg=C.BG_PANEL, highlightbackground=C.BORDER,
                         highlightthickness=0 if flat else 1, bd=0)
        # O titulo e usado tal e qual (sem .upper()): maiusculizar estragaria o
        # "alfa" de "Loop de alfa", que passaria a Alfa maiusculo grego.
        header = tk.Label(self, text=title, bg=C.BG_PANEL, fg=C.TITLE,
                          font=F.BOLD, anchor="w", padx=8, pady=5)
        header.pack(fill="x")
        if note:
            tk.Label(self, text=note, bg=C.BG_PANEL, fg=C.TEXT_DIM,
                     font=F.SMALL, anchor="w", justify="left", padx=8,
                     wraplength=note_wrap).pack(fill="x", pady=(0, 3))
        self.body = tk.Frame(self, bg=C.BG_PANEL)
        self.body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.body.columnconfigure(1, weight=1)
        self._row = 0

    def next_row(self) -> int:
        row = self._row
        self._row += 1
        return row


# ====================================================================== #
#  Campos
# ====================================================================== #
class _BaseField:
    """Rotulo a esquerda, widget branco a direita, unidade em texto ténue."""

    def __init__(self, section: Section, label: str, unit: str = "",
                 tooltip: str = ""):
        self.section = section
        self.label_text = label
        self.unit = unit
        self.row = section.next_row()
        body = section.body

        text = f"{label} [{unit}]" if unit else label
        self.label = tk.Label(body, text=text, bg=C.BG_PANEL, fg=C.TEXT,
                              font=F.BASE, anchor="w", justify="left",
                              wraplength=190)
        self.label.grid(row=self.row, column=0, sticky="w", pady=1, padx=(0, 8))
        if tooltip:
            Tooltip(self.label, tooltip)

    @property
    def name(self) -> str:
        return self.label_text


class _EntryField(_BaseField):
    """Campo de texto branco."""

    def __init__(self, section: Section, label: str, default="", unit: str = "",
                 width: int = 16, tooltip: str = ""):
        super().__init__(section, label, unit, tooltip)
        self.var = tk.StringVar(value="" if default is None else str(default))
        self.entry = tk.Entry(
            section.body, textvariable=self.var, width=width,
            bg=C.FIELD_BG, fg=C.FIELD_FG, font=F.BASE, relief="flat",
            insertbackground=C.FIELD_FG, highlightthickness=1,
            highlightbackground=C.BORDER, highlightcolor=C.RUN_BG,
            disabledbackground=C.FIELD_DISABLED)
        self.entry.grid(row=self.row, column=1, sticky="w", pady=1)
        self.var.trace_add("write", lambda *_: self.clear_error())

    def raw(self) -> str:
        return self.var.get().strip()

    def set(self, value) -> None:
        self.var.set("" if value is None else str(value))
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
            self.mark_error()
            raise FieldError(f'"{self.name}" nao pode ficar em branco.')
        try:
            v = float(raw)
        except ValueError:
            self.mark_error()
            raise FieldError(f'"{self.name}": "{self.raw()}" nao e um numero.')
        if self.minimum is not None and v < self.minimum:
            self.mark_error()
            raise FieldError(f'"{self.name}" tem de ser >= {self.minimum:g}.')
        if self.maximum is not None and v > self.maximum:
            self.mark_error()
            raise FieldError(f'"{self.name}" tem de ser <= {self.maximum:g}.')
        return v


class IntField(FloatField):
    """Numero inteiro."""

    def value(self) -> Optional[int]:
        v = super().value()
        if v is None:
            return None
        if v != int(v):
            self.mark_error()
            raise FieldError(f'"{self.name}" tem de ser um numero inteiro.')
        return int(v)


class ChoiceField(_BaseField):
    """Lista de opcoes (combobox de leitura)."""

    def __init__(self, section: Section, label: str, options: Sequence[str],
                 default: str = "", unit: str = "", tooltip: str = ""):
        super().__init__(section, label, unit, tooltip)
        self.var = tk.StringVar(value=default or (options[0] if options else ""))
        self.combo = ttk.Combobox(section.body, textvariable=self.var,
                                  values=list(options), state="readonly",
                                  width=15, style="TVSCR.TCombobox", font=F.BASE)
        self.combo.grid(row=self.row, column=1, sticky="w", pady=1)

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
        holder.grid(row=row, column=0, columnspan=2, sticky="w", pady=1)
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
        holder.grid(row=self.row, column=1, sticky="ew", pady=1)
        holder.columnconfigure(0, weight=1)

        self.var = tk.StringVar(value=default)
        self.entry = tk.Entry(holder, textvariable=self.var, bg=C.FIELD_BG,
                              fg=C.FIELD_FG, font=F.BASE, relief="flat",
                              insertbackground=C.FIELD_FG, highlightthickness=1,
                              highlightbackground=C.BORDER, highlightcolor=C.RUN_BG)
        self.entry.grid(row=0, column=0, sticky="ew")
        tk.Button(holder, text="...", command=self._browse, width=3,
                  bg=C.BTN_BG, fg=C.BTN_FG, font=F.BOLD, relief="flat",
                  activebackground=C.BTN_ACTIVE, cursor="hand2").grid(
                      row=0, column=1, padx=(4, 0))

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
        super().__init__(parent, bg=C.BG, highlightbackground=C.BORDER,
                         highlightthickness=1)
        self.text = tk.Text(self, height=height, bg=C.LOG_BG, fg=C.LOG_FG,
                            font=F.MONO, relief="flat", wrap="none",
                            state="disabled", padx=8, pady=6)
        yscroll = tk.Scrollbar(self, orient="vertical", command=self.text.yview)
        xscroll = tk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.text.tag_configure("erro", foreground=C.LOG_ERR)
        self.text.tag_configure("ok", foreground=C.LOG_OK)
        self.text.tag_configure("titulo", foreground=C.BTN_FG, font=F.MONO)

    def write(self, message: str, tag: str = "") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", message if message.endswith("\n") else message + "\n",
                         tag or ())
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def dump(self) -> str:
        return self.text.get("1.0", "end-1c")


# ====================================================================== #
#  Ajuda contextual
# ====================================================================== #
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
        self._window.wm_geometry(f"+{x}+{y}")
        tk.Label(self._window, text=self.text, bg="#FFFDE7", fg="#10281A",
                 font=F.SMALL, justify="left", wraplength=340, padx=7, pady=5,
                 relief="solid", bd=1).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None
