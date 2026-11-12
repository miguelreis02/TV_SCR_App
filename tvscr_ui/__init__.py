"""
tvscr_ui -- interface grafica da aplicacao de dimensionamento SCR.

Separada de proposito do pacote de calculo :mod:`tvscr`: a interface so recolhe
inputs e mostra resultados; todo o modelo vive em ``tvscr``. Trocar de
interface (web, linha de comandos, outra biblioteca) nao obriga a tocar no
calculo.

    python app.py            # a partir da raiz do projecto
    python -m tvscr_ui
"""

from __future__ import annotations

from .main_window import MainWindow, launch

__all__ = ["MainWindow", "launch"]
