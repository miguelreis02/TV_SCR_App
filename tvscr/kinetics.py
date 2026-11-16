"""
Cinetica e transporte do modelo de Tronconi, Cavanna & Forzatti (1998).

Os valores por omissao sao os da Tabela 2 do artigo (catalisador 1). Todos os
parametros sao inputs -- a aplicacao deve poder substitui-los sem tocar no
solver.

Dois "niveis" de parametrizacao, deliberadamente separados:

``KineticParameters``
    Os parametros fisicos propriamente ditos (pre-exponenciais, energias de
    activacao, difusividades). Inclui ``aging_KK0``, o factor de envelhecimento
    do catalisador que entra ao QUADRADO no pre-exponencial de reducao de NO
    (``k0NO_ef = k0NO * KK0^2``), tal como no MATLAB.

``KineticTuning``
    Multiplicadores adimensionais de CALIBRACAO (``opt.ktune`` no MATLAB),
    aplicados por cima da cinetica ja calculada. Tudo a 1 reproduz exactamente
    a cinetica de referencia.

NOTA (nao-identificabilidade): a temperatura fixa, a conversao so "ve" as
constantes agrupadas ``kads`` e ``kNO``. Variar ``k0`` ou ``E`` isoladamente a
T fixo e redundante; para sensibilidade a temperatura, varie ``T`` e deixe
Arrhenius actuar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

__all__ = ["KineticParameters", "KineticTuning", "GasConstants"]


@dataclass(frozen=True)
class GasConstants:
    """Constantes fisicas e premissas do gas."""

    R_cal: float = 1.987      # constante dos gases [cal/(mol.K)] -- energias em cal/mol
    R_J: float = 8.314        # constante dos gases [J/(mol.K)]   -- densidade do gas
    M_exhaust_g_mol: float = 29.0     # massa molar media do escape [g/mol] (NOx especifico)
    M_NOx_g_mol: float = 46.01        # massa molar do NOx, como NO2 [g/mol] (MARPOL NTC)


@dataclass(frozen=True)
class KineticTuning:
    """Multiplicadores de calibracao (``opt.ktune``). Tudo a 1 = referencia."""

    kNO: float = 1.0
    kads: float = 1.0
    Deff: float = 1.0
    k0d: float = 1.0

    @property
    def is_identity(self) -> bool:
        return (self.kNO == 1.0 and self.kads == 1.0
                and self.Deff == 1.0 and self.k0d == 1.0)

    def describe(self) -> str:
        return (f"kNO={self.kNO:.3f} kads={self.kads:.3f} "
                f"Deff={self.Deff:.3f} k0d={self.k0d:.3f}")


@dataclass(frozen=True)
class KineticParameters:
    """Cinetica + transporte do modelo 1-D.

    Parameters
    ----------
    k0ads, Eads:
        Adsorcao de NH3: ``kads = k0ads * exp(-Eads/(R T))``. ``Eads`` [cal/mol].
    k0NO, ENO:
        Reducao de NO: ``kNO = k0NO * KK0^2 * exp(-ENO/(R T))``. ``ENO`` [cal/mol].
    aging_KK0:
        Envelhecimento do catalisador [-]. ``1`` = novo (BOL); ``0.8`` = fim de
        vida tipico. Entra ao quadrado no pre-exponencial de reducao de NO.
    k0d, E0d, beta:
        Dessorcao de NH3 (isotermica de Temkin):
        ``kd = k0d * exp(-E0d*(1 - beta*theta)/(R T))``. ``E0d`` [cal/mol].
    f:
        Criterio NUMERICO da fronteira da regiao activa ``x*`` (Eq. A6).
        Nao e um parametro cinetico.
    Deff:
        Difusividade efetiva intraporo [m^2/s].
    Dmol:
        Difusividade molecular no gas [m^2/s] (entra no Sherwood local).
    M_bar_kg_mol:
        Massa molar media do gas [kg/mol] (densidade -> velocidade -> AV).
    """

    k0ads: float = 8.5e6
    Eads: float = 9.0e3
    k0NO: float = 2.5e10
    ENO: float = 18.6e3
    aging_KK0: float = 1.0
    k0d: float = 8.0e8
    E0d: float = 2.6e4
    beta: float = 0.32
    f: float = 0.01
    Deff: float = 1.0e-6
    Dmol: float = 8.0e-5
    M_bar_kg_mol: float = 0.02896
    gas: GasConstants = GasConstants()

    # ------------------------------------------------------------------ #
    @property
    def k0NO_effective(self) -> float:
        """Pre-exponencial de reducao de NO ja com o envelhecimento aplicado."""
        return self.k0NO * self.aging_KK0 ** 2

    def kads_at(self, T_K: float | np.ndarray) -> float | np.ndarray:
        """Constante agrupada de adsorcao de NH3 a temperatura ``T_K``."""
        return self.k0ads * np.exp(-self.Eads / (self.gas.R_cal * np.asarray(T_K, dtype=float)))

    def kNO_at(self, T_K: float | np.ndarray) -> float | np.ndarray:
        """Constante agrupada de reducao de NO a temperatura ``T_K``."""
        return self.k0NO_effective * np.exp(
            -self.ENO / (self.gas.R_cal * np.asarray(T_K, dtype=float)))

    # ------------------------------------------------------------------ #
    def with_tuning(self, tuning: KineticTuning) -> "KineticParameters":
        """Devolve uma copia com os multiplicadores de calibracao absorvidos.

        Multiplicar ``k0ads``/``k0NO`` e equivalente a multiplicar o valor de
        Arrhenius ja calculado (que e o que o MATLAB faz em ``apply_ktune``),
        mas mantem a cinetica coerente para qualquer temperatura.
        """
        if tuning.is_identity:
            return self
        return replace(
            self,
            k0ads=self.k0ads * tuning.kads,
            k0NO=self.k0NO * tuning.kNO,
            Deff=self.Deff * tuning.Deff,
            k0d=self.k0d * tuning.k0d,
        )

    def with_aging(self, KK0: float) -> "KineticParameters":
        return replace(self, aging_KK0=KK0)

    def describe(self) -> str:
        return (f"k0ads={self.k0ads:.3e} Eads={self.Eads:.4g} | "
                f"k0NO={self.k0NO:.3e} (KK0={self.aging_KK0:.3f}) ENO={self.ENO:.4g} | "
                f"k0d={self.k0d:.3e} E0d={self.E0d:.4g} beta={self.beta:.3f} | "
                f"Deff={self.Deff:.3e} Dmol={self.Dmol:.3e} f={self.f:.3g}")
