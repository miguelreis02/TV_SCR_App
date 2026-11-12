"""
Varrimento de varios motores + tabela-resumo (porte de
``run_all_volume_sweeps_alpha.m``).

Nao ha limite de 5 motores nem nomes fixos: recebe os casos que lhe derem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from .alpha_loop import AlphaLoopOptions
from .operating import EngineCase
from .solver import SolverOptions
from .sweep import VolumeSweepOptions, VolumeSweepResult, volume_sweep
from .targets import EmissionTargets
from .urea import DEFAULT_UREA, UreaSolution

__all__ = ["BatchResult", "run_all_volume_sweeps"]


@dataclass
class BatchResult:
    """Resultados de todos os motores + tabela-resumo dos volumes criticos."""

    sweeps: Dict[str, VolumeSweepResult] = field(default_factory=dict)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    targets: Optional[EmissionTargets] = None
    options: Optional[VolumeSweepOptions] = None
    alpha_options: Optional[AlphaLoopOptions] = None

    def __getitem__(self, key: str) -> VolumeSweepResult:
        return self.sweeps[key]

    def describe(self) -> str:
        return self.summary.to_string(index=False)


def run_all_volume_sweeps(cases: Sequence[EngineCase] | Dict[str, EngineCase],
                          targets: Optional[EmissionTargets] = None,
                          options: Optional[VolumeSweepOptions] = None,
                          alpha_options: Optional[AlphaLoopOptions] = None,
                          *,
                          solver_options: Optional[SolverOptions] = None,
                          urea: UreaSolution = DEFAULT_UREA) -> BatchResult:
    """Corre o varrimento em volume para varios motores.

    Parameters
    ----------
    cases:
        Sequencia (ou dicionario ``nome -> caso``) de :class:`EngineCase`.
    targets, options, alpha_options:
        Iguais para todos os motores. Para cenarios diferentes por motor,
        chame :func:`~tvscr.sweep.volume_sweep` directamente.
    """
    case_list: List[EngineCase] = (list(cases.values())
                                   if isinstance(cases, dict) else list(cases))
    if not case_list:
        raise ValueError("run_all_volume_sweeps: nenhum motor a correr.")

    sweeps: Dict[str, VolumeSweepResult] = {}
    rows = []
    for case in case_list:
        s = volume_sweep(case, targets, options, alpha_options,
                         solver_options=solver_options, urea=urea)
        sweeps[case.name] = s
        rows.append(s.summary_row())

    summary = pd.DataFrame(rows)

    verbose = options.verbose if options is not None else True
    if verbose:
        print("\n" + "=" * 27 + " RESUMO: VOLUMES CRITICOS " + "=" * 27)
        print(summary.to_string(index=False))
        print("=" * 79)

    return BatchResult(sweeps=sweeps, summary=summary, targets=targets,
                       options=options, alpha_options=alpha_options)
