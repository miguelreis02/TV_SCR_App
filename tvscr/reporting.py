"""
Escrita de resultados em disco, com os mesmos nomes de ficheiro e de coluna
dos scripts MATLAB, para que os resultados sejam directamente comparaveis.

Ficheiros produzidos por motor, em ``<outdir>/<motor>/``::

    volume_sweep_<motor>.csv          uma linha por volume
    volume_sweep_<motor>_modos.csv    uma linha por (volume, modo)

e, na raiz, ``resumo_volumes_criticos.csv``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd

from .batch import BatchResult
from .sweep import VolumeSweepResult

__all__ = ["write_sweep_outputs", "write_batch_summary", "write_all"]


def _safe_write(frame: pd.DataFrame, path: Path) -> Optional[Path]:
    """Grava um CSV; avisa (em vez de rebentar) se o ficheiro estiver aberto."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return path
    except OSError as exc:
        import warnings
        warnings.warn(
            f"Nao consegui gravar {path} ({exc}). Feche o ficheiro se estiver aberto.",
            RuntimeWarning, stacklevel=2)
        return None


def write_sweep_outputs(result: VolumeSweepResult,
                        outdir: Union[str, Path],
                        subdir_per_engine: bool = True,
                        subdir: Optional[str] = None) -> dict:
    """Grava os dois CSV de um varrimento. Devolve os caminhos escritos.

    ``subdir`` sobrepoe-se ao nome da subpasta (por omissao, o do motor). E
    util no varrimento de substratos, onde o mesmo motor produz varios
    resultados e o nome tem de os distinguir.
    """
    base = Path(outdir)
    if subdir is not None:
        base = base / subdir
    elif subdir_per_engine:
        base = base / result.engine
    tag = result.engine
    return {
        "sweep": _safe_write(result.to_dataframe(), base / f"volume_sweep_{tag}.csv"),
        "modes": _safe_write(result.modes_dataframe(), base / f"volume_sweep_{tag}_modos.csv"),
    }


def write_batch_summary(batch: BatchResult, outdir: Union[str, Path]) -> Optional[Path]:
    """Grava a tabela-resumo dos volumes criticos."""
    return _safe_write(batch.summary, Path(outdir) / "resumo_volumes_criticos.csv")


def write_all(batch: BatchResult, outdir: Union[str, Path]) -> dict:
    """Grava tudo: os CSV de cada motor e o resumo."""
    paths = {name: write_sweep_outputs(s, outdir)
             for name, s in batch.sweeps.items()}
    paths["__summary__"] = write_batch_summary(batch, outdir)
    return paths
