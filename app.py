"""
Ponto de entrada da aplicacao TV SCR.

    python app.py

Abre a interface grafica. Todo o calculo esta no pacote ``tvscr``; a interface
(``tvscr_ui``) so recolhe os inputs e mostra os resultados.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("A interface precisa do tkinter, que nao esta disponivel nesta\n"
              "instalacao de Python. Instale-o (no Windows vem com o instalador\n"
              "oficial) ou use a biblioteca directamente:\n\n"
              "    from tvscr import EngineDataset, volume_sweep\n\n"
              "Ver os exemplos em examples/.", file=sys.stderr)
        return 1

    missing = [name for name in ("numpy", "scipy", "pandas")
               if not _has(name)]
    if missing:
        print(f"Faltam dependencias: {', '.join(missing)}\n"
              f"Instale com:  pip install -r requirements.txt", file=sys.stderr)
        return 1

    from tvscr_ui import launch
    launch()
    return 0


def _has(module: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(module) is not None


if __name__ == "__main__":
    raise SystemExit(main())
