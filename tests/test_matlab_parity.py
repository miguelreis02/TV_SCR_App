"""
Paridade com o MATLAB.

Compara o porte Python contra os CSV de referencia gerados pelos scripts
MATLAB em ``Geometric_Sweep_Alpha_Loop/Results/``, motor a motor:

* ``volume_sweep_<DG>.csv``        -- uma linha por volume avaliado;
* ``volume_sweep_<DG>_modos.csv``  -- uma linha por (volume, modo);
* ``resumo_volumes_criticos.csv``  -- volumes criticos.

O cenario tem de ser o dos defaults do MATLAB a data em que a referencia foi
gerada: ``Fouling = 0.15``, ``KK0 = 0.80``, CPSI 46, parede 0.43 mm, alvos
60 %/10 ppm (ciclo) e 80 %/20 ppm (modo), alpha de arranque 0.80 com passo
de 2 %, e o limite Tier III pela lei de potencia pura (``9*n^-0.2``).

Correr com pytest, ou directamente::

    python tests/test_matlab_parity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (AlphaLoopOptions, EmissionTargets, EngineDataset,
                   KineticParameters, SubstrateGeometry, VolumeSweepOptions,
                   volume_sweep)

# --------------------------------------------------------------------- #
#  Referencia MATLAB
# --------------------------------------------------------------------- #
MATLAB_ROOT = Path(r"D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\Tronconi1998")
CSV_INPUTS = MATLAB_ROOT / "Data Set" / "Tabela_Inputs_Final.csv"
RESULTS = MATLAB_ROOT / "DGX_Simulations" / "Geometric_Sweep_Alpha_Loop" / "Results"

ENGINES = ["DG1", "DG2", "DG3", "DG4", "DG5"]

# Cenario dos defaults do MATLAB usados para gerar a referencia.
SCENARIO = dict(fouling=0.15, aging_KK0=0.80)
SUBSTRATE = SubstrateGeometry(cpsi=46, wall_thickness_m=0.43e-3)

RTOL = 1e-9        # tolerancia relativa nas grandezas continuas
ATOL = 1e-12


requires_reference = pytest.mark.skipif(
    not CSV_INPUTS.is_file() or not RESULTS.is_dir(),
    reason="dataset/resultados MATLAB de referencia nao disponiveis")


def _sweep(engine: str):
    """Varrimento com a malha de volumes que o MATLAB usava.

    O script original arrancava a 150 % do volume instalado; aqui esse volume
    de arranque e passado explicitamente, porque a aplicacao deixou de ter o
    conceito de "volume instalado" -- o resultado e o volume critico.
    """
    ds = EngineDataset.from_csv(CSV_INPUTS)
    case = ds.build_case(engine, substrate=SUBSTRATE,
                         kinetics=KineticParameters(),
                         tier_power_law_only=True)
    v_start = 1.5 * case.geometry.volume_m3
    return volume_sweep(
        case, EmissionTargets(),
        VolumeSweepOptions(volume_max_m3=v_start, verbose=False, **SCENARIO),
        AlphaLoopOptions())


def _compare(got: pd.DataFrame, ref: pd.DataFrame, columns, label: str):
    assert len(got) == len(ref), (
        f"{label}: {len(got)} linhas em Python vs {len(ref)} no MATLAB")
    worst = 0.0
    for col in columns:
        a = got[col].to_numpy(dtype=float)
        b = ref[col].to_numpy(dtype=float)
        finite = np.isfinite(a) & np.isfinite(b)
        assert np.array_equal(np.isfinite(a), np.isfinite(b)), \
            f"{label}/{col}: padrao de NaN diferente"
        if finite.any():
            denom = np.maximum(np.abs(b[finite]), 1e-30)
            rel = np.abs(a[finite] - b[finite]) / denom
            worst = max(worst, float(rel.max()))
            np.testing.assert_allclose(a[finite], b[finite], rtol=RTOL, atol=ATOL,
                                       err_msg=f"{label}/{col}")
    return worst


@requires_reference
@pytest.mark.parametrize("engine", ENGINES)
def test_volume_sweep_matches_matlab(engine: str):
    s = _sweep(engine)

    ref = pd.read_csv(RESULTS / engine / f"volume_sweep_{engine}.csv")
    got = s.to_dataframe()

    # colunas inteiras/logicas: igualdade exacta
    for col in ("situacao", "admissivel", "n_iter", "fase"):
        np.testing.assert_array_equal(
            got[col].to_numpy(int), ref[col].to_numpy(int),
            err_msg=f"{engine}/{col}")

    _compare(got, ref, ["V_m3", "A_m2", "NOx_ciclo_gkWh", "slip_ciclo_ppm",
                        "XNO_ciclo_perc", "urea_ciclo_Lh"],
             f"{engine}/sweep")


@requires_reference
@pytest.mark.parametrize("engine", ENGINES)
def test_mode_detail_matches_matlab(engine: str):
    s = _sweep(engine)

    ref = pd.read_csv(RESULTS / engine / f"volume_sweep_{engine}_modos.csv")
    got = s.modes_dataframe()

    np.testing.assert_array_equal(
        got["situacao_modo"].to_numpy(int), ref["situacao_modo"].to_numpy(int),
        err_msg=f"{engine}/situacao_modo")

    _compare(got, ref, ["V_m3", "Load_perc", "Weight_perc", "alpha", "XNO_perc",
                        "NO_gkWh", "slip_ppm", "urea_Lh", "tau_s", "AV_Nmh", "eta"],
             f"{engine}/modos")


@requires_reference
def test_critical_volumes_match_matlab():
    """So o volume critico: o resumo deixou de trazer instalado/sobredimensionamento."""
    got = pd.DataFrame([_sweep(e).summary_row() for e in ENGINES])
    ref = pd.read_csv(RESULTS / "resumo_volumes_criticos.csv")
    _compare(got, ref, ["V_crit_m3", "A_crit_m2"], "volumes criticos")


@requires_reference
def test_cycle_values_match_matlab_at_the_same_volume():
    """O ciclo tem de coincidir avaliado no MESMO volume que o MATLAB reportava.

    A referencia reportava o ciclo no volume instalado; aqui pede-se esse
    volume explicitamente a :meth:`VolumeSweepResult.at_volume`, para a
    comparacao continuar a ser possivel sem o conceito voltar ao produto.
    """
    ref = pd.read_csv(RESULTS / "resumo_volumes_criticos.csv")
    for i, engine in enumerate(ENGINES):
        got = _sweep(engine).at_volume(float(ref["V_instalado_m3"].iloc[i]))
        for column, key in (("NOx_ciclo_gkWh", "NOx_ciclo_gkWh"),
                            ("slip_ciclo_ppm", "slip_ciclo_ppm"),
                            ("urea_ciclo_Lh", "urea_ciclo_Lh")):
            np.testing.assert_allclose(
                got[key], float(ref[column].iloc[i]), rtol=RTOL, atol=ATOL,
                err_msg=f"{engine}/{column}")


# --------------------------------------------------------------------- #
#  Execucao directa: imprime o erro relativo maximo por motor
# --------------------------------------------------------------------- #
def main() -> int:
    if not CSV_INPUTS.is_file() or not RESULTS.is_dir():
        print("Referencia MATLAB nao encontrada; nada a comparar.")
        return 1

    print(f"{'motor':>6} {'linhas':>7} {'err_max_ciclo':>14} {'err_max_modos':>14} "
          f"{'V_crit_py':>10} {'V_crit_ml':>10}")
    ref_summary = pd.read_csv(RESULTS / "resumo_volumes_criticos.csv")
    worst_all = 0.0
    rows = []

    for i, engine in enumerate(ENGINES):
        s = _sweep(engine)
        ref = pd.read_csv(RESULTS / engine / f"volume_sweep_{engine}.csv")
        ref_m = pd.read_csv(RESULTS / engine / f"volume_sweep_{engine}_modos.csv")

        e1 = _compare(s.to_dataframe(), ref,
                      ["V_m3", "A_m2", "NOx_ciclo_gkWh", "slip_ciclo_ppm",
                       "XNO_ciclo_perc", "urea_ciclo_Lh"], f"{engine}/sweep")
        e2 = _compare(s.modes_dataframe(), ref_m,
                      ["alpha", "XNO_perc", "NO_gkWh", "slip_ppm", "urea_Lh",
                       "tau_s", "AV_Nmh", "eta"], f"{engine}/modos")
        worst_all = max(worst_all, e1, e2)
        rows.append(s.summary_row())
        print(f"{engine:>6} {len(ref):>7} {e1:>14.3e} {e2:>14.3e} "
              f"{s.critical_volume_m3:>10.4f} "
              f"{ref_summary['V_crit_m3'].iloc[i]:>10.4f}")

    print(f"\nerro relativo maximo global: {worst_all:.3e}")
    print("\n--- resumo Python (no volume critico) ---")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n--- resumo MATLAB (no volume instalado) ---")
    print(ref_summary.to_string(index=False))
    return 0 if worst_all < 1e-9 else 2


if __name__ == "__main__":
    raise SystemExit(main())
