"""
Paleta e tipos de letra da interface.

Fundo verde, campos brancos. Tudo o que e cor ou fonte esta aqui: para mudar o
aspecto da aplicacao nao e preciso tocar no resto da interface.
"""

from __future__ import annotations

import tkinter.font as tkfont

__all__ = ["C", "F", "init_fonts"]


class C:
    """Cores."""

    BG = "#0F4C2E"          # verde escuro -- fundo da janela
    BG_PANEL = "#14603A"    # verde medio  -- painel de uma seccao
    BG_HEADER = "#0A3721"   # verde muito escuro -- barra de titulo
    BORDER = "#2E8B57"      # verde claro  -- contornos

    FIELD_BG = "#FFFFFF"    # campos de input
    FIELD_FG = "#10281A"
    FIELD_DISABLED = "#DCE8E0"

    TEXT = "#FFFFFF"        # texto sobre verde
    TEXT_DIM = "#BFE0CC"    # unidades, notas
    TITLE = "#FFFFFF"

    TAB_BG = "#14603A"          # separador inativo
    TAB_FG = "#BFE0CC"
    TAB_HOVER = "#1B7A49"
    TAB_ACTIVE_BG = "#FFFFFF"   # separador activo: campo branco, como os inputs
    TAB_ACTIVE_FG = "#0F4C2E"

    BTN_BG = "#FFFFFF"      # botoes secundarios
    BTN_FG = "#0F4C2E"
    BTN_ACTIVE = "#E3F0E8"

    RUN_BG = "#F2C14E"      # botao principal (correr)
    RUN_FG = "#0A3721"
    RUN_ACTIVE = "#FFD778"

    LOG_BG = "#FFFFFF"      # consola de resultados
    LOG_FG = "#10281A"
    LOG_ERR = "#B00020"
    LOG_OK = "#0F6B3C"

    ERROR_FIELD = "#FFD6D6"  # campo com valor invalido


class F:
    """Tipos de letra (preenchidos por :func:`init_fonts`)."""

    BASE = None
    BOLD = None
    SMALL = None
    TITLE = None
    SUBTITLE = None
    MONO = None


def init_fonts(root) -> None:
    """Cria os tipos de letra. Tem de ser chamada depois de existir um ``Tk``."""
    family = "Segoe UI"
    available = set(tkfont.families(root))
    if family not in available:
        family = "TkDefaultFont"
    mono = "Consolas" if "Consolas" in available else "TkFixedFont"

    F.BASE = tkfont.Font(root=root, family=family, size=9)
    F.BOLD = tkfont.Font(root=root, family=family, size=9, weight="bold")
    F.SMALL = tkfont.Font(root=root, family=family, size=8)
    F.TITLE = tkfont.Font(root=root, family=family, size=15, weight="bold")
    F.SUBTITLE = tkfont.Font(root=root, family=family, size=9)
    F.MONO = tkfont.Font(root=root, family=mono, size=9)
