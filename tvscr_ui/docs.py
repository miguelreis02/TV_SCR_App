"""
Documentacao dentro da aplicacao: leitor do ``INSTRUCOES.md``.

O ficheiro Markdown na raiz do projecto e a documentacao oficial; este modulo
mostra-o na janela, sem o copiar nem o converter previamente -- o que se le na
aplicacao e sempre o ficheiro que esta em disco.

Duas partes independentes:

* :func:`parse_markdown` -- le o subconjunto de Markdown usado na
  documentacao (titulos, paragrafos, listas, citacoes, tabelas, blocos de
  codigo, filetes, negrito, italico, codigo em linha, ligacoes e imagens) e
  devolve uma lista de blocos. Nao depende do Tk.
* :class:`DocsView` -- desenha esses blocos num ``tk.Text``, com indice
  lateral, procura e ligacoes.

Nao ha dependencias novas: um conversor de Markdown completo seria uma
biblioteca a mais para instalar, e a documentacao so usa este subconjunto.
"""

from __future__ import annotations

import re
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from .theme import C, F
from .widgets import ghost_button

__all__ = ["DocsView", "parse_markdown", "parse_inline", "slugify", "plain_text",
           "Block", "Span", "DOC_PATH"]

#: A documentacao oficial: o ``INSTRUCOES.md`` da raiz do projecto.
DOC_PATH = Path(__file__).resolve().parents[1] / "INSTRUCOES.md"


# ====================================================================== #
#  Markdown -> blocos
# ====================================================================== #
@dataclass
class Span:
    """Troco de texto com o mesmo estilo."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    link: Optional[str] = None
    image: Optional[str] = None       # caminho da imagem (``text`` e a legenda)


@dataclass
class Block:
    """Um bloco do documento.

    ``kind`` e um de: ``heading``, ``paragraph``, ``list``, ``quote``,
    ``code``, ``table``, ``rule``.
    """

    kind: str
    spans: List[Span] = field(default_factory=list)
    level: int = 0                    # titulo: 1..6; lista: profundidade
    anchor: str = ""                  # titulo: ancora (como no GitHub)
    marker: str = ""                  # lista: "•" ou "1."
    text: str = ""                    # bloco de codigo
    rows: List[List[List[Span]]] = field(default_factory=list)   # tabela


_INLINE = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|(?P<image>!\[[^\]]*\]\([^)\s]+\))"
    r"|(?P<link>\[[^\]]+\]\([^)\s]+\))"
    r"|(?P<bold>\*\*(?=\S).+?(?<=\S)\*\*)"
    r"|(?P<italic>\*(?=[^\s*])[^*\n]+?(?<=[^\s*])\*)")
_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def parse_inline(text: str, bold: bool = False, italic: bool = False,
                 link: Optional[str] = None) -> List[Span]:
    """Parte uma linha em trocos de estilo uniforme."""
    spans: List[Span] = []
    position = 0
    for match in _INLINE.finditer(text):
        if match.start() > position:
            spans.append(Span(text[position:match.start()], bold, italic,
                              link=link))
        token = match.group(0)
        kind = match.lastgroup
        if kind == "code":
            spans.append(Span(token[1:-1], bold, italic, code=True, link=link))
        elif kind == "image":
            label, target = _LINK.match(token).groups()
            spans.append(Span(label, image=target))
        elif kind == "link":
            label, target = _LINK.match(token).groups()
            spans.extend(parse_inline(label, bold, italic, link=target))
        elif kind == "bold":
            spans.extend(parse_inline(token[2:-2], True, italic, link))
        else:
            spans.extend(parse_inline(token[1:-1], bold, True, link))
        position = match.end()
    if position < len(text):
        spans.append(Span(text[position:], bold, italic, link=link))
    return spans


def plain_text(spans: List[Span]) -> str:
    """Texto dos trocos, sem marcas de estilo."""
    return "".join(span.text for span in spans)


def slugify(title: str, used: Optional[Dict[str, int]] = None) -> str:
    """Ancora de um titulo, pela regra do GitHub.

    Minusculas; fora letras, algarismos, espacos, hifens e sublinhados; cada
    espaco passa a hifen. Um titulo repetido recebe ``-1``, ``-2``, ... Assim
    as ligacoes do indice funcionam igual no GitHub e na aplicacao.
    """
    slug = re.sub(r"[^\w\- ]", "", title.strip().lower()).replace(" ", "-")
    if used is None:
        return slug
    count = used.get(slug, 0)
    used[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def _table_cells(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [cell.strip().replace("\\|", "|") for cell in cells]


def parse_markdown(source: str) -> List[Block]:
    """Converte o texto Markdown numa lista de blocos, pela ordem do documento."""
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[Block] = []
    used: Dict[str, int] = {}
    paragraph: List[str] = []
    i = 0

    def flush() -> None:
        if paragraph:
            blocks.append(Block("paragraph",
                                parse_inline(" ".join(s.strip() for s in paragraph))))
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # --- bloco de codigo ---
        if stripped.startswith("```"):
            flush()
            body: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            blocks.append(Block("code", text="\n".join(body)))
            i += 1
            continue

        if not stripped:
            flush()
            i += 1
            continue

        # --- titulo ---
        heading = _HEADING.match(line)
        if heading:
            flush()
            spans = parse_inline(heading.group(2))
            blocks.append(Block("heading", spans, level=len(heading.group(1)),
                                anchor=slugify(plain_text(spans), used)))
            i += 1
            continue

        # --- tabela ---
        if ("|" in line and i + 1 < len(lines)
                and _TABLE_RULE.match(lines[i + 1]) and "-" in lines[i + 1]):
            flush()
            rows = [[parse_inline(cell) for cell in _table_cells(line)]]
            i += 2
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                rows.append([parse_inline(cell) for cell in _table_cells(lines[i])])
                i += 1
            width = len(rows[0])
            for row in rows:                      # todas com o mesmo n. de colunas
                del row[width:]
                row.extend([] for _ in range(width - len(row)))
            blocks.append(Block("table", rows=rows))
            continue

        # --- filete ---
        if _RULE.match(line):
            flush()
            blocks.append(Block("rule"))
            i += 1
            continue

        # --- citacao ---
        if stripped.startswith(">"):
            flush()
            quote: List[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                text = lines[i].strip()[1:].strip()
                if text:
                    quote.append(text)
                elif quote:
                    blocks.append(Block("quote", parse_inline(" ".join(quote))))
                    quote = []
                i += 1
            if quote:
                blocks.append(Block("quote", parse_inline(" ".join(quote))))
            continue

        # --- lista ---
        item = _ITEM.match(line)
        if item:
            flush()
            indent, marker, text = item.groups()
            parts = [text]
            i += 1
            while i < len(lines):
                follow = lines[i]
                if (not follow.strip() or _ITEM.match(follow)
                        or follow.strip().startswith(("```", "#", ">", "|"))
                        or not follow.startswith(" ")):
                    break
                parts.append(follow.strip())      # continuacao do mesmo item
                i += 1
            blocks.append(Block(
                "list", parse_inline(" ".join(parts)),
                level=len(indent.replace("\t", "    ")) // 2,
                marker="•" if marker in "-*+" else marker.rstrip(".)") + "."))
            continue

        paragraph.append(line)
        i += 1

    flush()
    return blocks


# ====================================================================== #
#  Leitor
# ====================================================================== #
class DocsView(tk.Frame):
    """Leitor da documentacao: indice a esquerda, texto a direita, procura.

    ``on_close`` e chamado pelo botao que volta ao dimensionamento.
    """

    TOC_LEVELS = (2, 3)              # niveis de titulo que entram no indice
    MARGIN = 28                      # margem do texto [px]

    def __init__(self, parent, path: Optional[Path] = None,
                 on_close: Optional[Callable[[], None]] = None):
        super().__init__(parent, bg=C.BG)
        self.home = Path(path) if path is not None else DOC_PATH
        self.path = self.home
        self.blocks: List[Block] = []
        self._images: List[tk.PhotoImage] = []
        self._links: Dict[str, str] = {}
        self._toc: List[Tuple[str, str]] = []           # (ancora, titulo)
        #: celulas das tabelas: (tabela, rotulo, texto, e cabecalho?)
        self._cells: List[Tuple[tk.Frame, tk.Label, str, bool]] = []
        self._hits: List[Tuple] = []
        self._hit = -1
        self._last_query = ""
        self._rendered_width = 0
        self._stamp: Optional[float] = None
        self._resize_after: Optional[str] = None
        self._spy_after: Optional[str] = None

        self._build_bar(on_close)
        body = tk.Frame(self, bg=C.BG)
        body.pack(fill="both", expand=True)
        self._build_toc(body)
        self._build_text(body)
        self.load(self.home)

    # ------------------------------------------------------------------ #
    #  Construcao
    # ------------------------------------------------------------------ #
    def _build_bar(self, on_close) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.pack(fill="x", pady=(0, 10))

        if on_close is not None:
            ghost_button(bar, "◀  Voltar ao dimensionamento",
                         on_close).pack(side="left", padx=(0, 12))
        self.btn_home = ghost_button(bar, "Documentação principal",
                                     lambda: self.load(self.home))
        self._title = tk.Label(bar, text="", bg=C.BG, fg=C.TITLE,
                               font=F.PAGE_TITLE, anchor="w")

        # --- procura (a direita); empacotada antes do titulo, para ser este a
        # ceder quando a janela e estreita ---
        self._count = tk.Label(bar, text="", bg=C.BG, fg=C.TEXT_DIM,
                               font=F.SMALL, width=14, anchor="w")
        self._count.pack(side="right")
        ghost_button(bar, "▼", lambda: self.find(True)).pack(side="right",
                                                             padx=(2, 8))
        ghost_button(bar, "▲", lambda: self.find(False)).pack(side="right",
                                                              padx=(6, 0))
        self.query = tk.StringVar()
        self.search = tk.Entry(
            bar, textvariable=self.query, width=24, bg=C.FIELD_BG,
            fg=C.FIELD_FG, font=F.BASE, relief="flat",
            insertbackground=C.FIELD_FG, highlightthickness=1,
            highlightbackground=C.FIELD_BORDER, highlightcolor=C.FOCUS)
        self.search.pack(side="right", ipady=3)
        tk.Label(bar, text="Procurar", bg=C.BG, fg=C.TEXT_DIM,
                 font=F.BASE).pack(side="right", padx=(0, 6))
        self.search.bind("<Return>", lambda _e: self.find(True))
        self.search.bind("<Shift-Return>", lambda _e: self.find(False))
        self.search.bind("<KP_Enter>", lambda _e: self.find(True))
        self._title.pack(side="left", fill="x", expand=True)

    def _build_toc(self, body: tk.Frame) -> None:
        holder = tk.Frame(body, bg=C.BG_PANEL, highlightthickness=1,
                          highlightbackground=C.BORDER, highlightcolor=C.BORDER)
        holder.pack(side="left", fill="y", padx=(0, 12))
        tk.Label(holder, text="ÍNDICE", bg=C.BG_PANEL, fg=C.TITLE,
                 font=F.BOLD, anchor="w", padx=12).pack(fill="x", pady=(9, 4))
        inner = tk.Frame(holder, bg=C.BG_PANEL)
        inner.pack(fill="both", expand=True, padx=(4, 0), pady=(0, 4))
        self.toc = tk.Listbox(
            inner, width=34, activestyle="none", exportselection=False,
            bg=C.BG_PANEL, fg=C.TEXT, font=F.BASE, relief="flat", bd=0,
            highlightthickness=0, selectbackground=C.SELECT_BG,
            selectforeground=C.SELECT_FG, selectborderwidth=0)
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self.toc.yview,
                               style="TVSCR.Vertical.TScrollbar")
        self.toc.configure(yscrollcommand=scroll.set)
        self.toc.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.toc.bind("<<ListboxSelect>>", self._on_toc_pick)

    def _build_text(self, body: tk.Frame) -> None:
        holder = tk.Frame(body, bg=C.SHEET_BG, highlightthickness=1,
                          highlightbackground=C.BORDER, highlightcolor=C.BORDER)
        holder.pack(side="left", fill="both", expand=True)
        self.text = tk.Text(
            holder, bg=C.SHEET_BG, fg=C.SHEET_FG, font=F.DOC, relief="flat",
            wrap="word", state="disabled", cursor="arrow", padx=self.MARGIN,
            pady=18, highlightthickness=0, spacing1=0, spacing3=0,
            selectbackground=C.SELECT_BG, selectforeground=C.SELECT_FG,
            inactiveselectbackground=C.TAB_BG)
        scroll = ttk.Scrollbar(holder, orient="vertical",
                               command=self.text.yview,
                               style="TVSCR.Vertical.TScrollbar")
        self.text.configure(yscrollcommand=lambda a, b: (scroll.set(a, b),
                                                         self._schedule_spy()))
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.bind("<Configure>", self._on_resize)
        self._configure_tags()

    def _configure_tags(self) -> None:
        t = self.text
        t.tag_configure("h1", font=F.DOC_H1, foreground=C.TITLE, spacing1=4,
                        spacing3=10)
        t.tag_configure("h2", font=F.DOC_H2, foreground=C.TITLE, spacing1=22,
                        spacing3=8)
        t.tag_configure("h3", font=F.DOC_H3, foreground=C.TITLE, spacing1=16,
                        spacing3=6)
        t.tag_configure("h4", font=F.DOC_H4, foreground=C.TITLE, spacing1=12,
                        spacing3=4)
        t.tag_configure("p", spacing1=3, spacing2=2, spacing3=7)
        t.tag_configure("quote", lmargin1=18, lmargin2=18, rmargin=10,
                        background=C.HEAD_BG, spacing1=7, spacing2=2,
                        spacing3=7)
        for level in range(4):
            left = 14 + 22 * level
            t.tag_configure(f"li{level}", lmargin1=left, lmargin2=left + 20,
                            spacing1=2, spacing2=2, spacing3=4)
        t.tag_configure("codeblock", font=F.MONO, background=C.CODE_BG,
                        lmargin1=12, lmargin2=12, wrap="none", spacing1=1,
                        spacing3=1)
        t.tag_configure("gap", font=F.SMALL, spacing1=0, spacing3=0)
        t.tag_configure("bold", font=F.DOC_BOLD)
        t.tag_configure("italic", font=F.DOC_ITALIC)
        t.tag_configure("code", font=F.MONO, background=C.CODE_BG)
        t.tag_configure("link", foreground=C.BLUE, underline=True)
        t.tag_configure("match", background=C.MATCH_BG)
        t.tag_configure("current", background=C.NAVY, foreground=C.SELECT_FG)
        t.tag_raise("match")
        t.tag_raise("current")
        t.tag_raise("sel")
        t.tag_bind("link", "<Enter>", lambda _e: t.configure(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda _e: t.configure(cursor="arrow"))
        t.tag_bind("link", "<Button-1>", self._on_link_click)

    # ------------------------------------------------------------------ #
    #  Carregar e desenhar
    # ------------------------------------------------------------------ #
    def load(self, path: Path, anchor: Optional[str] = None) -> bool:
        """Le um ficheiro Markdown e mostra-o. Devolve ``False`` se nao existir."""
        path = Path(path)
        try:
            source = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            self.blocks = [
                Block("heading", [Span("Documentação não encontrada")], level=1,
                      anchor="erro"),
                Block("paragraph", [
                    Span("Não foi possível ler "), Span(str(path), code=True),
                    Span(f" ({exc.strerror or exc}). A documentação é o ficheiro "),
                    Span("INSTRUCOES.md", code=True),
                    Span(" da pasta do projeto.")])]
            ok = False
        else:
            self.blocks = parse_markdown(source)
            ok = True
        self.path = path
        self._stamp = self._file_stamp()
        if self.path == self.home:
            self.btn_home.pack_forget()
        else:
            self.btn_home.pack(side="left", padx=(0, 12), before=self._count)
        self._title.configure(text="Documentação" if self.path == self.home
                              else path.name)
        self._render()
        if anchor:
            self.goto(anchor)
        return ok

    def reload(self) -> None:
        self.load(self.path)

    def _file_stamp(self) -> Optional[float]:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def reload_if_changed(self) -> bool:
        """Volta a ler o ficheiro se ele tiver sido alterado em disco."""
        if self._file_stamp() == self._stamp:
            return False
        anchor = self.current_anchor()
        self.load(self.path, anchor)
        return True

    @property
    def anchors(self) -> List[str]:
        return [b.anchor for b in self.blocks if b.kind == "heading"]

    def _render(self) -> None:
        t = self.text
        self._rendered_width = max(t.winfo_width(), 400)
        t.configure(state="normal")
        t.delete("1.0", "end")
        for name in t.tag_names():
            if name.startswith("link:"):
                t.tag_delete(name)
        for mark in t.mark_names():
            if mark.startswith("h:"):
                t.mark_unset(mark)
        self._images.clear()
        self._links.clear()
        self._cells.clear()
        self._toc.clear()
        self._hits, self._hit, self._last_query = [], -1, ""
        self._count.configure(text="")

        for block in self.blocks:
            getattr(self, f"_draw_{block.kind}")(block)
        t.configure(state="disabled")

        self.toc.delete(0, "end")
        for _anchor, title in self._toc:
            self.toc.insert("end", title)
        t.yview_moveto(0)

    def _insert(self, spans: List[Span], base: str) -> None:
        """Escreve trocos de texto com as marcas de estilo e as ligacoes."""
        t = self.text
        for span in spans:
            if span.image is not None:
                self._insert_image(span)
                continue
            tags = [base]
            if span.bold:
                tags.append("bold")
            if span.italic:
                tags.append("italic")
            if span.code:
                tags.append("code")
            if span.link:
                name = f"link:{len(self._links)}"
                self._links[name] = span.link
                tags += ["link", name]
            t.insert("end", span.text, tuple(tags))

    def _load_image(self, target: str, max_width: int) -> Optional[tk.PhotoImage]:
        path = (self.path.parent / target).resolve()
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
        factor = -(-image.width() // max(max_width, 80))        # arredonda acima
        if factor > 1:
            image = image.subsample(factor)
        self._images.append(image)
        return image

    def _insert_image(self, span: Span) -> None:
        image = self._load_image(span.image, self._content_width())
        if image is None:
            self.text.insert("end", f"[imagem: {span.text or span.image}]",
                             ("p", "italic"))
        else:
            self.text.image_create("end", image=image, padx=2, pady=4)

    def _content_width(self) -> int:
        return max(300, self._rendered_width - 2 * self.MARGIN - 24)

    # --- um metodo por tipo de bloco ---
    def _draw_heading(self, block: Block) -> None:
        t = self.text
        level = min(block.level, 4)
        mark = f"h:{block.anchor}"
        t.mark_set(mark, "end-1c")
        t.mark_gravity(mark, "left")
        self._insert(block.spans, f"h{level}")
        t.insert("end", "\n", f"h{level}")
        if block.level in self.TOC_LEVELS:
            indent = "    " * (block.level - self.TOC_LEVELS[0])
            self._toc.append((block.anchor, indent + plain_text(block.spans)))

    def _draw_paragraph(self, block: Block) -> None:
        self._insert(block.spans, "p")
        self.text.insert("end", "\n", "p")

    def _draw_quote(self, block: Block) -> None:
        self._insert(block.spans, "quote")
        self.text.insert("end", "\n", "quote")
        self.text.insert("end", "\n", "gap")

    def _draw_list(self, block: Block) -> None:
        tag = f"li{min(block.level, 3)}"
        self.text.insert("end", f"{block.marker} ", tag)
        self._insert(block.spans, tag)
        self.text.insert("end", "\n", tag)

    def _draw_code(self, block: Block) -> None:
        self.text.insert("end", "\n", "gap")
        self.text.insert("end", block.text + "\n", "codeblock")
        self.text.insert("end", "\n", "gap")

    def _draw_rule(self, _block: Block) -> None:
        rule = tk.Frame(self.text, bg=C.BORDER, height=1,
                        width=self._content_width())
        self.text.window_create("end", window=rule, pady=8)
        self.text.insert("end", "\n", "gap")
        self._scroll_through(rule)

    def _draw_table(self, block: Block) -> None:
        """Tabela como grelha de rotulos embutida no texto.

        Um ``tk.Text`` nao sabe quebrar texto dentro de colunas; com rotulos
        cada celula quebra a sua largura. As larguras sao repartidas pelo
        espaco disponivel, na proporcao do conteudo.
        """
        rows = block.rows
        n_cols = len(rows[0])
        pad = 16
        available = self._content_width() - (n_cols + 1)
        natural = [max(max((self._cell_font(row[c], r == 0).measure(
                                plain_text(row[c])) for r, row in enumerate(rows)),
                           default=0) + pad, 48)
                   for c in range(n_cols)]
        widths = _share_widths(natural, available, minimum=96)

        frame = tk.Frame(self.text, bg=C.TILE_BORDER)
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                header = r == 0
                image = (self._load_image(cell[0].image, widths[c] - pad)
                         if len(cell) == 1 and cell[0].image else None)
                label = tk.Label(
                    frame, bg=C.HEAD_BG if header else C.SHEET_BG,
                    fg=C.TITLE if header else C.SHEET_FG,
                    font=self._cell_font(cell, header), anchor="nw",
                    justify="left", padx=7, pady=5)
                if image is not None:
                    label.configure(image=image)
                else:
                    label.configure(text=plain_text(cell),
                                    wraplength=widths[c] - pad)
                label.grid(row=r, column=c, sticky="nsew",
                           padx=(1, 1 if c == n_cols - 1 else 0),
                           pady=(1, 1 if r == len(rows) - 1 else 0))
                self._cells.append((frame, label, plain_text(cell), header))
                self._scroll_through(label)
        for c in range(n_cols):
            frame.columnconfigure(c, minsize=widths[c])
        self.text.window_create("end", window=frame, pady=6)
        self.text.insert("end", "\n", "gap")
        self._scroll_through(frame)

    @staticmethod
    def _cell_font(cell: List[Span], header: bool):
        if header or (cell and all(s.bold for s in cell)):
            return F.DOC_BOLD
        if cell and all(s.code for s in cell):
            return F.MONO
        return F.DOC

    def _scroll_through(self, widget) -> None:
        """A roda do rato sobre um elemento embutido rola o texto por baixo."""
        widget.bind("<MouseWheel>", lambda e: self.text.yview_scroll(
            int(-e.delta / 120) * 3, "units"))
        widget.bind("<Button-4>", lambda _e: self.text.yview_scroll(-3, "units"))
        widget.bind("<Button-5>", lambda _e: self.text.yview_scroll(3, "units"))

    def _on_resize(self, event) -> None:
        """Mudou a largura: as tabelas tem de ser repartidas de novo."""
        if abs(event.width - self._rendered_width) < 24:
            return
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(180, self._rerender)

    def _rerender(self) -> None:
        self._resize_after = None
        if abs(self.text.winfo_width() - self._rendered_width) < 24:
            return
        anchor = self.current_anchor()
        query = self.query.get()
        self._render()
        if anchor:
            self.goto(anchor)
        if query.strip():
            self._collect_hits(query.strip())

    # ------------------------------------------------------------------ #
    #  Navegacao
    # ------------------------------------------------------------------ #
    def goto(self, anchor: str) -> bool:
        """Poe o titulo com essa ancora no topo. ``False`` se nao existir."""
        mark = f"h:{anchor.lstrip('#')}"
        if mark not in self.text.mark_names():
            return False
        self.text.yview(self.text.index(mark))
        self._spy()
        return True

    def current_anchor(self) -> Optional[str]:
        """Ancora do ultimo titulo que ja passou pelo topo da vista."""
        top = self.text.index("@0,0")
        current = None
        for block in self.blocks:
            if block.kind != "heading":
                continue
            if self.text.compare(f"h:{block.anchor}", "<=", f"{top} lineend"):
                current = block.anchor
            else:
                break
        return current

    def _on_toc_pick(self, _event=None) -> None:
        picked = self.toc.curselection()
        if picked:
            self.goto(self._toc[picked[0]][0])

    def _schedule_spy(self) -> None:
        if self._spy_after is None:
            self._spy_after = self.after(120, self._spy)

    def _spy(self) -> None:
        """Realca no indice a seccao que esta a ser lida."""
        self._spy_after = None
        top = self.text.index("@0,0")
        row = None
        for index, (anchor, _title) in enumerate(self._toc):
            if self.text.compare(f"h:{anchor}", "<=", f"{top} lineend"):
                row = index
            else:
                break
        self.toc.selection_clear(0, "end")
        if row is not None:
            self.toc.selection_set(row)
            self.toc.see(row)

    def _on_link_click(self, event) -> None:
        index = self.text.index(f"@{event.x},{event.y}")
        for name in self.text.tag_names(index):
            if name in self._links:
                self.follow(self._links[name])
                return

    def follow(self, target: str) -> None:
        """Segue uma ligacao: ancora, outro ficheiro Markdown ou a Internet."""
        if target.startswith("#"):
            self.goto(target)
        elif re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I) or \
                target.startswith("mailto:"):
            webbrowser.open(target)
        else:
            name, _, anchor = target.partition("#")
            path = (self.path.parent / name).resolve()
            if path.suffix.lower() == ".md" and path.is_file():
                self.load(path, anchor or None)
            elif path.exists():
                webbrowser.open(path.as_uri())

    # ------------------------------------------------------------------ #
    #  Procura
    # ------------------------------------------------------------------ #
    def focus_search(self) -> None:
        self.search.focus_set()
        self.search.selection_range(0, "end")

    def _collect_hits(self, query: str) -> None:
        t = self.text
        t.tag_remove("match", "1.0", "end")
        t.tag_remove("current", "1.0", "end")
        self._paint_cells()
        self._hits, self._hit, self._last_query = [], -1, query
        if not query:
            self._count.configure(text="")
            return

        hits = []
        length = tk.IntVar()
        start = "1.0"
        while True:
            start = t.search(query, start, stopindex="end", nocase=True,
                             count=length)
            if not start or length.get() == 0:
                break
            end = f"{start}+{length.get()}c"
            t.tag_add("match", start, end)
            line, column = (int(n) for n in start.split("."))
            hits.append(((line, column, 0), "text", start, end))
            start = end
        needle = query.lower()
        for order, (frame, label, text, _header) in enumerate(self._cells):
            if needle in text.lower():
                line, column = (int(n) for n in t.index(frame).split("."))
                hits.append(((line, column, order + 1), "cell", frame, label))
        hits.sort(key=lambda hit: hit[0])
        self._hits = hits
        self._paint_cells()
        self._count.configure(
            text="sem resultados" if not hits else f"{len(hits)} resultados")

    def _paint_cells(self, current: Optional[tk.Label] = None) -> None:
        """Cores das celulas: normal, com o texto procurado, ou a corrente."""
        found = {hit[3] for hit in self._hits if hit[1] == "cell"}
        for _frame, label, _text, header in self._cells:
            if label is current:
                label.configure(bg=C.NAVY, fg=C.SELECT_FG)
            elif label in found:
                label.configure(bg=C.MATCH_BG, fg=C.SHEET_FG)
            else:
                label.configure(bg=C.HEAD_BG if header else C.SHEET_BG,
                                fg=C.TITLE if header else C.SHEET_FG)

    def find(self, forward: bool = True) -> int:
        """Vai para a ocorrencia seguinte (ou anterior). Devolve o total."""
        query = self.query.get().strip()
        if query != self._last_query:
            self._collect_hits(query)
        if not self._hits:
            return 0
        self._hit = (self._hit + (1 if forward else -1)) % len(self._hits)
        _key, kind, first, second = self._hits[self._hit]
        t = self.text
        t.tag_remove("current", "1.0", "end")
        self._paint_cells(current=second if kind == "cell" else None)
        if kind == "text":
            t.tag_add("current", first, second)
            t.see(first)
        else:
            t.see(t.index(first))
            self.update_idletasks()
            box = t.dlineinfo(t.index(first))
            if box is not None:                   # celula fora da vista
                y = box[1] + second.winfo_y()
                if y < 0 or y + second.winfo_height() > t.winfo_height():
                    t.yview_scroll(y - 60, "pixels")
        self._count.configure(text=f"{self._hit + 1} de {len(self._hits)}")
        return len(self._hits)


def _share_widths(natural: List[int], available: int,
                  minimum: int = 96) -> List[int]:
    """Reparte ``available`` px pelas colunas, na proporcao do conteudo.

    Colunas que cabem na sua parte justa ficam com a largura natural; as
    restantes dividem o que sobra, proporcionalmente ao que pediam.
    """
    if sum(natural) <= available:
        return list(natural)
    widths = [0] * len(natural)
    pending = list(range(len(natural)))
    space = available
    while pending:
        fair = space / len(pending)
        small = [c for c in pending if natural[c] <= fair]
        if not small:
            break
        for c in small:
            widths[c] = natural[c]
            space -= natural[c]
            pending.remove(c)
    total = sum(natural[c] for c in pending) or 1
    for c in pending:
        widths[c] = max(minimum, int(space * natural[c] / total))
    return widths
