"""
Varrimento geometrico com alpha adaptativo (porte de ``run_volume_sweep_alpha.m``).

Substitui o varrimento ``L x A`` com alpha FIXO por um varrimento em VOLUME
com alpha ADAPTATIVO: para cada volume, o loop de alpha procura o vector que
cumpre os alvos. O varrimento desce em volume ate a geometria se tornar
inadmissivel (Situacao 4) -- esse e o **volume critico** do motor.

Porque muda a pergunta
----------------------
Com alpha congelado, a pergunta e "o que acontece a este reator se o encolher
sem mexer no doseamento". Com alpha adaptativo e "qual e o menor reator
viavel", porque um reator menor seria, na pratica, operado com outro
doseamento. O alpha reage a geometria, sujeito aos limites de emissao e slip.

Convencao geometrica
--------------------
``L`` fica FIXO (por omissao, o comprimento instalado) e ``A = V / L``. E a
convencao do caso pratico, onde os motores diferem so na area frontal para o
mesmo comprimento. O comprimento fixo e um input (``options.length_m``), nao
uma constante do codigo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

import numpy as np
import pandas as pd

from .alpha_loop import (AlphaLoopOptions, AlphaLoopResult, Situation,
                         alpha_event_loop)
from .geometry import ReactorGeometry
from .kinetics import KineticTuning
from .numerics import matlab_colon
from .operating import EngineCase
from .solver import SolverOptions
from .targets import EmissionTargets, ResolvedTargets
from .urea import DEFAULT_UREA, UreaSolution, urea_flow_Lh

__all__ = ["VolumeSweepOptions", "GeometryEvaluation", "VolumeSweepResult",
           "evaluate_geometry", "volume_sweep"]


# ====================================================================== #
#  Opcoes
# ====================================================================== #
@dataclass
class VolumeSweepOptions:
    """Opcoes do varrimento em volume.

    Parameters
    ----------
    volume_max_m3:
        MAIOR volume a considerar; o varrimento comeca aqui e desce. Se for
        ``None``, usa o volume da geometria de referencia do caso.
    volume_step_m3:
        Decremento de volume (valor positivo; o varrimento e descendente).
    volume_min_m3:
        Piso do varrimento.
    volumes_m3:
        Lista explicita de volumes a avaliar. Se dada, ignora os tres campos
        acima (util para malhas nao uniformes ou para repetir um varrimento).
    length_m:
        Comprimento fixo do monolito. ``None`` = usa o instalado no caso.
    refine:
        Bisseccao em V entre o ultimo volume admissivel e o primeiro que
        falhou, para afinar o volume critico alem da resolucao do passo.
    refine_tol_m3:
        Tolerancia da bisseccao em V.
    fouling, aging_KK0:
        Sobrepoem-se aos valores do caso, se dados. Os scripts MATLAB corriam
        por omissao com ``fouling = 0.15`` e ``KK0 = 0.80``; aqui nao ha
        omissao escondida -- se quiser esse cenario, passe-o explicitamente.
    tuning:
        Multiplicadores de calibracao da cinetica (``opt.ktune``).
    """

    volume_max_m3: Optional[float] = None
    volume_step_m3: float = 0.20
    volume_min_m3: float = 0.20
    volumes_m3: Optional[Sequence[float]] = None
    length_m: Optional[float] = None
    refine: bool = True
    refine_tol_m3: float = 0.02
    fouling: Optional[float] = None
    aging_KK0: Optional[float] = None
    tuning: KineticTuning = field(default_factory=KineticTuning)
    verbose: bool = True


# ====================================================================== #
#  Avaliacao de UMA geometria
# ====================================================================== #
@dataclass
class GeometryEvaluation:
    """Resultado do loop de alpha numa geometria, ja pos-processado."""

    volume_m3: float
    area_m2: float
    geometry: ReactorGeometry
    situation: Situation
    ok: bool
    n_iter: int
    why: str
    alpha: np.ndarray
    X_NO: np.ndarray
    NO_gkWh: np.ndarray
    slip_ppm: np.ndarray
    urea_Lh: np.ndarray
    tau_s: np.ndarray
    AV_Nmh: np.ndarray
    eta: np.ndarray
    sit_mode: np.ndarray
    NO_cycle: float
    slip_cycle: float
    XNO_cycle: float
    urea_cycle: float
    valid: bool
    loop: Optional[AlphaLoopResult] = None


def evaluate_geometry(case: EngineCase,
                      geometry: ReactorGeometry,
                      targets: ResolvedTargets,
                      alpha_options: Optional[AlphaLoopOptions] = None,
                      *,
                      tuning: Optional[KineticTuning] = None,
                      solver_options: Optional[SolverOptions] = None,
                      urea: UreaSolution = DEFAULT_UREA,
                      kads: Optional[np.ndarray] = None,
                      kNO: Optional[np.ndarray] = None,
                      keep_loop: bool = False) -> GeometryEvaluation:
    """Corre o loop de alpha numa geometria e empacota o resultado."""
    loop = alpha_event_loop(case, geometry, targets, alpha_options,
                            tuning=tuning, solver_options=solver_options,
                            urea=urea, kads=kads, kNO=kNO)
    r = loop.cycle
    n = case.n_modes
    nan = np.full(n, np.nan)

    if r is None or not r.geometry_ok:
        return GeometryEvaluation(
            volume_m3=geometry.volume_m3, area_m2=geometry.frontal_area_m2,
            geometry=geometry, situation=loop.situation, ok=loop.ok,
            n_iter=loop.n_iter, why=loop.why, alpha=loop.alpha.copy(),
            X_NO=nan.copy(), NO_gkWh=nan.copy(), slip_ppm=nan.copy(),
            urea_Lh=nan.copy(), tau_s=nan.copy(), AV_Nmh=nan.copy(),
            eta=nan.copy(), sit_mode=np.full(n, np.nan),
            NO_cycle=float("nan"), slip_cycle=float("nan"),
            XNO_cycle=float("nan"), urea_cycle=float("nan"),
            valid=False, loop=loop if keep_loop else None)

    # A ureia usa o alpha DEVOLVIDO pelo loop (que pode diferir do avaliado em
    # r quando o fecho ocorre depois de uma actualizacao) -- igual ao MATLAB.
    urea_Lh = urea_flow_Lh(loop.alpha, case.NO_in_ppm, case.mass_flow_kgs, urea)
    w = case.weight
    wsum = float(np.sum(w))

    return GeometryEvaluation(
        volume_m3=geometry.volume_m3, area_m2=geometry.frontal_area_m2,
        geometry=geometry, situation=loop.situation, ok=loop.ok,
        n_iter=loop.n_iter, why=loop.why, alpha=loop.alpha.copy(),
        X_NO=r.X_NO.copy(), NO_gkWh=r.NO_gkWh.copy(), slip_ppm=r.slip_ppm.copy(),
        urea_Lh=urea_Lh, tau_s=r.tau_s.copy(), AV_Nmh=r.AV_Nmh.copy(),
        eta=r.eta.copy(), sit_mode=loop.sit_mode.copy(),
        NO_cycle=r.NO_cycle, slip_cycle=r.slip_cycle,
        XNO_cycle=float(np.sum(w * r.X_NO) / wsum),
        urea_cycle=float(np.sum(w * urea_Lh) / wsum),
        valid=r.valid_cycle, loop=loop if keep_loop else None)


# ====================================================================== #
#  Resultado do varrimento
# ====================================================================== #
@dataclass
class VolumeSweepResult:
    """Varrimento completo de um motor."""

    engine: str
    length_m: float
    volume_max_m3: float          # maior volume considerado no varrimento
    nox_limit_gkWh: float
    targets: ResolvedTargets
    load_pct: np.ndarray
    weight: np.ndarray
    required_conversion_pct: np.ndarray

    # --- por volume (nV,) ---
    volume_m3: np.ndarray
    area_m2: np.ndarray
    situation: np.ndarray
    ok: np.ndarray
    n_iter: np.ndarray
    phase: np.ndarray            # 1 = varrimento, 2 = refinamento
    NO_cycle: np.ndarray
    slip_cycle: np.ndarray
    XNO_cycle: np.ndarray
    urea_cycle: np.ndarray
    valid: np.ndarray
    why: List[str]

    # --- por (volume, modo) (nV, nM) ---
    alpha: np.ndarray
    X_NO: np.ndarray
    NO_gkWh: np.ndarray
    slip_ppm: np.ndarray
    urea_Lh: np.ndarray
    tau_s: np.ndarray
    AV_Nmh: np.ndarray
    eta: np.ndarray
    sit_mode: np.ndarray

    # --- conclusoes ---
    critical_volume_m3: float
    failed_volume_m3: float
    critical_area_m2: float

    options: Optional[VolumeSweepOptions] = None
    alpha_options: Optional[AlphaLoopOptions] = None

    # ------------------------------------------------------------------ #
    @property
    def critical_index(self) -> int:
        """Indice da linha correspondente ao volume critico (-1 se nao houver)."""
        if not np.isfinite(self.critical_volume_m3) or self.volume_m3.size == 0:
            return -1
        return int(np.argmin(np.abs(self.volume_m3 - self.critical_volume_m3)))

    def at_volume(self, volume_m3: float) -> dict:
        """Valores do ciclo no volume avaliado mais proximo do pedido."""
        j = int(np.argmin(np.abs(self.volume_m3 - volume_m3)))
        return self._row(j)

    def at_critical(self) -> dict:
        """Ponto de operacao NO VOLUME CRITICO -- o reator que se vai instalar."""
        return self._row(self.critical_index)

    def _row(self, j: int) -> dict:
        if j < 0:
            nan = float("nan")
            return {"V_m3": nan, "A_m2": nan, "NOx_ciclo_gkWh": nan,
                    "slip_ciclo_ppm": nan, "XNO_ciclo_perc": nan,
                    "urea_ciclo_Lh": nan, "alpha": np.full(self.load_pct.size, nan)}
        return {
            "V_m3": float(self.volume_m3[j]),
            "A_m2": float(self.area_m2[j]),
            "NOx_ciclo_gkWh": float(self.NO_cycle[j]),
            "slip_ciclo_ppm": float(self.slip_cycle[j]),
            "XNO_ciclo_perc": float(self.XNO_cycle[j]),
            "urea_ciclo_Lh": float(self.urea_cycle[j]),
            "alpha": self.alpha[j, :].copy(),
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Uma linha por volume (equivalente a ``volume_sweep_DG<k>.csv``)."""
        return pd.DataFrame({
            "V_m3": self.volume_m3,
            "A_m2": self.area_m2,
            "situacao": self.situation,
            "admissivel": self.ok.astype(int),
            "NOx_ciclo_gkWh": self.NO_cycle,
            "slip_ciclo_ppm": self.slip_cycle,
            "XNO_ciclo_perc": self.XNO_cycle,
            "urea_ciclo_Lh": self.urea_cycle,
            "n_iter": self.n_iter,
            "fase": self.phase,
        })

    def modes_dataframe(self) -> pd.DataFrame:
        """Uma linha por (volume, modo) (equivalente ao ``..._modos.csv``).

        A ordem das linhas segue a do MATLAB: coluna a coluna (todos os
        volumes do modo 1, depois do modo 2, ...), porque o ``T2 = table(...)``
        original lineariza matrizes por colunas.
        """
        nV, nM = self.alpha.shape
        return pd.DataFrame({
            "V_m3": np.tile(self.volume_m3, nM),
            "Load_perc": np.repeat(self.load_pct, nV),
            "Weight_perc": np.repeat(self.weight, nV),
            "alpha": self.alpha.ravel(order="F"),
            "XNO_perc": self.X_NO.ravel(order="F"),
            "NO_gkWh": self.NO_gkWh.ravel(order="F"),
            "slip_ppm": self.slip_ppm.ravel(order="F"),
            "urea_Lh": self.urea_Lh.ravel(order="F"),
            "tau_s": self.tau_s.ravel(order="F"),
            "AV_Nmh": self.AV_Nmh.ravel(order="F"),
            "eta": self.eta.ravel(order="F"),
            "situacao_modo": self.sit_mode.ravel(order="F"),
        })

    def summary_row(self) -> dict:
        """Uma linha de resumo, com o ciclo avaliado NO VOLUME CRITICO."""
        crit = self.at_critical()
        return {
            "Engine": self.engine,
            "L_m": self.length_m,
            "V_crit_m3": self.critical_volume_m3,
            "A_crit_m2": self.critical_area_m2,
            "NOx_ciclo_gkWh": crit["NOx_ciclo_gkWh"],
            "slip_ciclo_ppm": crit["slip_ciclo_ppm"],
            "XNO_ciclo_perc": crit["XNO_ciclo_perc"],
            "urea_ciclo_Lh": crit["urea_ciclo_Lh"],
        }


# ====================================================================== #
#  Varrimento
# ====================================================================== #
_HEADER = (f"{'V[m3]':>8} {'A[m2]':>8} {'sit':>6} {'NOx_c[g/kWh]':>12} "
           f"{'slip_c[ppm]':>11} {'XNO_c[%]':>10} {'urea[L/h]':>10} {'n_it':>6}")


def _print_row(e: GeometryEvaluation) -> None:
    print(f"{e.volume_m3:8.3f} {e.area_m2:8.3f} {int(e.situation):6d} "
          f"{e.NO_cycle:12.4f} {e.slip_cycle:11.3f} {e.XNO_cycle:10.2f} "
          f"{e.urea_cycle:10.2f} {e.n_iter:6d}")


def volume_sweep(case: EngineCase,
                 targets: Optional[EmissionTargets] = None,
                 options: Optional[VolumeSweepOptions] = None,
                 alpha_options: Optional[AlphaLoopOptions] = None,
                 *,
                 solver_options: Optional[SolverOptions] = None,
                 urea: UreaSolution = DEFAULT_UREA,
                 progress: Optional[Callable[[GeometryEvaluation], None]] = None
                 ) -> VolumeSweepResult:
    """Varrimento descendente em volume ate ao volume critico.

    Parameters
    ----------
    case:
        Motor + ciclo + geometria instalada + cinetica.
    targets:
        Alvos relativos. Por omissao 60 %/10 ppm no ciclo e 80 %/20 ppm por modo.
    options:
        Opcoes do varrimento (passo, refinamento, fouling, envelhecimento...).
    alpha_options:
        Opcoes do loop de alpha.
    progress:
        Chamado apos cada geometria avaliada (para barras de progresso / UI).

    Returns
    -------
    VolumeSweepResult
        Com ``critical_volume_m3`` = menor volume admissivel encontrado, e o
        ponto de operacao reportado nesse volume (:meth:`at_critical`).
    """
    opt = options or VolumeSweepOptions()
    aopt = alpha_options or AlphaLoopOptions()
    tgt_rel = targets or EmissionTargets()

    # ---- aplicar sobreposicoes de cenario ao caso ---------------------- #
    work = case
    if opt.fouling is not None:
        work = work.with_fouling(opt.fouling)
    if opt.aging_KK0 is not None:
        work = work.with_aging(opt.aging_KK0)

    tgt = tgt_rel.resolve(float(work.nox_limit_gkWh))

    L = opt.length_m if opt.length_m is not None else work.geometry.length_m
    V_max = (opt.volume_max_m3 if opt.volume_max_m3 is not None
             else work.geometry.volume_m3)
    n_modes = work.n_modes

    # Arrhenius por modo: nao depende da geometria -> calcula-se uma vez.
    kin = work.kinetics.with_tuning(opt.tuning)
    kads = np.asarray(kin.kads_at(work.T_K), dtype=float)
    kNO = np.asarray(kin.kNO_at(work.T_K), dtype=float)

    X_req = work.required_conversion_pct(tgt.mode_NO_gkWh)

    if opt.verbose:
        print(f"\n{'=' * 16} {work.name} - varrimento em VOLUME "
              f"(alpha adaptativo) {'=' * 16}")
        print(f" Reator    : L={L:.2f} m (fixo)   |  "
              f"Limite = {work.nox_limit_gkWh:.4f} g/kWh")
        print(f" Alvos     : {tgt.describe()}")
        print(" Conversao minima equivalente por modo [%]: "
              + " ".join(f"{v:.2f}" for v in X_req))
        print(f" Cenario   : fouling={work.geometry.fouling:.0%}  "
              f"KK0={work.kinetics.aging_KK0:.3f}  ktune({opt.tuning.describe()})")
        if opt.volumes_m3 is None:
            print(f" Varrimento: V de {V_max:.2f} m3 ate {opt.volume_min_m3:.2f} m3, "
                  f"em passos de -{opt.volume_step_m3:.2f} m3")
        print("-" * 79)
        print(_HEADER)

    def evaluate(volume: float) -> GeometryEvaluation:
        geom = ReactorGeometry(
            length_m=L, frontal_area_m2=volume / L,
            substrate=work.geometry.substrate, fouling=work.geometry.fouling)
        return evaluate_geometry(work, geom, tgt, aopt, tuning=opt.tuning,
                                 solver_options=solver_options, urea=urea,
                                 kads=kads, kNO=kNO)

    # ---- varrimento descendente ---------------------------------------- #
    if opt.volumes_m3 is not None:
        volumes = np.asarray(list(opt.volumes_m3), dtype=float)
    else:
        volumes = matlab_colon(V_max, -abs(opt.volume_step_m3), opt.volume_min_m3)

    records: List[GeometryEvaluation] = []
    phases: List[int] = []
    V_crit = float("nan")
    V_fail = float("nan")

    for V in volumes:
        e = evaluate(float(V))
        records.append(e)
        phases.append(1)
        if opt.verbose:
            _print_row(e)
        if progress is not None:
            progress(e)
        if e.ok:
            V_crit = float(V)          # admissivel -> continua a reduzir
        else:
            V_fail = float(V)          # 1o inadmissivel -> fecha o varrimento
            break

    # ---- refinamento do volume critico (bisseccao em V) ---------------- #
    if opt.refine and np.isfinite(V_crit) and np.isfinite(V_fail):
        a, b = V_fail, V_crit          # a inadmissivel < b admissivel
        while (b - a) > opt.refine_tol_m3:
            m = 0.5 * (a + b)
            e = evaluate(m)
            records.append(e)
            phases.append(2)
            if opt.verbose:
                _print_row(e)
            if progress is not None:
                progress(e)
            if e.ok:
                b = m
            else:
                a = m
        V_crit, V_fail = b, a

    # ---- empacotar por volume decrescente ------------------------------ #
    order = np.argsort([-r.volume_m3 for r in records], kind="stable")
    recs = [records[i] for i in order]
    ph = np.array([phases[i] for i in order], dtype=int)

    def col(attr: str, dtype=float) -> np.ndarray:
        return np.array([getattr(r, attr) for r in recs], dtype=dtype)

    def mat(attr: str) -> np.ndarray:
        return np.vstack([np.asarray(getattr(r, attr), dtype=float) for r in recs]) \
            if recs else np.zeros((0, n_modes))

    result = VolumeSweepResult(
        engine=work.name, length_m=L, volume_max_m3=float(V_max),
        nox_limit_gkWh=float(work.nox_limit_gkWh), targets=tgt,
        load_pct=work.load_pct, weight=work.weight,
        required_conversion_pct=X_req,
        volume_m3=col("volume_m3"), area_m2=col("area_m2"),
        situation=np.array([int(r.situation) for r in recs], dtype=int),
        ok=np.array([r.ok for r in recs], dtype=bool),
        n_iter=col("n_iter", int), phase=ph,
        NO_cycle=col("NO_cycle"), slip_cycle=col("slip_cycle"),
        XNO_cycle=col("XNO_cycle"), urea_cycle=col("urea_cycle"),
        valid=np.array([r.valid for r in recs], dtype=bool),
        why=[r.why for r in recs],
        alpha=mat("alpha"), X_NO=mat("X_NO"), NO_gkWh=mat("NO_gkWh"),
        slip_ppm=mat("slip_ppm"), urea_Lh=mat("urea_Lh"), tau_s=mat("tau_s"),
        AV_Nmh=mat("AV_Nmh"), eta=mat("eta"), sit_mode=mat("sit_mode"),
        critical_volume_m3=V_crit, failed_volume_m3=V_fail,
        critical_area_m2=V_crit / L,
        options=opt, alpha_options=aopt,
    )

    if opt.verbose:
        print("-" * 79)
        if np.isfinite(V_crit):
            crit = result.at_critical()
            print(f" VOLUME CRITICO = {V_crit:.3f} m3   "
                  f"(A = {result.critical_area_m2:.3f} m2, L = {L:.2f} m)")
            print(f" Nesse volume: NOx = {crit['NOx_ciclo_gkWh']:.4f} g/kWh  "
                  f"slip = {crit['slip_ciclo_ppm']:.3f} ppm  "
                  f"X_NO = {crit['XNO_ciclo_perc']:.2f} %  "
                  f"ureia = {crit['urea_ciclo_Lh']:.2f} L/h")
        else:
            print(f" Nenhum volume admissivel encontrado "
                  f"(nem a {V_max:.2f} m3).")
        print("=" * 79)

    return result
