"""
Doseamento: conversao alpha <-> caudal de solucao de ureia.

Porte de ``urea_flow_Lh.m`` (com as propriedades da solucao parametrizaveis)
e de ``nh3_ppm.m`` (curva de doseamento da empresa, usada como ponto de
partida da calibracao de alpha).

Cadeia estequiometrica::

    n_exh  = mdot / M_exh              [mol/s]
    y_NH3  = alpha * NO_in * 1e-6      [-]
    n_NH3  = y_NH3 * n_exh             [mol/s]
    n_urea = n_NH3 / nu                [mol/s]   (CO(NH2)2 -> 2 NH3)
    m_sol  = n_urea * M_urea / w_urea  [kg/s]
    V_dot  = m_sol / rho_sol           [m3/s] -> [L/h]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Union

import numpy as np

__all__ = ["UreaSolution", "urea_flow_Lh", "alpha_from_urea_flow", "DosingCurve"]


@dataclass(frozen=True)
class UreaSolution:
    """Propriedades da solucao de ureia doseada.

    Parameters
    ----------
    mass_fraction:
        Fraccao massica de ureia na solucao [-] (0.40 = AUS 40).
    density_kg_m3:
        Densidade da solucao [kg/m3].
    M_urea_kg_mol:
        Massa molar da ureia [kg/mol].
    M_exhaust_kg_mol:
        Massa molar media do gas de escape [kg/mol].
    nh3_per_urea:
        Moles de NH3 libertadas por mole de ureia [-].
    """

    mass_fraction: float = 0.40
    density_kg_m3: float = 1109.0
    M_urea_kg_mol: float = 0.06006
    M_exhaust_kg_mol: float = 0.02896
    nh3_per_urea: float = 2.0


DEFAULT_UREA = UreaSolution()


def urea_flow_Lh(alpha: Union[float, Sequence[float], np.ndarray],
                 NO_in_ppm: Union[float, Sequence[float], np.ndarray],
                 mass_flow_kgs: Union[float, Sequence[float], np.ndarray],
                 solution: UreaSolution = DEFAULT_UREA) -> np.ndarray:
    """Caudal de solucao de ureia [L/h] a partir de alpha.

    Vectorizado: ``alpha``, ``NO_in_ppm`` e ``mass_flow_kgs`` podem ser
    vectores do mesmo tamanho (um por modo do ciclo).
    """
    a = np.atleast_1d(np.asarray(alpha, dtype=float)).ravel()
    no = np.atleast_1d(np.asarray(NO_in_ppm, dtype=float)).ravel()
    md = np.atleast_1d(np.asarray(mass_flow_kgs, dtype=float)).ravel()

    n_exh = md / solution.M_exhaust_kg_mol            # [mol/s]
    n_NH3 = (a * no * 1e-6) * n_exh                   # [mol/s]
    n_urea = n_NH3 / solution.nh3_per_urea            # [mol/s]
    m_sol = n_urea * solution.M_urea_kg_mol / solution.mass_fraction   # [kg/s]
    return (m_sol / solution.density_kg_m3) * 1000.0 * 3600.0          # [L/h]


def alpha_from_urea_flow(flow_Lh: Union[float, Sequence[float], np.ndarray],
                         NO_in_ppm: Union[float, Sequence[float], np.ndarray],
                         mass_flow_kgs: Union[float, Sequence[float], np.ndarray],
                         solution: UreaSolution = DEFAULT_UREA) -> np.ndarray:
    """Inversa de :func:`urea_flow_Lh`: caudal de solucao [L/h] -> alpha [-]."""
    q = np.atleast_1d(np.asarray(flow_Lh, dtype=float)).ravel()
    no = np.atleast_1d(np.asarray(NO_in_ppm, dtype=float)).ravel()
    md = np.atleast_1d(np.asarray(mass_flow_kgs, dtype=float)).ravel()

    m_sol = q * solution.density_kg_m3 / (1000.0 * 3600.0)             # [kg/s]
    n_urea = m_sol * solution.mass_fraction / solution.M_urea_kg_mol   # [mol/s]
    n_NH3 = n_urea * solution.nh3_per_urea
    n_exh = md / solution.M_exhaust_kg_mol
    return (n_NH3 / n_exh) / (no * 1e-6)


@dataclass(frozen=True)
class DosingCurve:
    """Curva de doseamento em funcao da carga (porte de ``nh3_ppm.m``).

    ``coefficients`` sao os do polinomio ``caudal_solucao[kg/h] = p(load_pct)``,
    pela convencao do ``polyval`` (grau decrescente). Os valores por omissao
    sao os da curva de implementacao do fabricante -- substituiveis.

    So e usada como ponto de partida da calibracao de alpha; o dimensionamento
    nao depende dela.
    """

    coefficients: tuple = (-0.0001016140129995, 0.0132698365795422,
                           0.3682120882200640, 2.6331172842886800)
    urea_mass_fraction: float = 0.40
    M_urea_g_mol: float = 60.056
    M_exhaust_g_mol: float = 28.85
    nh3_per_urea: float = 2.0

    def solution_flow_kg_h(self, load_pct: Union[float, np.ndarray]) -> np.ndarray:
        """Caudal de solucao [kg/h] a carga dada."""
        return np.polyval(np.asarray(self.coefficients, dtype=float),
                          np.asarray(load_pct, dtype=float))

    def nh3_ppm(self, load_pct: Union[float, np.ndarray],
                exhaust_mass_flow_kg_h: Union[float, np.ndarray]) -> np.ndarray:
        """Concentracao de NH3 no escape [ppm].

        ``exhaust_mass_flow_kg_h`` tem de estar em **kg/h** (mesma base
        temporal do polinomio).
        """
        y = self.solution_flow_kg_h(load_pct)                       # [kg/h]
        n_urea = (self.urea_mass_fraction * y) / self.M_urea_g_mol  # [kmol/h]
        n_NH3 = self.nh3_per_urea * n_urea                          # [kmol/h]
        n_exh = np.asarray(exhaust_mass_flow_kg_h, dtype=float) / self.M_exhaust_g_mol
        return (n_NH3 / n_exh) * 1e6

    def alpha(self, load_pct: Union[float, np.ndarray],
              exhaust_mass_flow_kg_h: Union[float, np.ndarray],
              NO_in_ppm: Union[float, np.ndarray]) -> np.ndarray:
        """Alpha implicito na curva de doseamento."""
        return self.nh3_ppm(load_pct, exhaust_mass_flow_kg_h) / np.asarray(
            NO_in_ppm, dtype=float)
