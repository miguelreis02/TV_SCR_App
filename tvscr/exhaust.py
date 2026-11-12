"""
Caudal massico de escape a partir do consumo e do excesso de ar.

Porte da parte de calculo de ``get_mass_dot_v3.m``. O script MATLAB fazia tres
coisas: lia o ficheiro de inputs, calculava os caudais, e desenhava. A leitura
esta em :mod:`tvscr.dataset` e o desenho passou para a interface; o calculo --
que e o que interessa ao modelo -- esta aqui.

Base fisica (identica a v1/v2/v3 do MATLAB)::

    m_fuel = SFOC[g/kWh] * P_travao[kW] / 3.6e6              [kg/s]
    m_exh  = m_fuel * (1 + AFR_estequiometrico * lambda)     [kg/s]

com ``lambda`` ponto a ponto, e o AFR estequiometrico obtido por balanco
elementar do combustivel (ver :mod:`tvscr.fuels`).

A premissa por tras da segunda linha e que TODO o ar admitido sai no escape:
o caudal de escape e o combustivel mais o ar, e o ar e ``lambda`` vezes o
estequiometrico. Nao ha fugas nem purgas contabilizadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

from .fuels import FuelComposition, get_fuel

__all__ = ["ExhaustFlow", "exhaust_flow", "exhaust_mass_flow"]

#: Massa molar media do gas de escape [kg/mol] (premissa; ver Tronconi 1998).
M_EXHAUST_KG_MOL = 0.02896


# ====================================================================== #
def exhaust_mass_flow(sfoc_g_per_kWh: Union[float, Sequence[float], np.ndarray],
                      power_kW: Union[float, Sequence[float], np.ndarray],
                      lambda_: Union[float, Sequence[float], np.ndarray],
                      afr_stoich: float) -> np.ndarray:
    """Caudal massico total de escape [kg/s], com ``lambda`` ponto a ponto.

    E o nucleo de ``get_mass_dot_v3.m``. Recebe o AFR estequiometrico ja
    calculado; para partir do nome do combustivel, use :func:`exhaust_flow`.
    """
    fuel = (np.asarray(sfoc_g_per_kWh, dtype=float)
            * np.asarray(power_kW, dtype=float) / 3.6e6)
    return fuel * (1.0 + afr_stoich * np.asarray(lambda_, dtype=float))


# ====================================================================== #
@dataclass
class ExhaustFlow:
    """Caudais de um conjunto de pontos de operacao, com os intermedios.

    Guardar os intermedios (caudal de combustivel, AFR, caudal molar) e o que
    permite conferir o resultado sem repetir a conta -- era o que o
    ``verborose`` do script MATLAB imprimia.
    """

    fuel: FuelComposition
    afr_stoich: float                       # [kg ar / kg combustivel]
    load_pct: Optional[np.ndarray]
    power_kW: np.ndarray
    sfoc_g_per_kWh: np.ndarray
    lambda_: np.ndarray
    fuel_mass_flow_kgs: np.ndarray
    exhaust_mass_flow_kgs: np.ndarray
    M_exhaust_kg_mol: float = M_EXHAUST_KG_MOL

    @property
    def exhaust_molar_flow_mols(self) -> np.ndarray:
        """Caudal molar de escape [mol/s]."""
        return self.exhaust_mass_flow_kgs / self.M_exhaust_kg_mol

    @property
    def air_mass_flow_kgs(self) -> np.ndarray:
        """Caudal de ar admitido [kg/s] = escape menos combustivel."""
        return self.exhaust_mass_flow_kgs - self.fuel_mass_flow_kgs

    @property
    def fuel_consumption_kg_h(self) -> np.ndarray:
        """Consumo de combustivel [kg/h] (a coluna que o dataset traz)."""
        return self.fuel_mass_flow_kgs * 3600.0

    def to_dataframe(self) -> pd.DataFrame:
        data = {
            "P_travao_kW": self.power_kW,
            "SFOC_g_kWh": self.sfoc_g_per_kWh,
            "lambda": self.lambda_,
            "m_fuel_kg_s": self.fuel_mass_flow_kgs,
            "consumo_kg_h": self.fuel_consumption_kg_h,
            "m_ar_kg_s": self.air_mass_flow_kgs,
            "m_exh_kg_s": self.exhaust_mass_flow_kgs,
            "n_exh_mol_s": self.exhaust_molar_flow_mols,
        }
        if self.load_pct is not None:
            data = {"Carga_perc": self.load_pct, **data}
        return pd.DataFrame(data)

    def describe(self) -> str:
        lines = [
            f"Combustivel: {self.fuel.name}  |  AFR estequiometrico = "
            f"{self.afr_stoich:.3f} kg ar / kg comb.",
            f"{'Carga%':>8} {'P[kW]':>10} {'SFOC':>8} {'lambda':>8} "
            f"{'m_fuel':>10} {'m_ar':>10} {'m_exh[kg/s]':>12}",
        ]
        loads = (self.load_pct if self.load_pct is not None
                 else np.full(self.power_kW.shape, np.nan))
        for i in range(self.power_kW.size):
            lines.append(
                f"{loads[i]:8.2f} {self.power_kW[i]:10.1f} "
                f"{self.sfoc_g_per_kWh[i]:8.1f} {self.lambda_[i]:8.3f} "
                f"{self.fuel_mass_flow_kgs[i]:10.4f} "
                f"{self.air_mass_flow_kgs[i]:10.3f} "
                f"{self.exhaust_mass_flow_kgs[i]:12.4f}")
        lines.append(f"m_exh: {self.exhaust_mass_flow_kgs.min():.3f} a "
                     f"{self.exhaust_mass_flow_kgs.max():.3f} kg/s")
        return "\n".join(lines)


def exhaust_flow(sfoc_g_per_kWh: Union[float, Sequence[float], np.ndarray],
                 power_kW: Union[float, Sequence[float], np.ndarray],
                 lambda_: Union[float, Sequence[float], np.ndarray],
                 fuel: Union[str, FuelComposition] = "HFO",
                 load_pct: Optional[Sequence[float]] = None,
                 M_exhaust_kg_mol: float = M_EXHAUST_KG_MOL) -> ExhaustFlow:
    """Calcula os caudais de escape a partir do consumo e do excesso de ar.

    Parameters
    ----------
    sfoc_g_per_kWh:
        Consumo especifico de combustivel, por ponto de operacao [g/kWh].
    power_kW:
        Potencia de travao, por ponto [kW].
    lambda_:
        Excesso de ar, por ponto [-].
    fuel:
        Nome no catalogo (``"HFO"``, ``"MDO"``, ``"MGO"``, ``"LSFO"``) ou uma
        :class:`~tvscr.fuels.FuelComposition` para um combustivel novo.
    load_pct:
        Cargas, so para o relatorio.
    M_exhaust_kg_mol:
        Massa molar media do gas de escape, usada no caudal molar.

    Returns
    -------
    ExhaustFlow
        Com o caudal de escape e todos os intermedios.

    Examples
    --------
    >>> flow = exhaust_flow([229.5, 208.0], [636.9, 2894.8], [3.42, 2.37], "HFO")
    >>> flow.exhaust_mass_flow_kgs.round(4)
    array([1.9229, 5.542 ])
    """
    composition = get_fuel(fuel)
    sfoc = np.atleast_1d(np.asarray(sfoc_g_per_kWh, dtype=float)).ravel()
    power = np.atleast_1d(np.asarray(power_kW, dtype=float)).ravel()
    lam = np.atleast_1d(np.asarray(lambda_, dtype=float)).ravel()

    if not (sfoc.size == power.size == lam.size):
        raise ValueError(
            f"exhaust_flow: SFOC ({sfoc.size}), potencia ({power.size}) e lambda "
            f"({lam.size}) tem de ter o mesmo numero de pontos.")

    fuel_flow = sfoc * power / 3.6e6
    exhaust = fuel_flow * (1.0 + composition.afr_stoich * lam)

    return ExhaustFlow(
        fuel=composition, afr_stoich=composition.afr_stoich,
        load_pct=(np.asarray(list(load_pct), dtype=float)
                  if load_pct is not None else None),
        power_kW=power, sfoc_g_per_kWh=sfoc, lambda_=lam,
        fuel_mass_flow_kgs=fuel_flow, exhaust_mass_flow_kgs=exhaust,
        M_exhaust_kg_mol=M_exhaust_kg_mol)
