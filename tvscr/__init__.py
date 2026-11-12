"""
tvscr -- dimensionamento de sistemas SCR-deNOx.

Porte para Python dos scripts MATLAB (nao binned) de
``Tronconi1998/DGX_Simulations/Geometric_Sweep_Alpha_Loop``, com todos os
inputs -- geometria, condicoes de operacao, cinetica, alvos -- expostos como
parametros.

Camadas
-------
=========================  ==================================================
modulo                     equivalente MATLAB
=========================  ==================================================
:mod:`tvscr.solver`        ``tronconi_sizing_forward_v2.m``
:mod:`tvscr.cycle`         ``run_D2_geom.m``
:mod:`tvscr.alpha_loop`    ``alpha_event_loop.m``
:mod:`tvscr.sweep`         ``run_volume_sweep_alpha.m``
:mod:`tvscr.batch`         ``run_all_volume_sweeps_alpha.m``
:mod:`tvscr.dataset`       ``get_mass_dot_v3.m`` (leitura do CSV)
:mod:`tvscr.operating`     ``precompute_D2_inputs_DGX.m``
:mod:`tvscr.exhaust`       ``get_mass_dot_v3.m`` (calculo dos caudais)
:mod:`tvscr.urea`          ``urea_flow_Lh.m`` + ``nh3_ppm.m``
:mod:`tvscr.calibration`   ``Alphas/get_NOx_DG<k>.m``
=========================  ==================================================

Exemplo minimo
--------------
>>> from tvscr import EngineDataset, EmissionTargets, VolumeSweepOptions, volume_sweep
>>> ds = EngineDataset.from_csv("Tabela_Inputs_Final.csv")
>>> case = ds.build_case("DG1", substrate=SubstrateGeometry(cpsi=46, wall_thickness_m=0.43e-3))
>>> s = volume_sweep(case, EmissionTargets(),
...                  VolumeSweepOptions(volume_max_m3=3.5, fouling=0.15))
>>> s.critical_volume_m3, s.critical_area_m2
"""

from __future__ import annotations

__version__ = "0.1.0"

from .alpha_loop import (AlphaLoopOptions, AlphaLoopResult, Situation,
                         alpha_event_loop)
from .batch import BatchResult, run_all_volume_sweeps
from .calibration import (CalibrationOptions, CalibrationResult,
                          calibrate_alpha, load_alpha_csv, load_alpha_mat)
from .cycle import CycleResult, run_cycle
from .dataset import ColumnMap, DatasetFormat, EngineDataset, load_engine_case
from .exhaust import ExhaustFlow, exhaust_flow
from .fuels import FUEL_LIBRARY, FuelComposition, get_fuel, stoich_afr
from .geometry import ReactorGeometry, SubstrateGeometry
from .kinetics import GasConstants, KineticParameters, KineticTuning
from .operating import (EngineCase, OperatingMode, exhaust_mass_flow,
                        nox_limit_gkwh, nox_ppm_from_specific,
                        specific_nox_gkwh)
from .reporting import write_all, write_batch_summary, write_sweep_outputs
from .scenario import RunScenario
from .solver import PointResult, SolverOptions, solve_point
from .substrate_sweep import (SubstrateSweepResult, SubstrateSweepRow,
                              as_substrate, substrate_sweep)
from .sweep import (GeometryEvaluation, VolumeSweepOptions, VolumeSweepResult,
                    evaluate_geometry, volume_sweep)
from .targets import EmissionTargets, ResolvedTargets
from .urea import DosingCurve, UreaSolution, alpha_from_urea_flow, urea_flow_Lh

__all__ = [
    "__version__",
    # geometria / cinetica
    "SubstrateGeometry", "ReactorGeometry",
    "KineticParameters", "KineticTuning", "GasConstants",
    # dados de motor
    "EngineDataset", "ColumnMap", "DatasetFormat", "load_engine_case",
    "EngineCase", "OperatingMode",
    "FuelComposition", "FUEL_LIBRARY", "get_fuel", "stoich_afr",
    "nox_limit_gkwh", "specific_nox_gkwh", "nox_ppm_from_specific",
    "exhaust_mass_flow", "exhaust_flow", "ExhaustFlow",
    # solver
    "SolverOptions", "PointResult", "solve_point",
    "CycleResult", "run_cycle",
    # doseamento
    "UreaSolution", "DosingCurve", "urea_flow_Lh", "alpha_from_urea_flow",
    # alvos e loop de alpha
    "EmissionTargets", "ResolvedTargets",
    "AlphaLoopOptions", "AlphaLoopResult", "Situation", "alpha_event_loop",
    # varrimento
    "VolumeSweepOptions", "VolumeSweepResult", "GeometryEvaluation",
    "volume_sweep", "evaluate_geometry",
    "BatchResult", "run_all_volume_sweeps",
    "SubstrateSweepResult", "SubstrateSweepRow", "substrate_sweep",
    "as_substrate",
    # calibracao e escrita
    "CalibrationOptions", "CalibrationResult", "calibrate_alpha",
    "load_alpha_csv", "load_alpha_mat",
    "write_sweep_outputs", "write_batch_summary", "write_all",
    # cenario declarativo (contrato de inputs da aplicacao)
    "RunScenario",
]
