"""
Varrimento de SUBSTRATOS: comparar pares CPSI / espessura de parede.

O CPSI e a espessura da parede nao vem do ficheiro de inputs -- sao escolha de
projeto, e mudam o reator de duas maneiras opostas:

* mais CPSI (ou parede mais fina) -> canais mais estreitos -> maior area
  geometrica por unidade de volume e melhor transferencia de massa, logo mais
  conversao para o mesmo volume;
* mas tambem menor fraccao de area aberta e maior velocidade intersticial,
  logo menor tempo de residencia -- e parede mais fina significa menos massa
  catalitica por canal.

Este modulo corre o varrimento em volume (com α adaptativo) uma vez por par, e
poe os volumes criticos lado a lado. Nao ha equivalente MATLAB: os scripts
originais tinham CPSI e parede fixos em 46 e 0.43 mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from .alpha_loop import AlphaLoopOptions
from .geometry import SubstrateGeometry
from .operating import EngineCase
from .solver import SolverOptions
from .sweep import VolumeSweepOptions, VolumeSweepResult, volume_sweep
from .targets import EmissionTargets
from .urea import DEFAULT_UREA, UreaSolution

__all__ = ["SubstrateSweepRow", "SubstrateSweepResult", "substrate_sweep",
           "as_substrate"]


def as_substrate(spec: Union[SubstrateGeometry, Dict, Sequence[float]]
                 ) -> SubstrateGeometry:
    """Aceita ``SubstrateGeometry``, ``{"cpsi":.., "wall_thickness_m":..}``
    ou o par ``(cpsi, wall_thickness_m)``."""
    if isinstance(spec, SubstrateGeometry):
        return spec
    if isinstance(spec, dict):
        return SubstrateGeometry(cpsi=float(spec["cpsi"]),
                                 wall_thickness_m=float(spec["wall_thickness_m"]))
    cpsi, wall = spec
    return SubstrateGeometry(cpsi=float(cpsi), wall_thickness_m=float(wall))


@dataclass
class SubstrateSweepRow:
    """Resultado de UM par (motor, substrato)."""

    engine: str
    substrate: SubstrateGeometry
    result: Optional[VolumeSweepResult] = None
    reason: str = ""            # porque nao ha resultado, se for o caso

    @property
    def ok(self) -> bool:
        return self.result is not None and np.isfinite(self.result.critical_volume_m3)

    def as_record(self) -> Dict:
        s = self.substrate
        record = {
            "Engine": self.engine,
            "CPSI": s.cpsi,
            "parede_mm": s.wall_thickness_m * 1e3,
            "dh_mm": s.hydraulic_diameter_m * 1e3,
            "eps_void": s.open_frontal_fraction,
        }
        if self.result is None:
            record.update({
                "V_crit_m3": np.nan, "A_crit_m2": np.nan,
                "NOx_ciclo_gkWh": np.nan, "slip_ciclo_ppm": np.nan,
                "XNO_ciclo_perc": np.nan, "urea_ciclo_Lh": np.nan,
                "observacao": self.reason})
            return record

        crit = self.result.at_critical()
        record.update({
            "V_crit_m3": self.result.critical_volume_m3,
            "A_crit_m2": self.result.critical_area_m2,
            "NOx_ciclo_gkWh": crit["NOx_ciclo_gkWh"],
            "slip_ciclo_ppm": crit["slip_ciclo_ppm"],
            "XNO_ciclo_perc": crit["XNO_ciclo_perc"],
            "urea_ciclo_Lh": crit["urea_ciclo_Lh"],
            "observacao": self.reason,
        })
        return record


@dataclass
class SubstrateSweepResult:
    """Todos os pares (motor, substrato) avaliados."""

    rows: List[SubstrateSweepRow] = field(default_factory=list)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    targets: Optional[EmissionTargets] = None
    options: Optional[VolumeSweepOptions] = None
    alpha_options: Optional[AlphaLoopOptions] = None

    @property
    def engines(self) -> List[str]:
        seen: List[str] = []
        for row in self.rows:
            if row.engine not in seen:
                seen.append(row.engine)
        return seen

    def for_engine(self, engine: str) -> List[SubstrateSweepRow]:
        return [r for r in self.rows if r.engine == engine]

    def best_for(self, engine: str) -> Optional[SubstrateSweepRow]:
        """Par com o MENOR volume critico para esse motor (o mais eficaz)."""
        usable = [r for r in self.for_engine(engine) if r.ok]
        if not usable:
            return None
        return min(usable, key=lambda r: r.result.critical_volume_m3)

    def describe(self) -> str:
        if self.summary.empty:
            return "(sem resultados)"
        return self.summary.to_string(index=False)


# ====================================================================== #
_HEADER = (f"{'motor':>10} {'CPSI':>7} {'parede':>8} {'dh':>7} {'eps':>6} "
           f"{'V_crit':>9} {'A_crit':>9} {'NOx':>9} {'slip':>9} {'ureia':>9}")


def substrate_sweep(cases: Union[EngineCase, Sequence[EngineCase]],
                    substrates: Iterable,
                    targets: Optional[EmissionTargets] = None,
                    options: Optional[VolumeSweepOptions] = None,
                    alpha_options: Optional[AlphaLoopOptions] = None,
                    *,
                    solver_options: Optional[SolverOptions] = None,
                    urea: UreaSolution = DEFAULT_UREA,
                    verbose: bool = True) -> SubstrateSweepResult:
    """Corre o varrimento em volume para cada par (motor, substrato).

    Parameters
    ----------
    cases:
        Um :class:`EngineCase` ou uma sequencia deles.
    substrates:
        Substratos a comparar. Cada elemento pode ser um
        :class:`~tvscr.geometry.SubstrateGeometry`, um dicionario
        ``{"cpsi":.., "wall_thickness_m":..}`` ou o par ``(cpsi, parede)``.
    targets, options, alpha_options:
        Iguais para todos os pares -- so o substrato varia.
    verbose:
        Imprime uma linha por par a medida que vao saindo. O varrimento em
        volume de cada par corre em silencio (senao a saida seria ilegivel).

    Returns
    -------
    SubstrateSweepResult
        Com uma linha por (motor, substrato). Substratos geometricamente
        impossiveis (``dh <= 0``) sao registados com o motivo, em vez de
        rebentarem o varrimento todo.
    """
    case_list: List[EngineCase] = ([cases] if isinstance(cases, EngineCase)
                                   else list(cases))
    if not case_list:
        raise ValueError("substrate_sweep: nenhum motor a correr.")

    subs = [as_substrate(s) for s in substrates]
    if not subs:
        raise ValueError("substrate_sweep: nenhum substrato a comparar.")

    opts = options or VolumeSweepOptions()
    quiet = _quiet(opts)

    if verbose:
        print(f"\n{'=' * 20} VARRIMENTO DE SUBSTRATOS {'=' * 20}")
        print(f" {len(case_list)} motor(es) x {len(subs)} substrato(s) = "
              f"{len(case_list) * len(subs)} varrimentos em volume")
        print("-" * 95)
        print(_HEADER)

    rows: List[SubstrateSweepRow] = []
    for case in case_list:
        for substrate in subs:
            row = SubstrateSweepRow(engine=case.name, substrate=substrate)
            if not substrate.is_valid:
                row.reason = (f"geometria impossivel: dh = "
                              f"{substrate.hydraulic_diameter_m * 1e3:.3f} mm <= 0")
            else:
                row.result = volume_sweep(
                    case.with_substrate(substrate), targets, quiet, alpha_options,
                    solver_options=solver_options, urea=urea)
                if not np.isfinite(row.result.critical_volume_m3):
                    row.reason = "nenhum volume admissivel no intervalo varrido"
            rows.append(row)
            if verbose:
                _print_row(row)

    summary = pd.DataFrame([r.as_record() for r in rows])

    result = SubstrateSweepResult(rows=rows, summary=summary, targets=targets,
                                  options=opts, alpha_options=alpha_options)

    if verbose:
        print("-" * 95)
        for engine in result.engines:
            best = result.best_for(engine)
            if best is None:
                print(f" {engine}: nenhum substrato deu um volume admissivel.")
            else:
                print(f" {engine}: melhor par = CPSI {best.substrate.cpsi:g} / "
                      f"parede {best.substrate.wall_thickness_m * 1e3:.2f} mm  ->  "
                      f"V_crit = {best.result.critical_volume_m3:.3f} m3")
        print("=" * 95)

    return result


def _quiet(options: VolumeSweepOptions) -> VolumeSweepOptions:
    """Copia das opcoes com o varrimento em volume silencioso."""
    from dataclasses import replace
    return replace(options, verbose=False)


def _print_row(row: SubstrateSweepRow) -> None:
    s = row.substrate
    head = (f"{row.engine:>10} {s.cpsi:>7g} {s.wall_thickness_m * 1e3:>7.2f}m "
            f"{s.hydraulic_diameter_m * 1e3:>6.2f}m {s.open_frontal_fraction:>6.3f}")
    if not row.ok:
        print(f"{head}  {row.reason}")
        return
    r = row.result
    crit = r.at_critical()
    print(f"{head} {r.critical_volume_m3:>9.3f} {r.critical_area_m2:>9.3f} "
          f"{crit['NOx_ciclo_gkWh']:>9.4f} {crit['slip_ciclo_ppm']:>9.3f} "
          f"{crit['urea_ciclo_Lh']:>9.2f}")
