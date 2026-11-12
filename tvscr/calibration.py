"""
Calibracao de alpha contra a conversao medida (porte de ``get_NOx_DG<k>.m``).

Em cada modo do ciclo, alpha e ajustado (+-``step`` por iteracao) ate
minimizar o erro relativo entre a conversao MEDIDA (do dataset) e a calculada
pelo solver. Retem-se sempre o alpha de |erro| MINIMO, porque o passo
multiplicativo pode oscilar em torno da solucao.

Para que serve
--------------
* Para o **varrimento em volume** o alpha calibrado e irrelevante: o loop de
  alpha substitui-o a cada iteracao a partir de ``alpha0``. Por isso a
  calibracao aqui e opcional -- ao contrario do MATLAB, que exigia o ficheiro
  ``alpha_DG<k>.mat`` so para poder correr.
* E necessaria para reproduzir a **curva de implementacao** (o doseamento real
  do motor) e para validar o modelo contra o ensaio.

Tambem se incluem leitores dos ficheiros de alpha ja produzidos pelo MATLAB
(``.csv`` e ``.mat``), para nao ter de recalibrar o que ja foi calibrado.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

from .cycle import run_cycle
from .geometry import ReactorGeometry
from .kinetics import KineticTuning
from .operating import EngineCase
from .solver import SolverOptions, solve_point
from .urea import DEFAULT_UREA, DosingCurve, UreaSolution, urea_flow_Lh

__all__ = ["CalibrationOptions", "CalibrationResult",
           "calibrate_alpha", "load_alpha_csv", "load_alpha_mat"]


@dataclass(frozen=True)
class CalibrationOptions:
    """Parametros do trim de calibracao."""

    step: float = 1.01        # factor de ajuste por iteracao (+-1 %)
    err_tol: float = 0.005    # tolerancia de erro relativo em X_NO (0.5 %)
    alpha_min: float = 0.30
    alpha_max: float = 3.00
    max_iter: int = 200
    alpha_start: Optional[Sequence[float]] = None   # palpite inicial por modo
    dosing_curve: Optional[DosingCurve] = None      # alternativa ao palpite


@dataclass
class CalibrationResult:
    """Alpha calibrado e diagnostico por modo."""

    engine: str
    load_pct: np.ndarray
    weight: np.ndarray
    alpha: np.ndarray             # alpha de erro minimo
    X_measured_pct: np.ndarray
    X_simulated_pct: np.ndarray
    relative_error: np.ndarray    # (X_sim - X_exp)/X_exp  [-]
    slip_ppm: np.ndarray
    NO_out_ppm: np.ndarray
    NO_gkWh: np.ndarray
    urea_Lh: np.ndarray
    n_trim: np.ndarray

    def to_dataframe(self) -> pd.DataFrame:
        """Mesmas colunas de ``alpha_DG<k>.csv``."""
        return pd.DataFrame({
            "Load_perc": self.load_pct,
            "Weight_perc": self.weight,
            "alpha": self.alpha,
            "X_exp_perc": self.X_measured_pct,
            "X_sim_perc": self.X_simulated_pct,
            "err_rel_perc": 100.0 * self.relative_error,
            "slip_ppm": self.slip_ppm,
        })

    def describe(self) -> str:
        lines = [f"--- {self.engine}: alpha calibrado (erro minimo em X_NO) ---",
                 f"{'Load%':>8} {'alpha':>8} {'X_exp[%]':>10} {'X_sim[%]':>10} "
                 f"{'err[%]':>10} {'slip[ppm]':>10}"]
        for i in range(self.alpha.size):
            lines.append(
                f"{self.load_pct[i]:8.2f} {self.alpha[i]:8.4f} "
                f"{self.X_measured_pct[i]:10.2f} {self.X_simulated_pct[i]:10.2f} "
                f"{100 * self.relative_error[i]:10.3f} {self.slip_ppm[i]:10.3f}")
        return "\n".join(lines)


# ====================================================================== #
def calibrate_alpha(case: EngineCase,
                    geometry: Optional[ReactorGeometry] = None,
                    options: Optional[CalibrationOptions] = None,
                    *,
                    tuning: Optional[KineticTuning] = None,
                    solver_options: Optional[SolverOptions] = None,
                    urea: UreaSolution = DEFAULT_UREA,
                    verbose: bool = False) -> CalibrationResult:
    """Calibra alpha modo a modo contra a conversao medida.

    Requer ``NO_out_ppm`` em todos os modos do caso.

    O palpite inicial e, por ordem de preferencia:
    ``options.alpha_start`` -> ``options.dosing_curve`` -> ``case.alpha_calibrated``
    -> 1.0.
    """
    opt = options or CalibrationOptions()
    geom = geometry if geometry is not None else case.geometry
    kin = case.kinetics if tuning is None else case.kinetics.with_tuning(tuning)

    X_exp = case.measured_conversion_pct
    if np.any(~np.isfinite(X_exp)):
        raise ValueError(
            "calibrate_alpha: faltam medidas de NO_out em pelo menos um modo.")

    n = case.n_modes
    mdot = case.mass_flow_kgs
    NO_in = case.NO_in_ppm
    T_K = case.T_K
    kads = np.asarray(kin.kads_at(T_K), dtype=float)
    kNO = np.asarray(kin.kNO_at(T_K), dtype=float)
    A_eff = geom.effective_frontal_area_m2

    # ---- palpite inicial ------------------------------------------------ #
    if opt.alpha_start is not None:
        alpha0 = np.asarray(list(opt.alpha_start), dtype=float)
    elif opt.dosing_curve is not None:
        alpha0 = np.asarray(opt.dosing_curve.alpha(
            case.load_pct, 3600.0 * mdot, NO_in), dtype=float)
    elif case.alpha_calibrated is not None:
        alpha0 = np.asarray(case.alpha_calibrated, dtype=float)
    else:
        alpha0 = np.ones(n)

    alpha_out = np.zeros(n)
    X_sim = np.zeros(n)
    slip = np.zeros(n)
    err = np.zeros(n)
    trims = np.zeros(n, dtype=int)

    def run(k: int, a: float):
        return solve_point(
            T_K=float(T_K[k]), pressure_Pa=case.pressure_Pa,
            mass_flow_kgs=float(mdot[k]), frontal_area_m2=A_eff,
            NO_in_ppm=float(NO_in[k]), alpha=float(a),
            length_m=geom.length_m, substrate=geom.substrate,
            kinetics=kin, kads=float(kads[k]), kNO=float(kNO[k]),
            options=solver_options)

    for k in range(n):
        a = float(np.clip(alpha0[k], opt.alpha_min, opt.alpha_max))
        f = run(k, a)
        e = (f.X_NO - X_exp[k]) / X_exp[k]

        a_best, e_best, f_best = a, e, f
        it = 0
        while abs(e) > opt.err_tol and it < opt.max_iter:
            a = a / opt.step if e > 0 else a * opt.step   # sobre-previsao -> reduzir
            a = float(np.clip(a, opt.alpha_min, opt.alpha_max))
            f = run(k, a)
            e = (f.X_NO - X_exp[k]) / X_exp[k]
            it += 1
            if abs(e) < abs(e_best):
                a_best, e_best, f_best = a, e, f
            if a <= opt.alpha_min or a >= opt.alpha_max:
                break                                     # saturacao

        alpha_out[k] = a_best
        err[k] = e_best
        X_sim[k] = f_best.X_NO
        slip[k] = f_best.slip_ppm
        trims[k] = it

    NO_out_ppm = NO_in * (1.0 - X_sim / 100.0)
    result = CalibrationResult(
        engine=case.name, load_pct=case.load_pct, weight=case.weight,
        alpha=alpha_out, X_measured_pct=X_exp, X_simulated_pct=X_sim,
        relative_error=err, slip_ppm=slip, NO_out_ppm=NO_out_ppm,
        NO_gkWh=case.specific_nox(NO_out_ppm),
        urea_Lh=urea_flow_Lh(alpha_out, NO_in, mdot, urea),
        n_trim=trims)

    if verbose:
        print(result.describe())
    return result


# ====================================================================== #
#  Leitura dos ficheiros de alpha ja produzidos pelo MATLAB
# ====================================================================== #
def load_alpha_csv(path: Union[str, Path],
                   column: str = "alpha") -> np.ndarray:
    """Le o alpha calibrado de um ``alpha_DG<k>.csv``."""
    frame = pd.read_csv(path)
    if column not in frame.columns:
        raise KeyError(f'Coluna "{column}" nao existe em {path}. '
                       f"Colunas: {list(frame.columns)}")
    if "Load_perc" in frame.columns:
        frame = frame.sort_values("Load_perc", kind="stable")
    return frame[column].to_numpy(dtype=float)


def load_alpha_mat(path: Union[str, Path],
                   variable: Optional[str] = None) -> np.ndarray:
    """Le o alpha calibrado de um ``alpha_DG<k>.mat`` (formato MATLAB v5/v7).

    Se ``variable`` for ``None``, procura a primeira variavel cujo nome comece
    por ``alpha``.
    """
    from scipy.io import loadmat

    data = loadmat(str(path), squeeze_me=True)
    if variable is None:
        candidates = [k for k in data
                      if not k.startswith("__") and k.lower().startswith("alpha")]
        if not candidates:
            raise KeyError(f"Nenhuma variavel 'alpha*' em {path}. "
                           f"Variaveis: {[k for k in data if not k.startswith('__')]}")
        variable = candidates[0]
    return np.atleast_1d(np.asarray(data[variable], dtype=float)).ravel()
