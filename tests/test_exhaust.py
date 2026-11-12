"""
Caudal massico de escape -- porte da parte de calculo de ``get_mass_dot_v3.m``.

A referencia e o proprio dataset consolidado: o ficheiro traz a coluna
``Fuel_Consumption_[kgh]``, que e o caudal de combustivel calculado no MATLAB
a partir do SFOC e da potencia. Se o porte reproduzir essa coluna, reproduz o
primeiro passo; o segundo (``m_exh = m_fuel*(1 + AFR_st*lambda)``) e uma
multiplicacao pelo AFR, testado a parte contra o balanco elementar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (EngineDataset, FuelComposition, exhaust_flow,
                   exhaust_mass_flow, stoich_afr)
from tvscr.exhaust import M_EXHAUST_KG_MOL

CSV_INPUTS = Path(r"D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\Tronconi1998"
                  r"\Data Set\Tabela_Inputs_Final.csv")

# DG1, os quatro modos do ciclo (do dataset consolidado).
SFOC = [229.5081967, 222.3602484, 208.0378251, 197.021764]
POWER = [636.9007854, 1403.378922, 2894.804234, 4212.856149]
LAMBDA = [3.421805002, 2.678748806, 2.371493289, 2.181210024]


# --------------------------------------------------------------------- #
#  AFR estequiometrico
# --------------------------------------------------------------------- #
def test_afr_from_elemental_balance():
    """C + O2, 4H + O2, S + O2, por kg de combustivel REAL."""
    fuel = FuelComposition("teste", carbon=0.85, hydrogen=0.10, sulphur=0.04)
    n_C = 1000 * 0.85 / 12.011
    n_H = 1000 * 0.10 / 1.008
    n_S = 1000 * 0.04 / 32.06
    esperado = (n_C + n_H / 4 + n_S) * 31.998 / 0.2314 / 1000
    assert fuel.afr_stoich == pytest.approx(esperado, rel=1e-12)


def test_hfo_afr_matches_the_matlab_value():
    # stoich_AFR('HFO') no MATLAB, com C=0.849 H=0.105 S=0.040
    assert stoich_afr("HFO") == pytest.approx(13.548, abs=5e-4)


# --------------------------------------------------------------------- #
#  Caudais
# --------------------------------------------------------------------- #
def test_fuel_flow_is_sfoc_times_power():
    flow = exhaust_flow(SFOC, POWER, LAMBDA, "HFO")
    np.testing.assert_allclose(
        flow.fuel_mass_flow_kgs,
        np.array(SFOC) * np.array(POWER) / 3.6e6, rtol=1e-14)


def test_exhaust_is_fuel_plus_air():
    """m_exh = m_fuel + m_ar, com m_ar = AFR_st * lambda * m_fuel."""
    flow = exhaust_flow(SFOC, POWER, LAMBDA, "HFO")
    ar = flow.afr_stoich * np.array(LAMBDA) * flow.fuel_mass_flow_kgs
    np.testing.assert_allclose(flow.air_mass_flow_kgs, ar, rtol=1e-12)
    np.testing.assert_allclose(
        flow.exhaust_mass_flow_kgs, flow.fuel_mass_flow_kgs + ar, rtol=1e-12)


def test_molar_flow_uses_the_mean_molar_mass():
    flow = exhaust_flow(SFOC, POWER, LAMBDA, "HFO")
    np.testing.assert_allclose(
        flow.exhaust_molar_flow_mols,
        flow.exhaust_mass_flow_kgs / M_EXHAUST_KG_MOL, rtol=1e-14)


def test_the_two_entry_points_agree():
    """``exhaust_flow`` e ``exhaust_mass_flow`` tem de dar o mesmo."""
    flow = exhaust_flow(SFOC, POWER, LAMBDA, "HFO")
    direct = exhaust_mass_flow(SFOC, POWER, LAMBDA, stoich_afr("HFO"))
    np.testing.assert_allclose(flow.exhaust_mass_flow_kgs, direct, rtol=1e-14)


def test_more_air_means_more_exhaust():
    baixo = exhaust_flow([200.0], [1000.0], [2.0], "HFO")
    alto = exhaust_flow([200.0], [1000.0], [4.0], "HFO")
    assert alto.exhaust_mass_flow_kgs[0] > baixo.exhaust_mass_flow_kgs[0]
    # o combustivel e o mesmo; so muda o ar
    np.testing.assert_allclose(alto.fuel_mass_flow_kgs,
                               baixo.fuel_mass_flow_kgs, rtol=1e-14)


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError):
        exhaust_flow([200.0, 210.0], [1000.0], [2.0], "HFO")


def test_a_custom_fuel_is_accepted():
    fuel = FuelComposition("bio", carbon=0.77, hydrogen=0.12, sulphur=0.0)
    flow = exhaust_flow(SFOC, POWER, LAMBDA, fuel)
    assert flow.fuel.name == "bio"
    assert flow.afr_stoich == pytest.approx(fuel.afr_stoich)


def test_dataframe_has_the_intermediate_columns():
    flow = exhaust_flow(SFOC, POWER, LAMBDA, "HFO", load_pct=[11, 24, 50, 73])
    frame = flow.to_dataframe()
    assert list(frame.columns)[:2] == ["Carga_perc", "P_travao_kW"]
    assert {"m_fuel_kg_s", "m_ar_kg_s", "m_exh_kg_s", "n_exh_mol_s"} <= set(frame.columns)


# --------------------------------------------------------------------- #
#  Contra o dataset
# --------------------------------------------------------------------- #
@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_dataset_consumption_column_carries_a_ten_percent_margin():
    """A coluna ``Fuel_Consumption_[kgh]`` NAO e ``SFOC * P``: e 1.1 vezes isso.

    O factor e exactamente 1.1 nas 20 linhas do dataset -- uma margem de 10 %
    sobre o consumo nominal. O ``get_mass_dot_v3.m`` ignora essa coluna e
    recalcula ``m_fuel = SFOC*P/3.6e6``, e o porte faz o mesmo: usar a coluna
    daria caudais de escape 10 % altos, e com eles um reator sobredimensionado.
    """
    frame = pd.read_csv(CSV_INPUTS, sep=";", decimal=",", encoding="utf-8-sig")
    flow = exhaust_flow(frame["SFOC_[g/kWh]"], frame["Engine_Power_[kW]"],
                        frame["Lamda"], "HFO")
    tabelado = frame["Fuel_Consumption_[kgh]"].to_numpy(float)
    np.testing.assert_allclose(tabelado / flow.fuel_consumption_kg_h, 1.1,
                               rtol=1e-8)


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_dataset_loader_uses_the_same_calculation():
    """O caudal que o EngineCase traz tem de ser o de exhaust_flow."""
    case = EngineDataset.from_csv(CSV_INPUTS).build_case("DG1")
    flow = exhaust_flow(
        [m.sfoc_g_per_kWh for m in case.modes],
        [m.power_kW for m in case.modes],
        [m.lambda_ for m in case.modes], case.fuel)
    np.testing.assert_allclose(case.mass_flow_kgs, flow.exhaust_mass_flow_kgs,
                               rtol=1e-14)
