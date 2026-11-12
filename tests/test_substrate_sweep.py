"""
Varrimento de substratos: comparacao de pares CPSI / espessura de parede.

Nao ha referencia MATLAB para comparar (os scripts originais tinham CPSI e
parede fixos), por isso testa-se o comportamento: cada par produz o mesmo
resultado que um varrimento normal com esse substrato, pares impossiveis sao
registados em vez de rebentarem, e a tendencia fisica esperada verifica-se.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (AlphaLoopOptions, EmissionTargets, EngineCase,
                   ReactorGeometry, RunScenario, SubstrateGeometry,
                   VolumeSweepOptions, as_substrate, substrate_sweep,
                   volume_sweep)

TARGETS = EmissionTargets()
SWEEP = VolumeSweepOptions(volume_max_m3=2.6, volume_step_m3=0.3,
                           refine=False, verbose=False)
ALPHA = AlphaLoopOptions()


def _case(area: float = 1.8) -> EngineCase:
    return EngineCase.from_arrays(
        "TESTE",
        ReactorGeometry(length_m=1.2, frontal_area_m2=area,
                        substrate=SubstrateGeometry(46, 0.43e-3)),
        load_pct=[11.0, 24.0, 50.0, 73.0],
        weight=[10.5, 31.6, 31.6, 26.3],
        power_kW=[637.0, 1403.0, 2895.0, 4213.0],
        T_in_K=[614.7, 662.6, 683.5, 694.7],
        NO_in_ppm=[530.0, 816.0, 1160.0, 1228.0],
        sfoc_g_per_kWh=[229.5, 222.4, 208.0, 197.0],
        lambda_=[3.42, 2.68, 2.37, 2.18],
        engine_speed_rpm=513.0,
    )


# --------------------------------------------------------------------- #
def test_as_substrate_accepts_the_three_forms():
    target = SubstrateGeometry(cpsi=64, wall_thickness_m=0.35e-3)
    assert as_substrate(target) is target
    assert as_substrate({"cpsi": 64, "wall_thickness_m": 0.35e-3}) == target
    assert as_substrate((64, 0.35e-3)) == target


def test_each_pair_matches_a_plain_volume_sweep():
    """O varrimento de substratos não pode ser outra coisa senão N varrimentos."""
    case = _case()
    substrate = SubstrateGeometry(cpsi=64, wall_thickness_m=0.35e-3)

    swept = substrate_sweep(case, [substrate], TARGETS, SWEEP, ALPHA,
                            verbose=False)
    direct = volume_sweep(case.with_substrate(substrate), TARGETS, SWEEP, ALPHA)

    assert len(swept.rows) == 1
    got = swept.rows[0].result
    assert got.critical_volume_m3 == pytest.approx(direct.critical_volume_m3)
    np.testing.assert_allclose(got.NO_cycle, direct.NO_cycle, rtol=1e-12)
    np.testing.assert_allclose(got.slip_cycle, direct.slip_cycle, rtol=1e-12)


def test_the_case_substrate_is_not_mutated():
    case = _case()
    before = case.geometry.substrate
    substrate_sweep(case, [(64, 0.35e-3), (100, 0.25e-3)], TARGETS, SWEEP,
                    ALPHA, verbose=False)
    assert case.geometry.substrate == before


def test_impossible_pair_is_reported_not_raised():
    """Parede maior que o passo: fica registada com o motivo, sem parar tudo."""
    result = substrate_sweep(_case(), [(46, 0.43e-3), (400, 5e-3)],
                             TARGETS, SWEEP, ALPHA, verbose=False)
    assert len(result.rows) == 2
    good, bad = result.rows
    assert good.ok
    assert not bad.ok
    assert "dh" in bad.reason
    assert bad.result is None
    # a tabela-resumo mantém a linha, com NaN nos resultados
    assert len(result.summary) == 2
    assert np.isnan(result.summary["V_crit_m3"].iloc[1])


def test_finer_substrate_needs_less_volume():
    """Mais CPSI e parede mais fina -> mais área geométrica -> V crítico menor."""
    result = substrate_sweep(_case(), [(46, 0.43e-3), (100, 0.25e-3)],
                             TARGETS, SWEEP, ALPHA, verbose=False)
    coarse, fine = result.rows
    assert coarse.ok and fine.ok
    assert fine.result.critical_volume_m3 < coarse.result.critical_volume_m3
    assert result.best_for("TESTE") is fine


def test_summary_has_one_row_per_engine_and_substrate():
    cases = [_case(1.8), _case(2.7)]
    cases[1].name = "TESTE2"
    result = substrate_sweep(cases, [(46, 0.43e-3), (64, 0.35e-3)],
                             TARGETS, SWEEP, ALPHA, verbose=False)
    assert len(result.rows) == 4
    assert result.engines == ["TESTE", "TESTE2"]
    assert set(result.summary.columns) >= {
        "Engine", "CPSI", "parede_mm", "dh_mm", "eps_void",
        "V_crit_m3", "A_crit_m2", "NOx_ciclo_gkWh"}
    assert "sobredimensionamento" not in result.summary.columns


def test_empty_inputs_are_rejected():
    with pytest.raises(ValueError):
        substrate_sweep([], [(46, 0.43e-3)], TARGETS, SWEEP, ALPHA, verbose=False)
    with pytest.raises(ValueError):
        substrate_sweep(_case(), [], TARGETS, SWEEP, ALPHA, verbose=False)


# --------------------------------------------------------------------- #
#  Pelo cenario declarativo
# --------------------------------------------------------------------- #
def _inline_scenario(**kwargs) -> RunScenario:
    spec = {
        "name": "TESTE", "engine_speed_rpm": 513.0,
        "length_m": 1.2, "frontal_area_m2": 1.8,
        "modes": [
            {"load_pct": 11.0, "weight": 10.5, "power_kW": 637.0,
             "T_in_K": 614.7, "NO_in_ppm": 530.0, "sfoc_g_per_kWh": 229.5,
             "lambda_": 3.42},
            {"load_pct": 50.0, "weight": 31.6, "power_kW": 2895.0,
             "T_in_K": 683.5, "NO_in_ppm": 1160.0, "sfoc_g_per_kWh": 208.0,
             "lambda_": 2.37},
            {"load_pct": 73.0, "weight": 26.3, "power_kW": 4213.0,
             "T_in_K": 694.7, "NO_in_ppm": 1228.0, "sfoc_g_per_kWh": 197.0,
             "lambda_": 2.18},
        ],
    }
    return RunScenario(inline_engines=[spec], targets=TARGETS, sweep=SWEEP,
                       alpha_loop=ALPHA, **kwargs)


def test_scenario_runs_a_substrate_sweep():
    scn = _inline_scenario(substrates=[{"cpsi": 46, "wall_thickness_m": 0.43e-3},
                                       {"cpsi": 64, "wall_thickness_m": 0.35e-3}])
    result = scn.run_substrate_sweep()
    assert len(result.rows) == 2
    assert all(r.engine == "TESTE" for r in result.rows)


def test_scenario_without_substrates_falls_back_to_the_single_one():
    scn = _inline_scenario(substrate=SubstrateGeometry(64, 0.35e-3))
    result = scn.run_substrate_sweep()
    assert len(result.rows) == 1
    assert result.rows[0].substrate.cpsi == pytest.approx(64)


def test_substrates_survive_a_scenario_roundtrip():
    import json
    scn = _inline_scenario(substrates=[{"cpsi": 46, "wall_thickness_m": 0.43e-3},
                                       {"cpsi": 100, "wall_thickness_m": 0.25e-3}])
    back = RunScenario.from_dict(json.loads(json.dumps(scn.to_dict(), default=str)))
    assert len(back.substrates) == 2
    assert back.substrates[1]["cpsi"] == pytest.approx(100)
