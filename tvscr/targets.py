"""
Alvos de emissao usados pelo loop de alpha e pelo varrimento geometrico.

Dois niveis, como no MATLAB:

============  =========================  =========================
              por MODO                   ciclo PONDERADO
============  =========================  =========================
NO_out        <= ``mode_NO_frac`` x Tier  <= ``cycle_NO_frac`` x Tier
NH3 slip      <= ``mode_slip_ppm``        <= ``cycle_slip_ppm``
============  =========================  =========================

As fraccoes sao do limite regulamentar do motor (Tier III por omissao), pelo
que os alvos absolutos so ficam definidos quando ligados a um
:class:`~tvscr.operating.EngineCase` -- e o que :meth:`EmissionTargets.resolve`
faz.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

__all__ = ["EmissionTargets", "ResolvedTargets"]


@dataclass(frozen=True)
class EmissionTargets:
    """Alvos relativos (fraccoes do limite regulamentar) e de slip absoluto."""

    cycle_NO_frac: float = 0.60
    mode_NO_frac: float = 0.80
    cycle_slip_ppm: float = 10.0
    mode_slip_ppm: float = 20.0

    def resolve(self, nox_limit_gkWh: float) -> "ResolvedTargets":
        """Converte as fraccoes em alvos absolutos [g/kWh]."""
        return ResolvedTargets(
            cycle_NO_gkWh=self.cycle_NO_frac * nox_limit_gkWh,
            mode_NO_gkWh=self.mode_NO_frac * nox_limit_gkWh,
            cycle_slip_ppm=self.cycle_slip_ppm,
            mode_slip_ppm=self.mode_slip_ppm,
            nox_limit_gkWh=nox_limit_gkWh,
            cycle_NO_frac=self.cycle_NO_frac,
            mode_NO_frac=self.mode_NO_frac,
        )


@dataclass(frozen=True)
class ResolvedTargets:
    """Alvos absolutos, ja ligados ao limite regulamentar de um motor."""

    cycle_NO_gkWh: float
    mode_NO_gkWh: float
    cycle_slip_ppm: float
    mode_slip_ppm: float
    nox_limit_gkWh: float
    cycle_NO_frac: float
    mode_NO_frac: float

    def describe(self) -> str:
        return (f"ciclo NOx<={self.cycle_NO_gkWh:.4f} ({self.cycle_NO_frac:.0%})  "
                f"slip<={self.cycle_slip_ppm:.1f} ppm | "
                f"modo NOx<={self.mode_NO_gkWh:.4f} ({self.mode_NO_frac:.0%})  "
                f"slip<={self.mode_slip_ppm:.1f} ppm")

    def with_overrides(self, **kwargs) -> "ResolvedTargets":
        return replace(self, **kwargs)
