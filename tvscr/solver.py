"""
Solver 1-D de SCR-deNOx -- Tronconi, Cavanna & Forzatti (1998).

Porte directo de ``tronconi_sizing_forward_v2.m``: variante ESTACIONARIA,
orientada a dimensionamento (forward: geometria -> conversao).

Modelo
------
Marcha espacial em ``z`` sobre ``N`` nos. Em cada no resolve-se um sistema
2x2 em ``[C_NO ; theta]``:

1. Balanco gasoso de NO em estado estacionario (limite de ``d/dt = 0``)::

       conv*(C_NO - C_NO_montante) + (4/dh)*k_mat*(C_NO - C_NO_parede) = 0

2. Balanco da cobertura de NH3, algebrico::

       r_eff_NH3 - r_eff_NO = 0

O campo de concentracoes DENTRO da parede e analitico (Thiele), com a
fronteira da regiao activa ``x*`` dada pela Eq. A6. A estequiometria
``C_NH3 - C_NO = (alpha - 1) * C_NO_in`` e invariante axial, o que reduz o
sistema a duas incognitas.

Notas de porte
--------------
* O 1o argumento de temperatura e KELVIN (o cabecalho MATLAB chamava-lhe
  ``T_C`` mas usava-o directamente como ``T``); aqui chama-se ``T_K``.
* ``x*`` e calculado a partir do modulo de Thiele do NH3 (``PhiN``) e
  REUTILIZADO no termo do NO -- e a fronteira da regiao onde ha NH3
  adsorvido, nao uma propriedade do NO. Igual ao MATLAB.
* O Newton 2x2 amortecido com projeccao em caixa e reproduzido passo a passo
  (mesmo jacobiano por diferencas finitas, mesmo line-search, mesma deteccao
  de restricao activa), porque os diagnosticos de validade dependem dele.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np

from .geometry import ReactorGeometry, SubstrateGeometry
from .kinetics import KineticParameters
from .numerics import EPS, safe_cosh, safe_sinh, solve2x2

__all__ = [
    "SolverOptions",
    "PointResult",
    "solve_point",
    "solve_geometry_point",
    "sherwood_kmat_profile",
    "effective_rates",
]


# ====================================================================== #
#  Opcoes numericas
# ====================================================================== #
@dataclass(frozen=True)
class SolverOptions:
    """Parametros NUMERICOS do solver (nao fisicos).

    Os valores por omissao sao os do MATLAB. ``n_nodes=120`` e a malha do
    modelo transiente validado -- alterar muda o resultado ao nivel da
    discretizacao.
    """

    n_nodes: int = 120                    # nos axiais
    newton_max_iter: int = 200            # iteracoes de Newton por no
    newton_line_search_steps: int = 40    # halvings do passo
    newton_step_tol: float = 1e-12        # criterio de paragem (passo relativo)
    theta_floor: float = 1e-9             # limite inferior da cobertura
    theta_ceil: float = 1.0 - 1e-9        # limite superior da cobertura
    theta0_guess: float = 0.02            # fallback de theta no no de entrada
    resnorm_tol: float = 1e-6             # gate de engenharia
    resnorm_tol_strict: float = 1e-10     # regra literal do enunciado


# ====================================================================== #
#  Resultado de um ponto
# ====================================================================== #
@dataclass
class PointResult:
    """Saida do solver para UM ponto de operacao + UMA geometria."""

    # --- resultados principais ---
    X_NO: float                 # conversao de NO             [%]
    X_NH3: float                # conversao de NH3            [%]
    slip_ppm: float             # NH3 a saida                 [ppm]

    # --- regime hidrodinamico ---
    velocity_ms: float          # velocidade intersticial     [m/s]
    AV: float                   # area-velocidade real        [m/s]
    AV_Nmh: float               # area-velocidade normalizada [Nm/h]
    tau_s: float                # tempo de residencia         [s]
    Q_m3s: float                # caudal volumetrico a T,P    [m3/s]
    rho_kgm3: float             # densidade do gas a T,P      [kg/m3]

    # --- geometria derivada ---
    dh_m: float
    pitch_m: float
    eps_void: float

    # --- perfis axiais ---
    z: np.ndarray               # (N+1,) coordenada adimensional
    CNO_ppm_z: np.ndarray       # (N+1,)
    CNH3_ppm_z: np.ndarray      # (N+1,)
    theta_z: np.ndarray         # (N+1,)

    # --- diagnostico de regime ---
    etaO_z: np.ndarray          # (N,) eficacia do NO (Thiele)
    PhiO_z: np.ndarray          # (N,) modulo de Thiele do NO
    Bim_z: np.ndarray           # (N,) Biot massico kapp/kmat
    kov_z: np.ndarray           # (N,) coeficiente global local [m/s]
    etaO_bar: float
    Bim_bar: float
    kov: float                  # coeficiente global do reator  [m/s]

    # --- diagnostico numerico ---
    resnorm_z: np.ndarray       # (N,)
    active_z: np.ndarray        # (N,) bool
    clip_lb_z: np.ndarray       # (N,2) bool
    clip_ub_z: np.ndarray       # (N,2) bool
    max_resnorm: float
    n_active: int
    any_active: bool
    theta_active: bool          # theta colado a 0/1 (benigno)
    floor_active: bool          # PISO estequiometrico de C_NO activo (grave)
    valid: bool                 # gate de engenharia
    valid_strict: bool          # regra literal

    # --- ecos dos inputs ---
    T_K: float = float("nan")
    alpha: float = float("nan")
    NO_in_ppm: float = float("nan")
    kads: float = float("nan")
    kNO: float = float("nan")

    @property
    def X_NO_ceiling(self) -> float:
        """Teto estequiometrico da conversao de NO [%]."""
        return 100.0 * min(1.0, self.alpha)

    def describe(self) -> str:
        return (f"X_NO={self.X_NO:6.2f} %  (teto {self.X_NO_ceiling:.1f} %)  "
                f"slip={self.slip_ppm:7.3f} ppm  AV={self.AV_Nmh:8.1f} Nm/h  "
                f"tau={self.tau_s:.4f} s  valid={self.valid}")


# ====================================================================== #
#  Transferencia de massa: Sherwood local
# ====================================================================== #
def sherwood_kmat_profile(n_nodes: int, L: float, dh: float,
                          Dmol: float, velocity: float) -> np.ndarray:
    """Coeficiente de transferencia de massa gas-parede ao longo do canal.

    Correlacao de Sherwood local para canal quadrado em desenvolvimento
    (Tronconi & Forzatti 1992 / Tronconi & Beretta 1999)::

        Sh(z*) = 2.977 + 8.827 * (1000 z*)^-0.545 * exp(-48.2 z*)
        z*     = z * Dmol / (v * dh^2)

    Devolve ``(n_nodes+1,)`` valores, um por no de ``theta`` (z = 0..1); o no
    de entrada e deslocado para ``z = dz/2`` para evitar ``Sh -> inf``.
    """
    z_adim = np.arange(n_nodes + 1, dtype=float) / n_nodes
    z_adim[0] = 0.5 / n_nodes
    z_star = (z_adim * L) * Dmol / (velocity * dh ** 2)
    Sh = 2.977 + 8.827 * (1000.0 * z_star) ** (-0.545) * np.exp(-48.2 * z_star)
    return Sh * Dmol / dh


# ====================================================================== #
#  Nucleo cinetico: taxas efetivas com campo interno analitico
# ====================================================================== #
def _x_star(phi: float, f: float) -> float:
    """Fronteira da regiao activa (Eq. A6), saturada em [0, 1]."""
    fc = f * safe_cosh(min(phi, 500.0))
    xs = math.acosh(fc) / phi if fc > 1.0 else 0.0
    return 0.0 if xs < 0.0 else (1.0 if xs > 1.0 else xs)


def effective_rates(CbN: float, CbO: float, theta: float,
                    s: float, kmat: float, Deff: float,
                    kads: float, kNO: float,
                    k0d: float, E0d: float, beta: float,
                    R_cal: float, T_K: float, f: float):
    """Continuidade gas-solido (Eqs. 9-10) + taxas efetivas (Eqs. 13-14).

    Returns
    -------
    (CWN, CWO, reffN, reffO, PhiN, PhiO, x_star, g)
        Concentracoes a superficie da parede, taxas efetivas por unidade de
        area, modulos de Thiele, fronteira activa e factor geometrico do NO.
    """
    one_th = 1.0 - theta
    if one_th < 0.0:
        one_th = 0.0

    kd_v = k0d * math.exp(-E0d * (1.0 - beta * theta) / (R_cal * T_K))

    # ---- NH3 (Eq. 13) ------------------------------------------------- #
    argN = kads * one_th
    if argN < 1e-9:
        argN = 1e-9
    PhiN = s * math.sqrt(argN / Deff)
    xs = _x_star(PhiN, f)
    tN = math.tanh(PhiN) / PhiN

    a = kads * one_th * tN
    b = kd_v * theta * (1.0 - xs) * tN
    CWN = (kmat * CbN + s * b) / (kmat + s * a)
    if CWN < 0.0:
        CWN = 0.0
    reffN = (kads * CWN * one_th - kd_v * theta * (1.0 - xs)) * tN

    # ---- NO (Eq. 14) -------------------------------------------------- #
    # x* vem do NH3: e a fronteira da zona com NH3 adsorvido, e e essa que
    # delimita onde o NO pode reagir.
    argO = kNO * theta
    if argO < 1e-12:
        argO = 1e-12
    PhiO = s * math.sqrt(argO / Deff)
    if PhiO > 1e-6:
        g = (1.0 - safe_sinh(PhiO * xs) / safe_cosh(PhiO)) * math.tanh(PhiO) / PhiO
    else:
        g = 1.0

    CWO = kmat * CbO / (kmat + s * kNO * theta * g)
    reffO = kNO * CWO * theta * g

    return CWN, CWO, reffN, reffO, PhiN, PhiO, xs, g


# ====================================================================== #
#  Newton 2x2 amortecido com projeccao em caixa
# ====================================================================== #
def _newton2(residual: Callable[[float, float], Tuple[float, float]],
             x0: Tuple[float, float],
             lb: Tuple[float, float],
             ub: Tuple[float, float],
             scale: Tuple[float, float],
             opts: SolverOptions):
    """Newton 2x2 amortecido, sem dependencias externas.

    A deteccao de "solucao colada" mede se a PROJECCAO mordeu o passo de
    Newton cru -- nao a mera proximidade ao limite, que ocorre de forma
    legitima (p.ex. ``C_NO -> 0`` quando ``alpha >= 1``).

    Returns
    -------
    (x, resnorm, clip_lb, clip_ub)
    """
    xa, xb = x0
    lb0, lb1 = lb
    ub0, ub1 = ub
    sc0, sc1 = scale

    xa = lb0 if xa < lb0 else (ub0 if xa > ub0 else xa)
    xb = lb1 if xb < lb1 else (ub1 if xb > ub1 else xb)

    F0, F1 = residual(xa, xb)
    clip_lb = [False, False]
    clip_ub = [False, False]

    for _ in range(opts.newton_max_iter):
        # --- jacobiano por diferencas finitas para a frente --------------
        h0 = 1e-7 * max(abs(xa), sc0)
        h1 = 1e-7 * max(abs(xb), sc1)
        Fa0, Fa1 = residual(xa + h0, xb)
        Fb0, Fb1 = residual(xa, xb + h1)
        j11 = (Fa0 - F0) / h0
        j21 = (Fa1 - F1) / h0
        j12 = (Fb0 - F0) / h1
        j22 = (Fb1 - F1) / h1

        s0, s1 = solve2x2(j11, j12, j21, j22, F0, F1)
        dx0, dx1 = -s0, -s1
        if not (math.isfinite(dx0) and math.isfinite(dx1)):
            break

        # --- line search com projeccao ----------------------------------
        lam = 1.0
        nF0 = math.hypot(F0, F1)
        xn0, xn1 = xa, xb
        for _k in range(opts.newton_line_search_steps):
            raw0 = xa + lam * dx0
            raw1 = xb + lam * dx1
            xt0 = lb0 if raw0 < lb0 else (ub0 if raw0 > ub0 else raw0)
            xt1 = lb1 if raw1 < lb1 else (ub1 if raw1 > ub1 else raw1)
            Ft0, Ft1 = residual(xt0, xt1)
            if math.hypot(Ft0, Ft1) <= nF0 or lam < 1e-10:
                xn0, xn1 = xt0, xt1
                F0, F1 = Ft0, Ft1
                clip_lb = [raw0 < lb0, raw1 < lb1]
                clip_ub = [raw0 > ub0, raw1 > ub1]
                break
            lam *= 0.5

        step = math.hypot((xn0 - xa) / sc0, (xn1 - xb) / sc1)
        xa, xb = xn0, xn1
        if step < opts.newton_step_tol:
            break

    return (xa, xb), math.hypot(F0, F1), clip_lb, clip_ub


def _solve_theta_inlet(CNH3_in: float, CNO_in: float, kmat0: float,
                       s: float, Deff: float, kads: float, kNO: float,
                       k0d: float, E0d: float, beta: float,
                       R_cal: float, T_K: float, f: float,
                       opts: SolverOptions) -> float:
    """Cobertura na face de entrada: raiz de ``reffN - reffO`` com o feed.

    Equivalente ao ``fzero(g, [1e-9, 1-1e-9])`` do MATLAB (Brent com
    bracketing). Se nao houver mudanca de sinal no intervalo, cai no palpite
    de recurso -- exactamente como o ``try/catch`` original.
    """
    from scipy.optimize import brentq   # import local: mantem o modulo leve

    def gap(th: float) -> float:
        rates = effective_rates(CNH3_in, CNO_in, th, s, kmat0, Deff, kads, kNO,
                                k0d, E0d, beta, R_cal, T_K, f)
        return rates[2] - rates[3]

    lo, hi = opts.theta_floor, opts.theta_ceil
    try:
        if gap(lo) * gap(hi) > 0.0:
            return opts.theta0_guess
        return float(brentq(gap, lo, hi, xtol=1e-15,
                            rtol=8.881784197001252e-16, maxiter=200))
    except (ValueError, RuntimeError, FloatingPointError):
        return opts.theta0_guess


# ====================================================================== #
#  Solver principal
# ====================================================================== #
def solve_point(T_K: float,
                pressure_Pa: float,
                mass_flow_kgs: float,
                frontal_area_m2: float,
                NO_in_ppm: float,
                alpha: float,
                length_m: float,
                substrate: SubstrateGeometry,
                kinetics: KineticParameters,
                kads: Optional[float] = None,
                kNO: Optional[float] = None,
                options: Optional[SolverOptions] = None) -> PointResult:
    """Resolve UM ponto de operacao numa geometria.

    Parameters
    ----------
    T_K:
        Temperatura de reaccao [K].
    pressure_Pa:
        Pressao [Pa].
    mass_flow_kgs:
        Caudal massico de escape [kg/s].
    frontal_area_m2:
        Area frontal EFETIVA do monolito [m^2] (ja com o derate de fouling,
        se aplicavel -- o solver nao volta a aplica-lo).
    NO_in_ppm:
        Concentracao de NO a entrada [ppm].
    alpha:
        Razao molar ``C_NH3_in / C_NO_in`` [-].
    length_m:
        Comprimento do monolito [m].
    substrate:
        Geometria da celula (CPSI, parede).
    kinetics:
        Parametros cineticos e de transporte.
    kads, kNO:
        Constantes agrupadas ja avaliadas a ``T_K``. Se ``None``, sao
        calculadas por Arrhenius a partir de ``kinetics`` (equivalente a
        omitir os argumentos no MATLAB).
    options:
        Parametros numericos.

    Raises
    ------
    ValueError
        Se a geometria for invalida (``dh <= 0``).
    """
    opts = options or SolverOptions()
    gas = kinetics.gas
    N = opts.n_nodes

    # ---- geometria ---------------------------------------------------- #
    pitch = substrate.pitch_m
    s = substrate.half_wall_m
    dh = substrate.hydraulic_diameter_m
    if dh <= 0.0:
        raise ValueError("Geometria invalida: dh <= 0 (CPSI e/ou parede excessivos).")
    eps_void = substrate.open_frontal_fraction

    # ---- cinetica a temperatura do ponto ------------------------------ #
    if kads is None:
        kads = float(kinetics.kads_at(T_K))
    if kNO is None:
        kNO = float(kinetics.kNO_at(T_K))
    Deff = kinetics.Deff
    Dmol = kinetics.Dmol
    k0d, E0d, beta, f = kinetics.k0d, kinetics.E0d, kinetics.beta, kinetics.f
    R_cal = gas.R_cal

    # ---- escoamento: caudal -> velocidade, AV ------------------------- #
    rho = pressure_Pa * kinetics.M_bar_kg_mol / (gas.R_J * T_K)
    Q = mass_flow_kgs / rho
    v = Q / (frontal_area_m2 * eps_void)
    AV = v * dh / (4.0 * length_m)
    AV_Nmh = AV * 3600.0 * 273.15
    tau = length_m / v

    # ---- concentracoes a entrada -------------------------------------- #
    ppm = 1e-6 * pressure_Pa / (gas.R_J * T_K)      # ppm -> mol/m3 a T,P
    CNO_in = NO_in_ppm * ppm
    CNH3_in = alpha * CNO_in
    dCfix = (alpha - 1.0) * CNO_in                  # C_NH3 - C_NO (invariante axial)

    # ---- transferencia de massa --------------------------------------- #
    kmat_z = sherwood_kmat_profile(N, length_m, dh, Dmol, v)

    # ---- marcha estacionaria em z ------------------------------------- #
    dz = 1.0 / N
    conv = (v / length_m) / dz          # coeficiente convectivo discreto [1/s]

    CNO_z = np.zeros(N)
    CNH3_z = np.zeros(N)
    theta_z = np.zeros(N + 1)
    resnorm_z = np.zeros(N)
    active_z = np.zeros(N, dtype=bool)
    clip_lb_z = np.zeros((N, 2), dtype=bool)
    clip_ub_z = np.zeros((N, 2), dtype=bool)

    theta_z[0] = _solve_theta_inlet(CNH3_in, CNO_in, float(kmat_z[0]), s, Deff,
                                    kads, kNO, k0d, E0d, beta, R_cal, T_K, f, opts)

    CO_up = CNO_in
    guess = (CNO_in, max(theta_z[0], opts.theta0_guess))
    lbase = max(0.0, 1.0 - alpha) * CNO_in          # piso estequiometrico de C_NO
    four_over_dh = 4.0 / dh

    for j in range(N):
        kmat_j = float(kmat_z[j + 1])

        def residual(CbO: float, th: float,
                     _co: float = CO_up, _km: float = kmat_j) -> Tuple[float, float]:
            CbN = CbO + dCfix
            if CbN < 0.0:
                CbN = 0.0
            rates = effective_rates(CbN, CbO, th, s, _km, Deff, kads, kNO,
                                    k0d, E0d, beta, R_cal, T_K, f)
            CWO, reffN, reffO = rates[1], rates[2], rates[3]
            return (conv * (CbO - _co) + four_over_dh * _km * (CbO - CWO),
                    reffN - reffO)

        x, resnorm, clb, cub = _newton2(
            residual, guess,
            (lbase, opts.theta_floor), (CO_up, opts.theta_ceil),
            (CNO_in, 1.0), opts)

        resnorm_z[j] = resnorm
        clip_lb_z[j, :] = clb
        clip_ub_z[j, :] = cub
        # Restricao ATIVA relevante: piso estequiometrico de C_NO (mascara
        # X_NO = alpha) OU theta colado a 0/1. O topo ub[0] = C_montante NAO
        # conta: e apenas a monotonia da marcha.
        active_z[j] = clb[0] or clb[1] or cub[1]

        CNO_z[j] = x[0]
        theta_z[j + 1] = x[1]
        CNH3_z[j] = max(x[0] + dCfix, 0.0)
        CO_up = CNO_z[j]
        guess = x

    # ---- diagnostico de regime (pos-processo) ------------------------- #
    PhiO_z = np.zeros(N)
    etaO_z = np.zeros(N)
    Bim_z = np.zeros(N)
    kov_z = np.zeros(N)
    for j in range(N):
        kmat_j = float(kmat_z[j + 1])
        rates = effective_rates(CNH3_z[j], CNO_z[j], theta_z[j + 1], s, kmat_j,
                                Deff, kads, kNO, k0d, E0d, beta, R_cal, T_K, f)
        PhiO, g = rates[5], rates[7]
        kapp = s * kNO * theta_z[j + 1] * g
        etaO_z[j] = g
        PhiO_z[j] = PhiO
        Bim_z[j] = kapp / kmat_j
        kov_z[j] = 1.0 / (1.0 / kmat_j + 1.0 / max(kapp, EPS))

    # ---- resultados ---------------------------------------------------- #
    CNO_out = CNO_z[-1]
    CNH3_out = CNH3_z[-1]
    X_NO = 100.0 * (CNO_in - CNO_out) / CNO_in
    X_NH3 = (100.0 * (CNH3_in - CNH3_out) / CNH3_in
             if CNH3_in > 0.0 else float("nan"))
    slip = max(CNO_out + dCfix, 0.0) / ppm

    max_resnorm = float(np.max(resnorm_z))
    any_active = bool(np.any(active_z))
    theta_active = bool(np.any(clip_lb_z[:, 1] | clip_ub_z[:, 1]))
    floor_active = bool(np.any(clip_lb_z[:, 0]))

    return PointResult(
        X_NO=X_NO, X_NH3=X_NH3, slip_ppm=slip,
        velocity_ms=v, AV=AV, AV_Nmh=AV_Nmh, tau_s=tau, Q_m3s=Q, rho_kgm3=rho,
        dh_m=dh, pitch_m=pitch, eps_void=eps_void,
        z=np.arange(N + 1, dtype=float) / N,
        CNO_ppm_z=np.concatenate(([CNO_in], CNO_z)) / ppm,
        CNH3_ppm_z=np.concatenate(([CNH3_in], CNH3_z)) / ppm,
        theta_z=theta_z,
        etaO_z=etaO_z, PhiO_z=PhiO_z, Bim_z=Bim_z, kov_z=kov_z,
        etaO_bar=float(np.mean(etaO_z)), Bim_bar=float(np.mean(Bim_z)),
        kov=-AV * math.log(max(1.0 - X_NO / 100.0, EPS)),
        resnorm_z=resnorm_z, active_z=active_z,
        clip_lb_z=clip_lb_z, clip_ub_z=clip_ub_z,
        max_resnorm=max_resnorm, n_active=int(np.sum(active_z)),
        any_active=any_active, theta_active=theta_active,
        floor_active=floor_active,
        # gate de engenharia: o perigo real e o PISO de C_NO a mascarar
        # X_NO = alpha; exige-se ainda residuo << escala da equacao.
        valid=(not floor_active) and (max_resnorm < opts.resnorm_tol),
        # regra literal: residuo minusculo E nenhuma restricao activa.
        valid_strict=(max_resnorm < opts.resnorm_tol_strict) and (not any_active),
        T_K=T_K, alpha=alpha, NO_in_ppm=NO_in_ppm, kads=kads, kNO=kNO,
    )


def solve_geometry_point(geometry: ReactorGeometry, **kwargs) -> PointResult:
    """Atalho: resolve usando uma ``ReactorGeometry`` (aplica o fouling)."""
    return solve_point(
        frontal_area_m2=geometry.effective_frontal_area_m2,
        length_m=geometry.length_m,
        substrate=geometry.substrate,
        **kwargs)
