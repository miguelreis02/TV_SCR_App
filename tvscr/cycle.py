"""
Ciclo de ensaio completo numa geometria (porte de ``run_D2_geom.m``).

Corre o solver 1-D uma vez por modo, converte o NO a saida em NOx especifico
[g/kWh] e pondera o ciclo. Propaga os diagnosticos numericos do solver para
que os pontos nao fiaveis possam ser excluidos da interpretacao.

Nao ha nada especifico do ciclo D2 aqui: o numero de modos e os pesos vem do
:class:`~tvscr.operating.EngineCase`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Union

import numpy as np

from .geometry import ReactorGeometry
from .kinetics import KineticTuning
from .numerics import interp1_linear
from .operating import EngineCase, specific_nox_gkwh
from .solver import PointResult, SolverOptions, solve_point
from .urea import DEFAULT_UREA, UreaSolution, urea_flow_Lh

__all__ = ["CycleResult", "run_cycle"]


@dataclass
class CycleResult:
    """Resultado do ciclo completo para UMA geometria e UM vector de alpha."""

    geometry: ReactorGeometry
    geometry_ok: bool
    alpha: np.ndarray                 # (N,) alpha usado em cada modo

    # --- por modo ---
    load_pct: np.ndarray
    weight: np.ndarray
    X_NO: np.ndarray                  # [%]
    slip_ppm: np.ndarray              # [ppm]
    NO_out_ppm: np.ndarray            # [ppm]
    NO_gkWh: np.ndarray               # [g/kWh]
    urea_Lh: np.ndarray               # [L/h]
    tau_s: np.ndarray
    AV_Nmh: np.ndarray
    eta: np.ndarray                   # eficacia media do NO (Thiele)

    # --- diagnostico numerico por modo ---
    max_resnorm: np.ndarray
    any_active: np.ndarray
    floor_active: np.ndarray
    valid_mode: np.ndarray
    valid_strict_mode: np.ndarray

    # --- ciclo ponderado ---
    NO_at_cycle: np.ndarray           # grandezas interpoladas nas cargas do ciclo
    slip_at_cycle: np.ndarray
    XNO_at_cycle: np.ndarray
    NO_cycle: float                   # NOx especifico ponderado  [g/kWh]
    slip_cycle: float                 # slip ponderado            [ppm]
    XNO_cycle: float                  # conversao ponderada       [%]
    urea_cycle: float                 # ureia ponderada           [L/h]

    # --- conformidade ---
    nox_limit_gkWh: float
    compliant: bool
    margin_gkWh: float
    worst_mode_NO: float
    worst_mode_index: int
    all_modes_ok: bool

    # --- agregados de validade ---
    valid_cycle: bool
    valid_strict_cycle: bool
    floor_active_any: bool
    max_resnorm_cycle: float

    points: List[Optional[PointResult]] = field(default_factory=list)

    @property
    def n_modes(self) -> int:
        return int(self.alpha.size)

    def describe(self) -> str:
        return (f"NOx_ciclo={self.NO_cycle:.4f} g/kWh (limite {self.nox_limit_gkWh:.4f})  "
                f"slip_ciclo={self.slip_cycle:.3f} ppm  "
                f"X_NO_ciclo={self.XNO_cycle:.2f} %  "
                f"ureia={self.urea_cycle:.2f} L/h  valid={self.valid_cycle}")


def _invalid_cycle(case: EngineCase, geometry: ReactorGeometry,
                   alpha: np.ndarray) -> CycleResult:
    """Resultado degenerado quando a geometria nao e admissivel (``dh <= 0``)."""
    n = case.n_modes
    nan = np.full(n, np.nan)
    return CycleResult(
        geometry=geometry, geometry_ok=False, alpha=alpha,
        load_pct=case.load_pct, weight=case.weight,
        X_NO=nan.copy(), slip_ppm=nan.copy(), NO_out_ppm=nan.copy(),
        NO_gkWh=nan.copy(), urea_Lh=nan.copy(), tau_s=nan.copy(),
        AV_Nmh=nan.copy(), eta=nan.copy(),
        max_resnorm=nan.copy(), any_active=np.zeros(n, dtype=bool),
        floor_active=np.zeros(n, dtype=bool),
        valid_mode=np.zeros(n, dtype=bool),
        valid_strict_mode=np.zeros(n, dtype=bool),
        NO_at_cycle=nan.copy(), slip_at_cycle=nan.copy(), XNO_at_cycle=nan.copy(),
        NO_cycle=float("nan"), slip_cycle=float("nan"),
        XNO_cycle=float("nan"), urea_cycle=float("nan"),
        nox_limit_gkWh=float(case.nox_limit_gkWh), compliant=False,
        margin_gkWh=float("nan"), worst_mode_NO=float("nan"),
        worst_mode_index=-1, all_modes_ok=False,
        valid_cycle=False, valid_strict_cycle=False,
        floor_active_any=False, max_resnorm_cycle=float("nan"),
        points=[None] * n,
    )


def run_cycle(case: EngineCase,
              geometry: Optional[ReactorGeometry] = None,
              alpha: Union[float, Sequence[float], np.ndarray, None] = None,
              *,
              tuning: Optional[KineticTuning] = None,
              options: Optional[SolverOptions] = None,
              urea: UreaSolution = DEFAULT_UREA,
              kads: Optional[np.ndarray] = None,
              kNO: Optional[np.ndarray] = None,
              keep_points: bool = False) -> CycleResult:
    """Corre o ciclo de ensaio completo numa geometria.

    Parameters
    ----------
    case:
        Motor + ciclo + cinetica.
    geometry:
        Geometria a avaliar. Por omissao, a instalada em ``case.geometry``.
        O fouling da geometria e aplicado a area frontal aqui (o solver
        recebe ja a area efetiva).
    alpha:
        Escalar (igual em todos os modos) ou um valor por modo. Por omissao usa
        ``case.alpha_calibrated``; se este nao existir, e obrigatorio.
    tuning:
        Multiplicadores de calibracao da cinetica.
    kads, kNO:
        Constantes agrupadas ja avaliadas por modo. Se dadas, evitam repetir
        Arrhenius em varrimentos com muitas chamadas.
    keep_points:
        Guarda o :class:`~tvscr.solver.PointResult` completo de cada modo
        (perfis axiais incluidos). Desligado por omissao, por memoria.
    """
    geom = geometry if geometry is not None else case.geometry
    n = case.n_modes

    if alpha is None:
        if case.alpha_calibrated is None:
            raise ValueError(
                "run_cycle: e preciso um alpha (argumento) ou "
                "case.alpha_calibrated definido.")
        alpha_vec = np.asarray(case.alpha_calibrated, dtype=float).copy()
    else:
        alpha_vec = np.atleast_1d(np.asarray(alpha, dtype=float)).ravel()
        if alpha_vec.size == 1:
            alpha_vec = np.full(n, float(alpha_vec[0]))
    if alpha_vec.size != n:
        raise ValueError(f"alpha tem {alpha_vec.size} valores mas o ciclo tem {n} modos.")

    if not geom.substrate.is_valid:
        return _invalid_cycle(case, geom, alpha_vec)

    kin = case.kinetics if tuning is None else case.kinetics.with_tuning(tuning)
    kads_vec = np.asarray(kin.kads_at(case.T_K), dtype=float) if kads is None \
        else np.asarray(kads, dtype=float)
    kNO_vec = np.asarray(kin.kNO_at(case.T_K), dtype=float) if kNO is None \
        else np.asarray(kNO, dtype=float)

    A_eff = geom.effective_frontal_area_m2
    mdot = case.mass_flow_kgs
    T_K = case.T_K
    NO_in = case.NO_in_ppm

    X_NO = np.zeros(n)
    slip = np.zeros(n)
    tau = np.zeros(n)
    AV = np.zeros(n)
    eta = np.zeros(n)
    resnorm = np.zeros(n)
    active = np.zeros(n, dtype=bool)
    floor_a = np.zeros(n, dtype=bool)
    ok_mode = np.zeros(n, dtype=bool)
    ok_strict = np.zeros(n, dtype=bool)
    points: List[Optional[PointResult]] = [None] * n

    for k in range(n):
        p = solve_point(
            T_K=float(T_K[k]), pressure_Pa=case.pressure_Pa,
            mass_flow_kgs=float(mdot[k]), frontal_area_m2=A_eff,
            NO_in_ppm=float(NO_in[k]), alpha=float(alpha_vec[k]),
            length_m=geom.length_m, substrate=geom.substrate,
            kinetics=kin, kads=float(kads_vec[k]), kNO=float(kNO_vec[k]),
            options=options)

        X_NO[k] = p.X_NO
        slip[k] = p.slip_ppm
        tau[k] = p.tau_s
        AV[k] = p.AV_Nmh
        eta[k] = p.etaO_bar
        resnorm[k] = p.max_resnorm
        active[k] = p.any_active
        floor_a[k] = p.floor_active
        ok_mode[k] = p.valid
        ok_strict[k] = p.valid_strict
        if keep_points:
            points[k] = p

    NO_out_ppm = NO_in * (1.0 - X_NO / 100.0)
    NO_gkWh = specific_nox_gkwh(NO_out_ppm, mdot, case.power_kW,
                                kin.gas.M_NO_g_mol, kin.gas.M_exhaust_g_mol)
    urea_Lh = urea_flow_Lh(alpha_vec, NO_in, mdot, urea)

    # ---- ponderacao do ciclo ------------------------------------------- #
    loads = case.load_pct                    # ja ordenado por carga crescente
    w = case.weight
    NO_at = interp1_linear(loads, NO_gkWh, loads)
    slip_at = interp1_linear(loads, slip, loads)
    XNO_at = interp1_linear(loads, X_NO, loads)
    wsum = float(np.sum(w))
    NO_cycle = float(np.sum(w * NO_at) / wsum)
    slip_cycle = float(np.sum(w * slip_at) / wsum)
    XNO_cycle = float(np.sum(w * X_NO) / wsum)
    urea_cycle = float(np.sum(w * urea_Lh) / wsum)

    limit = float(case.nox_limit_gkWh)
    worst_idx = int(np.argmax(NO_at))

    return CycleResult(
        geometry=geom, geometry_ok=True, alpha=alpha_vec,
        load_pct=loads, weight=w,
        X_NO=X_NO, slip_ppm=slip, NO_out_ppm=NO_out_ppm, NO_gkWh=NO_gkWh,
        urea_Lh=urea_Lh, tau_s=tau, AV_Nmh=AV, eta=eta,
        max_resnorm=resnorm, any_active=active, floor_active=floor_a,
        valid_mode=ok_mode, valid_strict_mode=ok_strict,
        NO_at_cycle=NO_at, slip_at_cycle=slip_at, XNO_at_cycle=XNO_at,
        NO_cycle=NO_cycle, slip_cycle=slip_cycle,
        XNO_cycle=XNO_cycle, urea_cycle=urea_cycle,
        nox_limit_gkWh=limit,
        compliant=bool(NO_cycle <= limit),
        margin_gkWh=limit - NO_cycle,
        worst_mode_NO=float(NO_at[worst_idx]),
        worst_mode_index=worst_idx,
        all_modes_ok=bool(np.all(NO_at <= limit)),
        valid_cycle=bool(np.all(ok_mode)),
        valid_strict_cycle=bool(np.all(ok_strict)),
        floor_active_any=bool(np.any(floor_a)),
        max_resnorm_cycle=float(np.max(resnorm)),
        points=points,
    )
