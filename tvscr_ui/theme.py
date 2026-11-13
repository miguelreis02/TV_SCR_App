"""
Paleta e tipos de letra da interface.

Fundo verde, campos brancos; os resultados aparecem numa folha branca. Tudo o
que e cor ou fonte esta aqui: para mudar o aspecto da aplicacao nao e preciso
tocar no resto da interface.
"""

from __future__ import annotations

import tkinter.font as tkfont

__all__ = ["C", "F", "init_fonts"]


class C:
    """Cores."""

    BG = "#0F4C2E"          # verde escuro -- fundo da janela e das paginas
    BG_PANEL = "#14603A"    # verde medio  -- cartao de uma seccao
    BG_HEADER = "#0A3721"   # verde muito escuro -- barra de titulo
    BORDER = "#2E8B57"      # verde claro  -- contornos

    FIELD_BG = "#FFFFFF"    # campos de input
    FIELD_FG = "#10281A"
    FIELD_DISABLED = "#DCE8E0"

    TEXT = "#FFFFFF"        # texto sobre verde
    TEXT_DIM = "#BFE0CC"    # unidades, notas
    TITLE = "#FFFFFF"

    # --- navegacao lateral (separadores verticais) ---
    NAV_BG = "#0A3721"          # igual ao cabecalho: os dois formam um "L"
    NAV_FG = "#D6EBDF"
    NAV_GROUP = "#8FBFA4"       # titulo de um grupo de separadores
    NAV_HOVER = "#14603A"
    NAV_ACTIVE_BG = "#1B7A49"
    NAV_ACTIVE_FG = "#FFFFFF"
    ACCENT = "#F2C14E"          # marca do separador activo (cor do botao correr)
    FLAG = "#FF8A80"            # separador com um campo invalido

    # --- separadores horizontais do painel de resultados ---
    TAB_BG = "#14603A"          # separador inativo
    TAB_FG = "#BFE0CC"
    TAB_HOVER = "#1B7A49"
    TAB_ACTIVE_BG = "#FFFFFF"   # separador activo: branco, como a folha
    TAB_ACTIVE_FG = "#0F4C2E"

    BTN_BG = "#FFFFFF"      # botoes secundarios
    BTN_FG = "#0F4C2E"
    BTN_ACTIVE = "#E3F0E8"

    GHOST_BG = "#14603A"    # botoes discretos sobre verde (navegacao, cenario)
    GHOST_FG = "#FFFFFF"
    GHOST_ACTIVE = "#1B7A49"
    GHOST_DISABLED = "#6FA588"

    RUN_BG = "#F2C14E"      # botao principal (correr)
    RUN_FG = "#0A3721"
    RUN_ACTIVE = "#FFD778"

    LOG_BG = "#FFFFFF"      # consola de resultados
    LOG_FG = "#10281A"
    LOG_ERR = "#B00020"
    LOG_OK = "#0F6B3C"

    # --- folha de resultados (texto escuro sobre branco) ---
    SHEET_BG = "#FFFFFF"
    SHEET_FG = "#10281A"
    SHEET_DIM = "#587566"       # legendas e notas
    TILE_BG = "#F1F7F3"         # mosaico de um indicador
    TILE_BORDER = "#CFE3D7"
    TILE_KEY_BG = "#E3F0E8"     # mosaico principal (volume critico)
    TILE_ERR_BG = "#FDECEC"
    TILE_ERR_BORDER = "#F1B5B5"
    HEAD_BG = "#E3F0E8"         # cabecalho das tabelas
    ROW_CRIT = "#FFF1C2"        # linha do volume critico
    SCROLL = "#C5DCCF"          # cursor das barras de rolamento
    SCROLL_TROUGH = "#EEF5F1"

    ERROR_FIELD = "#FFD6D6"  # campo com valor invalido


class F:
    """Tipos de letra (preenchidos por :func:`init_fonts`)."""

    BASE = None
    BOLD = None
    SMALL = None
    SMALL_BOLD = None
    TITLE = None
    SUBTITLE = None
    PAGE_TITLE = None
    KPI = None
    KPI_SMALL = None
    MONO = None


def init_fonts(root) -> None:
    """Cria os tipos de letra. Tem de ser chamada depois de existir um ``Tk``."""
    family = "Segoe UI"
    available = set(tkfont.families(root))
    if family not in available:
        family = "TkDefaultFont"
    mono = "Consolas" if "Consolas" in available else "TkFixedFont"

    F.BASE = tkfont.Font(root=root, family=family, size=10)
    F.BOLD = tkfont.Font(root=root, family=family, size=10, weight="bold")
    F.SMALL = tkfont.Font(root=root, family=family, size=9)
    F.SMALL_BOLD = tkfont.Font(root=root, family=family, size=8, weight="bold")
    F.TITLE = tkfont.Font(root=root, family=family, size=15, weight="bold")
    F.SUBTITLE = tkfont.Font(root=root, family=family, size=10)
    F.PAGE_TITLE = tkfont.Font(root=root, family=family, size=13, weight="bold")
    F.KPI = tkfont.Font(root=root, family=family, size=20, weight="bold")
    F.KPI_SMALL = tkfont.Font(root=root, family=family, size=14, weight="bold")
    F.MONO = tkfont.Font(root=root, family=mono, size=10)
