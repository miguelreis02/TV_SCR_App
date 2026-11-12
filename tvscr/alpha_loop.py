"""
Loop condicional de acontecimentos / situacoes sobre alpha.

Porte de ``alpha_event_loop.m``. Para UMA geometria, procura o vector de alpha
(um por modo do ciclo) que satisfaz simultaneamente os alvos de NO_out e de
NH3 slip, a DOIS niveis (por modo e no ciclo ponderado).

Acontecimentos (por modo ``k`` e para o ciclo)
----------------------------------------------
====  ==========================  ====  ==========================
A     NO_out abaixo do alvo       B     NO_out acima do alvo
C     slip abaixo do alvo         D     slip acima do alvo
====  ==========================  ====  ==========================

Situacoes
---------
====  =======  =======================  ================================
sit   eventos  leitura                  accao
====  =======  =======================  ================================
1     A + C    alvos cumpridos          fecha o loop (geometria admissivel)
2     B + C    falta conversao          aumentar alpha
3     A + D    slip excessivo           reduzir alpha
4     B + D    janela de alpha vazia    geometria INADMISSIVEL
====  =======  =======================  ================================

Duas decisoes de arquitectura, herdadas do MATLAB e deliberadas
---------------------------------------------------------------
**(a) A Situacao 4 e avaliada POR MODO, nao por agregacao.** Como cada modo
tem o seu proprio alpha, ter o modo *i* em Situacao 2 e o modo *j* em Situacao
3 nao e inviabilidade -- resolve-se ajustando cada um no seu sentido. So e
inviavel quando o MESMO modo (ou o ciclo) exige ao mesmo tempo mais e menos
alpha.

**(b) Bracketing + bisseccao geometrica contra oscilacao.** Um passo
multiplicativo puro de +-X % pode saltar 2<->3 indefinidamente sem nunca cair
na Situacao 1 nem na 4, se a janela viavel for mais estreita que o passo.
Guarda-se por modo o intervalo ``[lo, hi]`` e passa-se a bisseccao geometrica
assim que ambos existirem. Se o intervalo colapsar abaixo de ``bracket_tol``
sem atingir a Situacao 1, a janela e vazia -> Situacao 4. E isto que torna a
Situacao 4 uma **deteccao fiavel de inviabilidade**, e nao um acaso do passo.

**Camada do ciclo.** Quando todos os modos estao em Situacao 1 mas o ciclo
ponderado ainda viola um alvo, o ajuste passa a ser global -- mas so sobre os
modos com folga no sentido necessario. Se nenhum modo se pode mexer nesse
sentido, o alvo do ciclo e inatingivel nessa geometria -> Situacao 4, com
motivo explicito (e nao um ciclo infinito).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

import numpy as np

from .cycle import CycleResult, run_cycle
from .geometry import ReactorGeometry
from .kinetics import KineticTuning
from .numerics import EPS
from .operating import EngineCase
from .solver import SolverOptions
from .targets import ResolvedTargets
from .urea import DEFAULT_UREA, UreaSolution

__all__ = ["Situation", "AlphaLoopOptions", "AlphaLoopResult", "alpha_event_loop"]


class Situation(IntEnum):
    """Classificacao do estado do loop."""

    NOT_CONVERGED = 0     # esgotou as iteracoes
    TARGETS_MET = 1       # A + C -> geometria admissivel
    NEED_MORE_ALPHA = 2   # B + C -> falta conversao
    NEED_LESS_ALPHA = 3   # A + D -> slip excessivo
    INFEASIBLE = 4        # B + D -> janela de alpha vazia


@dataclass(frozen=True)
class AlphaLoopOptions:
    """Opcoes do loop de alpha (``opt.aopt`` no MATLAB)."""

    alpha0: float = 0.80          # alpha de arranque
    dalpha: float = 0.02          # passo multiplicativo (2 %)
    alpha_min: float = 0.30
    alpha_max: float = 1.20
    max_iter: int = 200
    bracket_tol: float = 1e-4     # colapso de [lo, hi]
    minimize_alpha: bool = False  # ver nota em alpha_event_loop
    verbose: bool = False


@dataclass
class AlphaLoopResult:
    """Saida do loop para uma geometria."""

    situation: Situation
    ok: bool
    alpha: np.ndarray                 # (N,) alpha convergido por modo
    cycle: Optional[CycleResult]      # avaliacao do ciclo no ponto final
    n_iter: int
    sit_mode: np.ndarray              # (N,) situacao final de cada modo
    why: str
    lo: np.ndarray                    # (N,) limites de alpha descobertos
    hi: np.ndarray
    history: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    n_minimize_steps: int = 0

    def describe(self) -> str:
        a = " ".join(f"{v:.3f}" for v in self.alpha)
        return (f"situacao={int(self.situation)} ok={self.ok} n_iter={self.n_iter} "
                f"alpha=[{a}] :: {self.why}")


# ====================================================================== #
def _is_situation1(cycle: CycleResult, tgt: ResolvedTargets) -> bool:
    """Situacao 1 nos DOIS niveis (usado na fase de minimizacao de alpha)."""
    return bool(np.all(cycle.NO_gkWh <= tgt.mode_NO_gkWh)
                and np.all(cycle.slip_ppm <= tgt.mode_slip_ppm)
                and cycle.NO_cycle <= tgt.cycle_NO_gkWh
                and cycle.slip_cycle <= tgt.cycle_slip_ppm)


def alpha_event_loop(case: EngineCase,
                     geometry: ReactorGeometry,
                     targets: ResolvedTargets,
                     options: Optional[AlphaLoopOptions] = None,
                     *,
                     tuning: Optional[KineticTuning] = None,
                     solver_options: Optional[SolverOptions] = None,
                     urea: UreaSolution = DEFAULT_UREA,
                     kads: Optional[np.ndarray] = None,
                     kNO: Optional[np.ndarray] = None) -> AlphaLoopResult:
    """Procura o alpha por modo que cumpre os alvos numa dada geometria.

    Parameters
    ----------
    case:
        Motor + ciclo + cinetica.
    geometry:
        Geometria a avaliar (ja com o fouling que se lhe queira aplicar).
    targets:
        Alvos absolutos (ver :class:`~tvscr.targets.EmissionTargets`).
    options:
        Opcoes do loop.
    kads, kNO:
        Constantes agrupadas por modo, pre-calculadas (evita repetir Arrhenius
        em varrimentos longos).

    Notes
    -----
    ``options.minimize_alpha`` -- enquanto o reator tem folga, o alpha de
    arranque ja cumpre tudo e o loop fecha a primeira iteracao, deixando o
    caudal de ureia igual ao do arranque (pouco informativo longe do volume
    critico). Com ``minimize_alpha=True``, depois de atingir a Situacao 1 o
    alpha desce por modo enquanto os alvos se mantiverem, devolvendo o **alpha
    minimo admissivel** (minimo de ureia e de slip). Nao altera o volume
    critico -- so o ponto de operacao reportado.
    """
    opt = options or AlphaLoopOptions()
    n = case.n_modes

    alpha = np.full(n, float(opt.alpha0))
    lo = np.full(n, np.nan)   # maior alpha conhecido AINDA com NOx alto
    hi = np.full(n, np.nan)   # menor alpha conhecido JA com slip alto
    sit = np.ones(n, dtype=int)
    history: List[np.ndarray] = []
    cycle: Optional[CycleResult] = None

    def evaluate(a: np.ndarray) -> CycleResult:
        return run_cycle(case, geometry, a, tuning=tuning,
                         options=solver_options, urea=urea, kads=kads, kNO=kNO)

    def close(situation: Situation, why: str, it: int,
              n_min: int = 0) -> AlphaLoopResult:
        hist = (np.vstack(history) if history else np.zeros((0, 3 * n + 3)))
        return AlphaLoopResult(
            situation=situation, ok=(situation == Situation.TARGETS_MET),
            alpha=alpha.copy(), cycle=cycle, n_iter=it, sit_mode=sit.copy(),
            why=why, lo=lo.copy(), hi=hi.copy(), history=hist,
            n_minimize_steps=n_min)

    it = 0
    for it in range(1, opt.max_iter + 1):
        # ---- avaliar a geometria com o alpha corrente ------------------ #
        cycle = evaluate(alpha)
        if not cycle.geometry_ok:
            return AlphaLoopResult(
                situation=Situation.INFEASIBLE, ok=False, alpha=alpha.copy(),
                cycle=cycle, n_iter=it, sit_mode=np.ones(n, dtype=int),
                why="geometria invalida (dh<=0)", lo=lo.copy(), hi=hi.copy(),
                history=np.zeros((0, 3 * n + 3)))

        # ---- ACONTECIMENTOS -------------------------------------------- #
        Bk = cycle.NO_gkWh > targets.mode_NO_gkWh      # B por modo
        Dk = cycle.slip_ppm > targets.mode_slip_ppm    # D por modo
        Bc = bool(cycle.NO_cycle > targets.cycle_NO_gkWh)     # B do ciclo
        Dc = bool(cycle.slip_cycle > targets.cycle_slip_ppm)  # D do ciclo

        # ---- SITUACOES por modo ---------------------------------------- #
        sit = np.ones(n, dtype=int)
        sit[Bk & ~Dk] = 2
        sit[~Bk & Dk] = 3
        sit[Bk & Dk] = 4

        history.append(np.concatenate((
            [it], alpha, cycle.NO_gkWh, cycle.slip_ppm,
            [cycle.NO_cycle, cycle.slip_cycle])))

        if opt.verbose:
            astr = " ".join(f"{v:.3f}" for v in alpha)
            sstr = "".join(str(int(v)) for v in sit)
            print(f"  it{it:02d}  alpha=[{astr}]  NOx_c={cycle.NO_cycle:.3f}  "
                  f"slip_c={cycle.slip_cycle:.2f}  sit=[{sstr}]  "
                  f"Bc={int(Bc)} Dc={int(Dc)}")

        # ---- Situacao 4 ao nivel do MODO: janela vazia nesse modo ------ #
        if np.any(sit == 4):
            bad = (np.flatnonzero(sit == 4) + 1).tolist()
            return close(Situation.INFEASIBLE,
                         f"Situacao 4 no(s) modo(s) {bad}: NO_out e slip acima "
                         f"do alvo ao mesmo alpha", it)

        modes_ok = bool(np.all(sit == 1))

        # ---- Situacao 4 ao nivel do CICLO ------------------------------ #
        if modes_ok and Bc and Dc:
            return close(Situation.INFEASIBLE,
                         "Situacao 4 no ciclo: NOx ponderado e slip ponderado "
                         "acima do alvo", it)

        # ---- Situacao 1: tudo cumprido, nos dois niveis ---------------- #
        if modes_ok and not Bc and not Dc:
            why = "Situacao 1: alvos cumpridos por modo e no ciclo"
            n_min = 0
            if opt.minimize_alpha:
                alpha, cycle, it, n_min = _minimize_alpha_phase(
                    evaluate, targets, opt, alpha, cycle, it)
                why = f"{why} (alpha minimizado em {n_min} passos)"
            return close(Situation.TARGETS_MET, why, it, n_min)

        # ---- Direccao do ajuste ---------------------------------------- #
        up = (sit == 2)
        down = (sit == 3)

        # Modos com folga no sentido necessario. Um modo encostado ao seu
        # limite de slip nao pode subir mais; idem para o de NOx a descer.
        can_up = ((~np.isfinite(hi)) | (alpha < hi * (1.0 - opt.bracket_tol))) \
            & (alpha < opt.alpha_max - EPS)
        can_down = ((~np.isfinite(lo)) | (alpha > lo * (1.0 + opt.bracket_tol))) \
            & (alpha > opt.alpha_min + EPS)

        if modes_ok:
            if Bc:
                if not np.any(can_up):
                    return close(Situation.INFEASIBLE,
                                 "Situacao 4 no ciclo: NOx ponderado acima do alvo "
                                 "e nenhum modo pode aumentar alpha sem partir o "
                                 "seu limite de slip", it)
                up = can_up
            if Dc:
                if not np.any(can_down):
                    return close(Situation.INFEASIBLE,
                                 "Situacao 4 no ciclo: slip ponderado acima do alvo "
                                 "e nenhum modo pode reduzir alpha sem partir o "
                                 "seu limite de NOx", it)
                down = can_down

        # ---- Actualizar intervalos e propor novo alpha ------------------ #
        a_prev = alpha.copy()
        for k in range(n):
            if up[k]:
                lo[k] = alpha[k]                       # este alpha e demasiado BAIXO
                if np.isfinite(hi[k]) and hi[k] > lo[k]:
                    alpha[k] = np.sqrt(lo[k] * hi[k])  # bisseccao geometrica
                else:
                    alpha[k] = alpha[k] * (1.0 + opt.dalpha)
            elif down[k]:
                hi[k] = alpha[k]                       # este alpha e demasiado ALTO
                if np.isfinite(lo[k]) and hi[k] > lo[k]:
                    alpha[k] = np.sqrt(lo[k] * hi[k])
                else:
                    alpha[k] = alpha[k] / (1.0 + opt.dalpha)
        alpha = np.minimum(np.maximum(alpha, opt.alpha_min), opt.alpha_max)

        # ---- Colapso do intervalo: janela vazia ------------------------- #
        with np.errstate(invalid="ignore", divide="ignore"):
            collapsed = (np.isfinite(lo) & np.isfinite(hi)
                         & ((hi / lo - 1.0) < opt.bracket_tol) & (sit != 1))
        if np.any(collapsed):
            bad = (np.flatnonzero(collapsed) + 1).tolist()
            return close(Situation.INFEASIBLE,
                         f"janela de alpha vazia no(s) modo(s) {bad} "
                         f"(intervalo [lo,hi] colapsou sem cumprir os alvos)", it)

        # ---- Saturacao dos limites de alpha ----------------------------- #
        stuck_hi = up & (a_prev >= opt.alpha_max - EPS)
        stuck_lo = down & (a_prev <= opt.alpha_min + EPS)
        if np.any(stuck_hi):
            bad = (np.flatnonzero(stuck_hi) + 1).tolist()
            return close(Situation.INFEASIBLE,
                         f"alpha saturou em alpha_max={opt.alpha_max:.2f} sem "
                         f"cumprir o NOx (modos {bad})", it)
        if np.any(stuck_lo):
            bad = (np.flatnonzero(stuck_lo) + 1).tolist()
            return close(Situation.INFEASIBLE,
                         f"alpha saturou em alpha_min={opt.alpha_min:.2f} sem "
                         f"cumprir o slip (modos {bad})", it)

        # ---- Sem movimento: nada a ajustar mas alvos por cumprir -------- #
        if np.max(np.abs(alpha - a_prev) / np.maximum(a_prev, EPS)) < 1e-12:
            return close(Situation.INFEASIBLE,
                         "alpha estagnou sem cumprir os alvos", it)

    # ---- Nao convergiu dentro de max_iter ------------------------------- #
    return close(Situation.NOT_CONVERGED,
                 f"nao convergiu em {opt.max_iter} iteracoes", opt.max_iter)


# ====================================================================== #
def _minimize_alpha_phase(evaluate, targets: ResolvedTargets,
                          opt: AlphaLoopOptions, alpha: np.ndarray,
                          cycle: CycleResult, it: int):
    """Descida gulosa por modo: reduz alpha enquanto a Situacao 1 se mantiver.

    Cada modo e "fixado" quando a proxima reducao partiria os alvos. Devolve o
    alpha minimo admissivel -> minimo de ureia e de slip.
    """
    n = alpha.size
    pinned = np.zeros(n, dtype=bool)
    n_step = 0

    while (not np.all(pinned)) and it < opt.max_iter:
        progressed = False
        for k in np.flatnonzero(~pinned).tolist():   # snapshot, como o MATLAB
            a_try = alpha.copy()
            a_try[k] = alpha[k] / (1.0 + opt.dalpha)
            if a_try[k] < opt.alpha_min:
                pinned[k] = True
                continue
            trial = evaluate(a_try)
            it += 1
            if _is_situation1(trial, targets):
                alpha = a_try
                cycle = trial
                progressed = True
                n_step += 1
            else:
                pinned[k] = True
        if not progressed:
            break

    return alpha, cycle, it, n_step
