"""
Paleta e tipos de letra da interface.

Fundos claros e texto preto, com os pormenores nas duas cores do logotipo da
TecnoVeritas: azul-marinho (titulos, botoes, seleccao) e vermelho (marcas do
que esta activo, erros). Tudo o que e cor ou fonte esta aqui: para mudar o
aspecto da aplicacao nao e preciso tocar no resto da interface.
"""

from __future__ import annotations

import tkinter.font as tkfont

__all__ = ["C", "F", "init_fonts"]


class C:
    """Cores."""

    # --- cores da marca (lidas do logotipo) ---
    NAVY = "#00275D"        # azul-marinho do nome
    RED = "#BC1020"         # vermelho do emblema
    BLUE = "#1F5FBF"        # azul mais vivo: foco, ligacoes, progresso

    BG = "#EEF1F5"          # cinzento-azulado muito claro -- janela e paginas
    BG_PANEL = "#FFFFFF"    # branco -- cartao de uma seccao
    BG_HEADER = "#FFFFFF"   # branco -- barra de titulo (o logotipo funde-se)
    BORDER = "#C9D1DB"      # contorno dos cartoes e dos paineis
    STATUS_BG = "#E3E8EF"   # barra de estado

    FIELD_BG = "#FFFFFF"    # campos de input
    FIELD_FG = "#111111"
    FIELD_BORDER = "#9AA6B4"    # mais escuro que o do cartao: o campo e branco
    FIELD_DISABLED = "#E9EDF2"
    FOCUS = BLUE                # contorno do campo com o cursor

    TEXT = "#111111"        # texto corrente
    TEXT_DIM = "#55606E"    # unidades, notas
    TITLE = NAVY            # titulos e valores em destaque

    # --- navegacao lateral (separadores verticais) ---
    NAV_BG = "#E3E8EF"
    NAV_FG = "#111111"
    NAV_GROUP = "#5B6878"       # titulo de um grupo de separadores
    NAV_HOVER = "#D3DBE6"
    NAV_ACTIVE_BG = "#FFFFFF"
    NAV_ACTIVE_FG = NAVY
    ACCENT = RED                # marca do separador activo
    FLAG = RED                  # separador com um campo invalido

    # --- separadores horizontais do painel de resultados ---
    TAB_BG = "#DCE3EC"          # separador inativo
    TAB_FG = "#27323F"
    TAB_HOVER = "#CBD5E2"
    TAB_ACTIVE_BG = "#FFFFFF"   # separador activo: branco, como a folha
    TAB_ACTIVE_FG = NAVY

    BTN_BG = "#E8EEF6"      # botoes secundarios (sobre branco)
    BTN_FG = NAVY
    BTN_ACTIVE = "#D3DFEF"

    GHOST_BG = "#DCE3EC"    # botoes discretos sobre o fundo (navegacao)
    GHOST_FG = NAVY
    GHOST_ACTIVE = "#CBD5E2"
    GHOST_DISABLED = "#9AA6B4"

    RUN_BG = NAVY           # botao principal (correr)
    RUN_FG = "#FFFFFF"
    RUN_ACTIVE = "#0B3F8F"
    RUN_DISABLED_FG = "#B8C4D6"

    SELECT_BG = NAVY        # linha ou opcao escolhida
    SELECT_FG = "#FFFFFF"
    PROGRESS = BLUE

    LOG_BG = "#FFFFFF"      # consola de resultados
    LOG_FG = "#111111"
    LOG_ERR = RED
    LOG_OK = "#0B4A9E"

    # --- folha de resultados e de documentacao ---
    SHEET_BG = "#FFFFFF"
    SHEET_FG = "#111111"
    SHEET_DIM = "#55606E"       # legendas e notas
    TILE_BG = "#F4F6F9"         # mosaico de um indicador
    TILE_BORDER = "#D5DBE3"
    TILE_KEY_BG = "#E8EFF8"     # mosaico principal (volume critico)
    TILE_ERR_BG = "#FCE8EA"
    TILE_ERR_BORDER = "#EDB4BA"
    HEAD_BG = "#E8EFF8"         # cabecalho das tabelas
    ROW_CRIT = "#CFE0F5"        # linha do volume critico
    CODE_BG = "#F1F4F8"         # codigo, na documentacao
    MATCH_BG = "#FFE9A8"        # texto encontrado pela procura
    SCROLL = "#C3CCD8"          # cursor das barras de rolamento
    SCROLL_TROUGH = "#EEF1F5"

    TIP_BG = "#FFFFFF"          # balao de ajuda

    ERROR_FIELD = "#FDE3E5"  # campo com valor invalido

    #: Cores das series dos graficos, pela ordem em que sao usadas.
    SERIES = (NAVY, RED, "#5B8DD6", "#7A8794", "#E0707A", BLUE)
    STAR = "#7FB2F0"            # marcador do volume critico


class F:
    """Tipos de letra (preenchidos por :func:`init_fonts`)."""

    BASE = None
    BOLD = None
    ITALIC = None
    SMALL = None
    SMALL_BOLD = None
    TITLE = None
    SUBTITLE = None
    PAGE_TITLE = None
    KPI = None
    KPI_SMALL = None
    MONO = None
    # --- documentacao ---
    DOC = None
    DOC_BOLD = None
    DOC_ITALIC = None
    DOC_H1 = None
    DOC_H2 = None
    DOC_H3 = None
    DOC_H4 = None


def init_fonts(root) -> None:
    """Cria os tipos de letra. Tem de ser chamada depois de existir um ``Tk``."""
    family = "Segoe UI"
    available = set(tkfont.families(root))
    if family not in available:
        family = "TkDefaultFont"
    # Sem Consolas (fora do Windows), usar a familia REAL da fonte fixa do Tk:
    # "TkFixedFont" e um nome de fonte, nao de familia, e passado como familia
    # daria uma fonte proporcional -- as tabelas da consola deixavam de alinhar.
    mono = ("Consolas" if "Consolas" in available
            else tkfont.nametofont("TkFixedFont").actual("family"))

    def font(size, **kw):
        return tkfont.Font(root=root, family=family, size=size, **kw)

    F.BASE = font(10)
    F.BOLD = font(10, weight="bold")
    F.ITALIC = font(10, slant="italic")
    F.SMALL = font(9)
    F.SMALL_BOLD = font(8, weight="bold")
    F.TITLE = font(15, weight="bold")
    F.SUBTITLE = font(10)
    F.PAGE_TITLE = font(13, weight="bold")
    F.KPI = font(20, weight="bold")
    F.KPI_SMALL = font(14, weight="bold")
    F.MONO = tkfont.Font(root=root, family=mono, size=10)

    F.DOC = font(10)
    F.DOC_BOLD = font(10, weight="bold")
    F.DOC_ITALIC = font(10, slant="italic")
    F.DOC_H1 = font(18, weight="bold")
    F.DOC_H2 = font(14, weight="bold")
    F.DOC_H3 = font(12, weight="bold")
    F.DOC_H4 = font(10, weight="bold")
