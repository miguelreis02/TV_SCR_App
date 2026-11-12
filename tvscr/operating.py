"""
Ponto de operacao, ciclo de ensaio e caso de motor.

Reune o que no MATLAB estava repartido entre ``get_mass_dot_v3.m`` (caudais,
limite Tier III, geometria instalada) e ``precompute_D2_inputs_DGX.m``
(Arrhenius por modo, pesos do ciclo, alpha calibrado).

Tudo e input explicito. ``EngineCase`` pode ser construido:

* a partir do CSV consolidado -- ver :mod:`tvscr.dataset`;
* a partir de listas de valores medidos, sem CSV nenhum;
* modo a modo, se a aplicacao recolher os dados de outra fonte.

O numero de modos NAO esta fixado em 4: o ciclo pode ter os modos que tiver.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Optional, Sequence

import numpy as np

from .exhaust import exhaust_mass_flow
from .geometry import ReactorGeometry
from .kinetics import KineticParameters, KineticTuning
from .numerics import interp1_linear

__all__ = [
    "OperatingMode",
    "EngineCase",
    "nox_limit_gkwh",
    "specific_nox_gkwh",
    "nox_ppm_from_specific",
    "exhaust_mass_flow",
]


# ====================================================================== #
#  Limite regulamentar de NOx
# ====================================================================== #
#: Coeficientes MARPOL Anexo VI, Reg. 13: (limite n<130, a, b, limite n>=2000)
#: para ``limite = a * n^-b`` na gama 130 <= n < 2000.
_TIER_COEFFS = {
    "I":   (17.0, 45.0, 0.20, 9.8),
    "II":  (14.4, 44.0, 0.23, 7.7),
    "III": (3.4,  9.0,  0.20, 2.0),
}


def nox_limit_gkwh(engine_speed_rpm: float, tier: str = "III",
                   power_law_only: bool = False) -> float:
    """Limite de NOx [g/kWh] em funcao da rotacao nominal do motor.

    Parameters
    ----------
    engine_speed_rpm:
        Rotacao nominal ``n`` [rpm].
    tier:
        ``"I"``, ``"II"`` ou ``"III"``.
    power_law_only:
        Se ``True``, aplica a lei de potencia em toda a gama, sem os patamares
        de ``n < 130`` e ``n >= 2000``. E o que o MATLAB faz
        (``9*n^-0.2``); os dois coincidem para ``130 <= n < 2000``, que e o
        caso dos motores do dataset (513 rpm). Deixado como opcao para
        reproduzir resultados antigos bit a bit.
    """
    key = str(tier).strip().upper().replace("TIER", "").strip()
    if key not in _TIER_COEFFS:
        raise ValueError(f'Tier desconhecido: "{tier}". Use I, II ou III.')
    low, a, b, high = _TIER_COEFFS[key]
    n = float(engine_speed_rpm)
    if power_law_only:
        return a * n ** (-b)
    if n < 130.0:
        return low
    if n >= 2000.0:
        return high
    return a * n ** (-b)


# ====================================================================== #
#  Conversoes ppm <-> g/kWh
# ====================================================================== #
def specific_nox_gkwh(NO_ppm: np.ndarray | float,
                      mass_flow_kgs: np.ndarray | float,
                      power_kW: np.ndarray | float,
                      M_NO_g_mol: float = 46.01,
                      M_exhaust_g_mol: float = 29.0):
    """Converte NO [ppm] em NOx especifico [g/kWh].

    ``NOx[g/kWh] = ppm * 3600 * mdot * M_NO2 / (P * M_exh * 1000)``

    O NOx especifico e expresso como NO2 (MARPOL Anexo VI / NOx Technical
    Code), pelo que ``M_NO_g_mol`` e por omissao a massa molar do NO2.
    """
    return (np.asarray(NO_ppm, dtype=float) * 3600.0
            * np.asarray(mass_flow_kgs, dtype=float) * M_NO_g_mol
            / np.asarray(power_kW, dtype=float) / M_exhaust_g_mol / 1000.0)


def nox_ppm_from_specific(NO_gkwh: np.ndarray | float,
                          mass_flow_kgs: np.ndarray | float,
                          power_kW: np.ndarray | float,
                          M_NO_g_mol: float = 46.01,
                          M_exhaust_g_mol: float = 29.0):
    """Inversa de :func:`specific_nox_gkwh`: NOx especifico [g/kWh] -> [ppm]."""
    return (np.asarray(NO_gkwh, dtype=float) * np.asarray(power_kW, dtype=float)
            * M_exhaust_g_mol * 1000.0
            / (3600.0 * np.asarray(mass_flow_kgs, dtype=float) * M_NO_g_mol))


# ====================================================================== #
#  Modo de operacao
# ====================================================================== #
@dataclass(frozen=True)
class OperatingMode:
    """Um ponto do ciclo de ensaio (um "modo").

    Parameters
    ----------
    load_pct:
        Carga de travao [%].
    weight:
        Peso do modo no ciclo [%] (ou qualquer unidade -- so a razao conta).
    power_kW:
        Potencia de travao [kW].
    exhaust_mass_flow_kgs:
        Caudal massico total de escape [kg/s].
    T_in_K:
        Temperatura a entrada do SCR [K].
    NO_in_ppm:
        NO a entrada do SCR (engine-out) [ppm].
    NO_out_ppm:
        NO medido a saida [ppm]. Opcional -- so serve para calibracao e
        diagnostico.
    fuel_mass_flow_kgs, lambda_, sfoc_g_per_kWh:
        Grandezas intermedias, guardadas para relatorio.
    """

    load_pct: float
    weight: float
    power_kW: float
    exhaust_mass_flow_kgs: float
    T_in_K: float
    NO_in_ppm: float
    NO_out_ppm: Optional[float] = None
    fuel_mass_flow_kgs: Optional[float] = None
    lambda_: Optional[float] = None
    sfoc_g_per_kWh: Optional[float] = None

    @property
    def T_in_C(self) -> float:
        return self.T_in_K - 273.15

    @property
    def measured_conversion_pct(self) -> Optional[float]:
        """Conversao medida ``100*(1 - NO_out/NO_in)`` [%], se houver medida."""
        if self.NO_out_ppm is None or self.NO_in_ppm == 0.0:
            return None
        return 100.0 * (1.0 - self.NO_out_ppm / self.NO_in_ppm)


# ====================================================================== #
#  Caso de motor
# ====================================================================== #
@dataclass
class EngineCase:
    """Motor + ciclo de ensaio + geometria instalada + cinetica.

    Os modos sao SEMPRE reordenados por carga crescente na construcao, para
    que a ponderacao do ciclo (que interpola na carga) fique bem definida.
    """

    name: str
    modes: Sequence[OperatingMode]
    geometry: ReactorGeometry
    kinetics: KineticParameters = field(default_factory=KineticParameters)
    nox_limit_gkWh: Optional[float] = None
    engine_speed_rpm: Optional[float] = None
    rated_power_kW: Optional[float] = None
    pressure_Pa: float = 101325.0
    fuel: str = "HFO"
    alpha_calibrated: Optional[np.ndarray] = None
    tier: str = "III"
    tier_power_law_only: bool = False

    def __post_init__(self) -> None:
        modes = list(self.modes)
        if not modes:
            raise ValueError("EngineCase: e preciso pelo menos um modo de operacao.")
        order = np.argsort([m.load_pct for m in modes], kind="stable")
        self.modes = tuple(modes[i] for i in order)

        if self.alpha_calibrated is not None:
            alpha = np.asarray(self.alpha_calibrated, dtype=float).ravel()
            if alpha.size != len(self.modes):
                raise ValueError(
                    f"alpha calibrado tem {alpha.size} pontos mas o ciclo tem "
                    f"{len(self.modes)} modos.")
            self.alpha_calibrated = alpha[order]

        if self.nox_limit_gkWh is None:
            if self.engine_speed_rpm is None:
                raise ValueError(
                    "EngineCase: indique nox_limit_gkWh ou engine_speed_rpm "
                    "para derivar o limite regulamentar.")
            self.nox_limit_gkWh = nox_limit_gkwh(
                self.engine_speed_rpm, self.tier, self.tier_power_law_only)

    # ---------------- vistas vectorizadas ------------------------------ #
    @property
    def n_modes(self) -> int:
        return len(self.modes)

    @property
    def has_measured_outlet(self) -> bool:
        """Ha NO medido a saida? So serve para calibrar alpha."""
        return any(m.NO_out_ppm is not None for m in self.modes)

    def _col(self, attr: str) -> np.ndarray:
        return np.array([getattr(m, attr) for m in self.modes], dtype=float)

    @property
    def load_pct(self) -> np.ndarray:
        return self._col("load_pct")

    @property
    def weight(self) -> np.ndarray:
        return self._col("weight")

    @property
    def power_kW(self) -> np.ndarray:
        return self._col("power_kW")

    @property
    def mass_flow_kgs(self) -> np.ndarray:
        return self._col("exhaust_mass_flow_kgs")

    @property
    def T_K(self) -> np.ndarray:
        return self._col("T_in_K")

    @property
    def NO_in_ppm(self) -> np.ndarray:
        return self._col("NO_in_ppm")

    @property
    def NO_out_ppm(self) -> np.ndarray:
        return np.array([np.nan if m.NO_out_ppm is None else m.NO_out_ppm
                         for m in self.modes], dtype=float)

    @property
    def measured_conversion_pct(self) -> np.ndarray:
        return 100.0 * (1.0 - self.NO_out_ppm / self.NO_in_ppm)

    # ---------------- cinetica por modo -------------------------------- #
    def mode_kads(self, tuning: Optional[KineticTuning] = None) -> np.ndarray:
        kin = self.kinetics if tuning is None else self.kinetics.with_tuning(tuning)
        return np.asarray(kin.kads_at(self.T_K), dtype=float)

    def mode_kNO(self, tuning: Optional[KineticTuning] = None) -> np.ndarray:
        kin = self.kinetics if tuning is None else self.kinetics.with_tuning(tuning)
        return np.asarray(kin.kNO_at(self.T_K), dtype=float)

    # ---------------- ponderacao do ciclo ------------------------------ #
    def cycle_average(self, per_mode: np.ndarray) -> float:
        """Media ponderada de uma grandeza por modo, sobre o ciclo.

        Reproduz ``run_D2_geom``: interpola a grandeza nas cargas do ciclo
        (identidade quando os modos SAO os pontos do ciclo, que e o caso do
        dataset) e faz a media com os pesos.
        """
        loads = self.load_pct
        values = np.asarray(per_mode, dtype=float).ravel()
        at_cycle = interp1_linear(loads, values, loads)
        w = self.weight
        return float(np.sum(w * at_cycle) / np.sum(w))

    def weighted_average(self, per_mode: np.ndarray) -> float:
        """Media ponderada directa (sem interpolacao)."""
        w = self.weight
        v = np.asarray(per_mode, dtype=float).ravel()
        return float(np.sum(w * v) / np.sum(w))

    # ---------------- alvos derivados ---------------------------------- #
    def required_conversion_pct(self, target_gkwh: float) -> np.ndarray:
        """Conversao minima por modo equivalente a um alvo de NOx [g/kWh].

        Diagnostico: e a mesma restricao de ``NO_out <= alvo``, expressa como
        conversao.
        """
        ppm_target = nox_ppm_from_specific(
            target_gkwh, self.mass_flow_kgs, self.power_kW,
            self.kinetics.gas.M_NO_g_mol, self.kinetics.gas.M_exhaust_g_mol)
        return 100.0 * (1.0 - ppm_target / self.NO_in_ppm)

    def specific_nox(self, NO_out_ppm: np.ndarray) -> np.ndarray:
        """NOx especifico por modo [g/kWh] a partir do NO a saida [ppm]."""
        return specific_nox_gkwh(
            NO_out_ppm, self.mass_flow_kgs, self.power_kW,
            self.kinetics.gas.M_NO_g_mol, self.kinetics.gas.M_exhaust_g_mol)

    # ---------------- variantes ---------------------------------------- #
    def with_geometry(self, geometry: ReactorGeometry) -> "EngineCase":
        return replace(self, geometry=geometry, modes=list(self.modes))

    def with_kinetics(self, kinetics: KineticParameters) -> "EngineCase":
        return replace(self, kinetics=kinetics, modes=list(self.modes))

    def with_fouling(self, fouling: float) -> "EngineCase":
        return self.with_geometry(self.geometry.with_fouling(fouling))

    def with_substrate(self, substrate) -> "EngineCase":
        """Mesmo motor e mesmo monolito, outra geometria de celula."""
        return self.with_geometry(self.geometry.with_substrate(substrate))

    def with_aging(self, KK0: float) -> "EngineCase":
        return self.with_kinetics(self.kinetics.with_aging(KK0))

    def with_tuning(self, tuning: KineticTuning) -> "EngineCase":
        return self.with_kinetics(self.kinetics.with_tuning(tuning))

    # ---------------- construtor a partir de colunas -------------------- #
    @classmethod
    def from_arrays(cls, name: str, geometry: ReactorGeometry, *,
                    load_pct: Iterable[float],
                    weight: Iterable[float],
                    power_kW: Iterable[float],
                    T_in_K: Iterable[float],
                    NO_in_ppm: Iterable[float],
                    exhaust_mass_flow_kgs: Optional[Iterable[float]] = None,
                    sfoc_g_per_kWh: Optional[Iterable[float]] = None,
                    lambda_: Optional[Iterable[float]] = None,
                    fuel: str = "HFO",
                    NO_out_ppm: Optional[Iterable[float]] = None,
                    **kwargs) -> "EngineCase":
        """Constroi o caso a partir de colunas medidas, sem CSV.

        ``exhaust_mass_flow_kgs`` pode ser omitido se forem dados
        ``sfoc_g_per_kWh`` e ``lambda_`` -- nesse caso e calculado pelo balanco
        de combustivel + ar (``m_exh = m_fuel*(1 + AFR_st*lambda)``).
        """
        from .fuels import stoich_afr

        load = np.asarray(list(load_pct), dtype=float)
        w = np.asarray(list(weight), dtype=float)
        P = np.asarray(list(power_kW), dtype=float)
        T = np.asarray(list(T_in_K), dtype=float)
        NO_in = np.asarray(list(NO_in_ppm), dtype=float)

        if exhaust_mass_flow_kgs is not None:
            mdot = np.asarray(list(exhaust_mass_flow_kgs), dtype=float)
            fuel_flow = np.full(mdot.shape, np.nan)
            lam = (np.asarray(list(lambda_), dtype=float)
                   if lambda_ is not None else np.full(mdot.shape, np.nan))
            sfoc = (np.asarray(list(sfoc_g_per_kWh), dtype=float)
                    if sfoc_g_per_kWh is not None else np.full(mdot.shape, np.nan))
        else:
            if sfoc_g_per_kWh is None or lambda_ is None:
                raise ValueError(
                    "from_arrays: forneca exhaust_mass_flow_kgs, ou "
                    "sfoc_g_per_kWh + lambda_ para o calcular.")
            sfoc = np.asarray(list(sfoc_g_per_kWh), dtype=float)
            lam = np.asarray(list(lambda_), dtype=float)
            fuel_flow = sfoc * P / 3.6e6
            mdot = exhaust_mass_flow(sfoc, P, lam, stoich_afr(fuel))

        NO_out = (np.asarray(list(NO_out_ppm), dtype=float)
                  if NO_out_ppm is not None else np.full(load.shape, np.nan))

        modes = [
            OperatingMode(
                load_pct=float(load[i]), weight=float(w[i]), power_kW=float(P[i]),
                exhaust_mass_flow_kgs=float(mdot[i]), T_in_K=float(T[i]),
                NO_in_ppm=float(NO_in[i]),
                NO_out_ppm=None if np.isnan(NO_out[i]) else float(NO_out[i]),
                fuel_mass_flow_kgs=None if np.isnan(fuel_flow[i]) else float(fuel_flow[i]),
                lambda_=None if np.isnan(lam[i]) else float(lam[i]),
                sfoc_g_per_kWh=None if np.isnan(sfoc[i]) else float(sfoc[i]),
            )
            for i in range(load.size)
        ]
        return cls(name=name, modes=modes, geometry=geometry, fuel=fuel, **kwargs)

    # ---------------- resumo -------------------------------------------- #
    def describe(self) -> str:
        measured = self.has_measured_outlet
        header = (f"  {'Load%':>7} {'W[%]':>7} {'P[kW]':>10} {'T[K]':>8} "
                  f"{'NOin':>8} {'mexh[kg/s]':>11}")
        if measured:
            header += f" {'NOout':>8} {'Xmed%':>8}"
        lines = [
            f"{self.name} | combustivel {self.fuel} | "
            f"{self.n_modes} modos | Tier {self.tier} = {self.nox_limit_gkWh:.4f} g/kWh",
            f"  Reator: {self.geometry.describe()}",
            header,
        ]
        X = self.measured_conversion_pct if measured else None
        for i, m in enumerate(self.modes):
            row = (f"  {m.load_pct:7.2f} {m.weight:7.2f} {m.power_kW:10.1f} "
                   f"{m.T_in_K:8.1f} {m.NO_in_ppm:8.1f} "
                   f"{m.exhaust_mass_flow_kgs:11.4f}")
            if measured:
                row += (f" {m.NO_out_ppm:8.1f} {X[i]:8.2f}"
                        if m.NO_out_ppm is not None else f" {'-':>8} {'-':>8}")
            lines.append(row)
        return "\n".join(lines)
