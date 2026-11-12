"""Permite ``python -m tvscr_ui``."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr_ui import launch

if __name__ == "__main__":
    launch()
