"""
Testes que nao dependem dos ficheiros MATLAB: invariantes fisicas, helpers de
compatibilidade e um ponto de regressao do solver.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (AlphaLoopOptions, EmissionTargets, EngineCase, KineticTuning,
                   KineticParameters, ReactorGeometry, SubstrateGeometry,
                   alpha_event_loop, alpha_from_urea_flow, nox_limit_gkwh,
                   run_cycle, solve_point, stoich_afr, urea_flow_Lh)
from tvscr.numerics import (interp1_linear, matlab_colon, matlab_mode, solve2x2)
from tvscr.operating import nox_ppm_from_specific, specific_nox_gkwh


# --------------------------------------------------------------------- #
#  Helpers de compatibilidade MATLAB
# --------------------------------------------------------------------- #
def test_matlab_mode_picks_smallest_on_tie():
    assert matlab_mode([3, 3, 1, 1, 2]) == 1.0
    assert matlab_mode([513, 513, 513, 900]) == 513.0


def test_matlab_colon_descending():
    v = matlab_colon(3.24, -0.2, 0.2)
    assert v.size == 16
    assert v[0] == pytest.approx(3.24)
    assert v[-1] == pytest.approx(0.24)
    assert np.all(np.diff(v) < 0)


def test_interp1_extrapolates_linearly():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.0, 2.0, 4.0])
    got = interp1_linear(x, y, np.array([-1.0, 0.5, 3.0]))
    np.testing.assert_allclose(got, [-2.0, 1.0, 6.0])


def test_solve2x2_matches_numpy():
    J = np.array([[2.0, 1.0], [1e-3, 4.0]])
    F = np.array([5.0, 7.0])
    got = solve2x2(J[0, 0], J[0, 1], J[1, 0], J[1, 1], F[0], F[1])
    np.testing.assert_allclose(got, np.linalg.solve(J, F), rtol=1e-14)


def test_solve2x2_singular_returns_inf():
    assert not np.isfinite(solve2x2(1.0, 2.0, 2.0, 4.0, 1.0, 1.0)[0])


# --------------------------------------------------------------------- #
#  Regulamentacao e conversoes
# --------------------------------------------------------------------- #
def test_tier3_limit_piecewise_and_power_law():
    # gama media: as duas formas coincidem
    assert nox_limit_gkwh(513, "III") == pytest.approx(9 * 513 ** -0.2)
    assert nox_limit_gkwh(513, "III", power_law_only=True) == pytest.approx(
        nox_limit_gkwh(513, "III"))
    # patamares
    assert nox_limit_gkwh(100, "III") == pytest.approx(3.4)
    assert nox_limit_gkwh(2500, "III") == pytest.approx(2.0)
    assert nox_limit_gkwh(513, "II") == pytest.approx(44 * 513 ** -0.23)


def test_specific_nox_roundtrip():
    ppm, mdot, P = 200.0, 3.5, 1400.0
    g = specific_nox_gkwh(ppm, mdot, P)
    assert nox_ppm_from_specific(g, mdot, P) == pytest.approx(ppm, rel=1e-12)


def test_stoich_afr_ordering():
    # mais hidrogenio -> mais ar por kg de combustivel
    assert stoich_afr("MGO") > stoich_afr("MDO") > stoich_afr("HFO")


def test_urea_flow_roundtrip():
    alpha = np.array([0.7, 0.85, 1.0])
    NO_in = np.array([500.0, 800.0, 1200.0])
    mdot = np.array([2.0, 4.0, 7.0])
    q = urea_flow_Lh(alpha, NO_in, mdot)
    np.testing.assert_allclose(alpha_from_urea_flow(q, NO_in, mdot), alpha, rtol=1e-12)


# --------------------------------------------------------------------- #
#  Geometria
# --------------------------------------------------------------------- #
def test_substrate_geometry():
    s = SubstrateGeometry(cpsi=46, wall_thickness_m=0.43e-3)
    assert s.pitch_m == pytest.approx(0.0254 / np.sqrt(46))
    assert s.hydraulic_diameter_m == pytest.approx(s.pitch_m - 0.43e-3)
    assert 0.0 < s.open_frontal_fraction < 1.0
    assert s.is_valid


def test_substrate_invalid_when_wall_too_thick():
    assert not SubstrateGeometry(cpsi=400, wall_thickness_m=5e-3).is_valid


def test_reactor_volume_and_fouling():
    g = ReactorGeometry(length_m=1.2, frontal_area_m2=1.8, fouling=0.15)
    assert g.volume_m3 == pytest.approx(2.16)
    assert g.effective_frontal_area_m2 == pytest.approx(1.53)
    assert g.with_volume(3.24).frontal_area_m2 == pytest.approx(2.7)


# --------------------------------------------------------------------- #
#  Solver
# --------------------------------------------------------------------- #
DEMO = dict(
    T_K=360 + 273.15, pressure_Pa=101325.0, mass_flow_kgs=0.80,
    frontal_area_m2=1.0, NO_in_ppm=560.0, alpha=1.0, length_m=0.15,
    substrate=SubstrateGeometry(cpsi=(0.0254 / 7.5e-3) ** 2,
                                wall_thickness_m=1.2e-3),
    kinetics=KineticParameters(),
)


def test_solver_reference_point_regression():
    """Ponto de demonstracao do MATLAB (Fig. 3, catalisador 1).

    Valores fixados a partir deste porte; servem de guarda de regressao.
    """
    p = solve_point(**DEMO)
    assert p.X_NO == pytest.approx(68.06533592538152, rel=1e-9)
    assert p.slip_ppm == pytest.approx(178.83411881786344, rel=1e-9)
    assert p.eps_void == pytest.approx(0.7056, rel=1e-12)
    assert p.dh_m == pytest.approx(0.0063, rel=1e-12)
    assert p.valid and p.valid_strict


def test_stoichiometric_ceiling_is_respected():
    for alpha in (0.4, 0.7, 1.0):
        p = solve_point(**{**DEMO, "alpha": alpha})
        assert p.X_NO <= 100.0 * min(1.0, alpha) + 1e-9


def test_longer_reactor_converts_more():
    short = solve_point(**{**DEMO, "length_m": 0.10})
    long = solve_point(**{**DEMO, "length_m": 0.30})
    assert long.X_NO > short.X_NO
    assert long.slip_ppm < short.slip_ppm


def test_more_alpha_gives_more_conversion_and_more_slip():
    low = solve_point(**{**DEMO, "alpha": 0.6})
    high = solve_point(**{**DEMO, "alpha": 0.9})
    assert high.X_NO > low.X_NO
    assert high.slip_ppm > low.slip_ppm


def test_invalid_geometry_raises():
    bad = SubstrateGeometry(cpsi=400, wall_thickness_m=5e-3)
    with pytest.raises(ValueError):
        solve_point(**{**DEMO, "substrate": bad})


# --------------------------------------------------------------------- #
#  Ciclo e loop de alpha, sem depender de ficheiros
# --------------------------------------------------------------------- #
def _synthetic_case(area: float = 1.8) -> EngineCase:
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


def test_cycle_weighting_and_modes_are_sorted():
    case = _synthetic_case()
    assert np.all(np.diff(case.load_pct) > 0)
    r = run_cycle(case, alpha=0.8)
    assert r.n_modes == 4
    assert r.NO_cycle == pytest.approx(case.cycle_average(r.NO_gkWh), rel=1e-12)
    assert r.geometry_ok and np.all(r.valid_mode)


def test_alpha_loop_closes_on_a_generous_reactor():
    case = _synthetic_case(area=3.0)
    tgt = EmissionTargets().resolve(case.nox_limit_gkWh)
    out = alpha_event_loop(case, case.geometry, tgt, AlphaLoopOptions())
    assert out.ok
    assert int(out.situation) == 1
    assert np.all(out.alpha > 0)


def test_alpha_loop_declares_a_tiny_reactor_infeasible():
    case = _synthetic_case(area=0.20)
    tgt = EmissionTargets().resolve(case.nox_limit_gkWh)
    out = alpha_event_loop(case, case.geometry, tgt, AlphaLoopOptions())
    assert not out.ok
    assert int(out.situation) == 4
    assert out.why


def test_minimize_alpha_never_increases_urea():
    case = _synthetic_case(area=3.0)
    tgt = EmissionTargets().resolve(case.nox_limit_gkWh)
    base = alpha_event_loop(case, case.geometry, tgt, AlphaLoopOptions())
    mini = alpha_event_loop(case, case.geometry, tgt,
                            AlphaLoopOptions(minimize_alpha=True))
    assert mini.ok
    assert np.all(mini.alpha <= base.alpha + 1e-12)


# --------------------------------------------------------------------- #
#  Cenario declarativo (contrato de inputs)
# --------------------------------------------------------------------- #
def test_scenario_dict_roundtrip_rebuilds_nested_dataclasses():
    from tvscr import RunScenario
    from tvscr.kinetics import GasConstants

    scn = RunScenario(
        substrate=SubstrateGeometry(cpsi=64, wall_thickness_m=0.3e-3),
        kinetics=KineticParameters(aging_KK0=0.85),
        targets=EmissionTargets(cycle_slip_ppm=5.0),
    )
    data = scn.to_dict()
    back = RunScenario.from_dict(data)

    assert isinstance(back.substrate, SubstrateGeometry)
    assert isinstance(back.kinetics.gas, GasConstants)
    assert isinstance(back.sweep.tuning, KineticTuning)
    assert back.substrate.cpsi == 64
    assert back.kinetics.aging_KK0 == pytest.approx(0.85)
    assert back.targets.cycle_slip_ppm == pytest.approx(5.0)
    assert back.to_dict() == data          # idempotente


def test_scenario_rejects_unknown_fields():
    from tvscr import RunScenario
    with pytest.raises(KeyError):
        RunScenario.from_dict({"targets": {"cycle_slip_ppmm": 5.0}})
