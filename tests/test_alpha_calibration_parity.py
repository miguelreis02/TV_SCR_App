"""
Paridade da calibracao de alpha com o MATLAB.

Compara :func:`tvscr.calibrate_alpha` contra os ficheiros
``Alphas/alpha_DG<k>.csv`` produzidos por ``get_NOx_DG<k>.m``.

Cenario da referencia: catalisador LIMPO (``Fouling = 0``) e cinetica de
referencia (``KK0 = 1``) -- o alpha foi calibrado contra a conversao medida no
reator real com a area GEOMETRICA total, pelo que aplicar aqui um derate
contaria o mesmo efeito duas vezes. O palpite inicial e a curva de doseamento
do fabricante (:class:`tvscr.DosingCurve`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (CalibrationOptions, DosingCurve, EngineDataset,
                   SubstrateGeometry, calibrate_alpha)

MATLAB_ROOT = Path(r"D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\Tronconi1998")
CSV_INPUTS = MATLAB_ROOT / "Data Set" / "Tabela_Inputs_Final.csv"
ALPHAS = MATLAB_ROOT / "DGX_Simulations" / "Alphas"

ENGINES = ["DG1", "DG2", "DG3", "DG4", "DG5"]
SUBSTRATE = SubstrateGeometry(cpsi=46, wall_thickness_m=0.43e-3)


requires_reference = pytest.mark.skipif(
    not CSV_INPUTS.is_file() or not ALPHAS.is_dir(),
    reason="dataset/alphas MATLAB de referencia nao disponiveis")


@requires_reference
@pytest.mark.parametrize("engine", ENGINES)
def test_calibrated_alpha_matches_matlab(engine: str):
    ds = EngineDataset.from_csv(CSV_INPUTS)
    case = ds.build_case(engine, substrate=SUBSTRATE, fouling=0.0,
                         tier_power_law_only=True)
    got = calibrate_alpha(
        case, options=CalibrationOptions(dosing_curve=DosingCurve())
    ).to_dataframe()
    ref = pd.read_csv(ALPHAS / f"alpha_{engine}.csv")

    for col in ("alpha", "X_exp_perc", "X_sim_perc", "err_rel_perc"):
        np.testing.assert_allclose(
            got[col].to_numpy(float), ref[col].to_numpy(float),
            rtol=1e-10, atol=1e-12, err_msg=f"{engine}/{col}")
    np.testing.assert_allclose(
        got["slip_ppm"].to_numpy(float), ref["slip_ppm"].to_numpy(float),
        rtol=1e-8, atol=1e-12, err_msg=f"{engine}/slip_ppm")
