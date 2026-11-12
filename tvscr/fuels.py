"""
Combustiveis marinhos: composicao elementar e AFR estequiometrico.

Porte de ``stoich_AFR`` (subfuncao de ``get_mass_dot_v3.m``). A composicao e
um input: ``FuelComposition`` pode ser instanciada com quaisquer fraccoes
massicas, e o catalogo ``FUEL_LIBRARY`` so fornece os valores por omissao dos
quatro combustiveis usados no dataset original.

Base fisica::

    C  + O2   -> CO2       1     mol O2 / mol C
    4H + O2   -> 2 H2O     1/4   mol O2 / mol H
    S  + O2   -> SO2       1     mol O2 / mol S

    AFR = (n_C + n_H/4 + n_S) * M_O2 / Y_O2_ar   [kg ar / kg combustivel]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Union

__all__ = ["FuelComposition", "FUEL_LIBRARY", "get_fuel", "stoich_afr"]

# Massas molares [g/mol]
M_C = 12.011
M_H = 1.008
M_S = 32.06
M_O2 = 31.998


@dataclass(frozen=True)
class FuelComposition:
    """Composicao elementar de um combustivel, em fraccoes MASSICAS.

    Parameters
    ----------
    name:
        Etiqueta do combustivel.
    carbon, hydrogen, sulphur:
        Fraccoes massicas [-]. Nao tem de somar 1 (o resto e considerado
        inerte/oxigenado e nao consome ar).
    oxygen_mass_fraction_air:
        Fraccao MASSICA de O2 no ar seco [-] (0.2314 por omissao).
    """

    name: str
    carbon: float
    hydrogen: float
    sulphur: float
    oxygen_mass_fraction_air: float = 0.2314

    @property
    def afr_stoich(self) -> float:
        """AFR estequiometrico [kg ar / kg combustivel REAL, com enxofre]."""
        n_C = 1000.0 * self.carbon / M_C          # [mol/kg combustivel]
        n_H = 1000.0 * self.hydrogen / M_H
        n_S = 1000.0 * self.sulphur / M_S
        o2_demand = n_C + n_H / 4.0 + n_S         # [mol O2 / kg combustivel]
        return o2_demand * M_O2 / self.oxygen_mass_fraction_air / 1000.0

    def describe(self) -> str:
        return (f"{self.name}: C={self.carbon:.4f} H={self.hydrogen:.4f} "
                f"S={self.sulphur:.4f} -> AFR_st={self.afr_stoich:.3f}")


#: Catalogo por omissao (valores de ``stoich_AFR`` no MATLAB).
FUEL_LIBRARY: Dict[str, FuelComposition] = {
    "HFO":  FuelComposition("HFO",  carbon=0.8490, hydrogen=0.1050, sulphur=0.0400),
    "MDO":  FuelComposition("MDO",  carbon=0.8550, hydrogen=0.1250, sulphur=0.0150),
    "MGO":  FuelComposition("MGO",  carbon=0.8570, hydrogen=0.1300, sulphur=0.0090),
    "LSFO": FuelComposition("LSFO", carbon=0.8600, hydrogen=0.1150, sulphur=0.0050),
}


def get_fuel(fuel: Union[str, FuelComposition]) -> FuelComposition:
    """Resolve um combustivel por nome ou devolve a composicao dada."""
    if isinstance(fuel, FuelComposition):
        return fuel
    key = str(fuel).strip().upper()
    if key not in FUEL_LIBRARY:
        raise KeyError(
            f'Composicao nao definida para o combustivel "{fuel}". '
            f"Conhecidos: {sorted(FUEL_LIBRARY)}. "
            f"Passe uma FuelComposition para um combustivel novo.")
    return FUEL_LIBRARY[key]


def stoich_afr(fuel: Union[str, FuelComposition]) -> float:
    """AFR estequiometrico [kg ar / kg combustivel]."""
    return get_fuel(fuel).afr_stoich
