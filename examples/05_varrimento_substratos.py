"""
Exemplo 5 -- comparar pares CPSI / espessura de parede.

O CPSI e a parede não vêm do ficheiro de inputs: são escolha de projeto, e
mexem no reator em dois sentidos opostos. Canais mais estreitos dão mais área
geométrica por unidade de volume e melhor transferência de massa, mas também
menos área aberta (logo maior velocidade e menor tempo de residência) e menos
massa catalítica por canal quando a parede afina.

Este exemplo corre o varrimento em volume uma vez por par e põe os volumes
críticos lado a lado.

    python examples/05_varrimento_substratos.py [DG1] [caminho/para/inputs.csv]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (AlphaLoopOptions, EmissionTargets, EngineDataset,
                   KineticParameters, SubstrateGeometry, VolumeSweepOptions,
                   substrate_sweep)

CSV_POR_OMISSAO = Path(
    r"D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\Tronconi1998"
    r"\Data Set\Tabela_Inputs_Final.csv")

# --------------------------------------------------------------------- #
#  Pares a comparar: (CPSI, espessura de parede [m])
# --------------------------------------------------------------------- #
SUBSTRATOS = [
    (46, 0.43e-3),      # o do caso de referência
    (46, 0.30e-3),      # mesmo passo, parede mais fina
    (64, 0.35e-3),
    (100, 0.25e-3),
    (200, 0.18e-3),
]

ALVOS = EmissionTargets(cycle_NO_frac=0.60, mode_NO_frac=0.80,
                        cycle_slip_ppm=10.0, mode_slip_ppm=20.0)

VARRIMENTO = VolumeSweepOptions(
    volume_max_m3=3.50, volume_step_m3=0.20,
    refine=True, refine_tol_m3=0.02,
    fouling=0.15, aging_KK0=0.80)

LOOP_ALPHA = AlphaLoopOptions(alpha0=0.80, dalpha=0.02)


def main() -> None:
    engine = sys.argv[1] if len(sys.argv) > 1 else "DG1"
    csv = Path(sys.argv[2]) if len(sys.argv) > 2 else CSV_POR_OMISSAO
    if not csv.is_file():
        raise SystemExit(f"Ficheiro de inputs não encontrado: {csv}")

    case = EngineDataset.from_csv(csv).build_case(
        engine, kinetics=KineticParameters(), tier_power_law_only=True)

    print(f"{case.name}: L = {case.geometry.length_m:.2f} m (fixo) · "
          f"limite = {case.nox_limit_gkWh:.4f} g/kWh")
    print(f"Vão correr {len(SUBSTRATOS)} varrimentos em volume — "
          f"conte com uns segundos por par.")

    result = substrate_sweep(case, SUBSTRATOS, ALVOS, VARRIMENTO, LOOP_ALPHA)

    outdir = Path(__file__).with_name("Resultados")
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"substratos_{engine}.csv"
    result.summary.to_csv(path, index=False)
    print(f"\nTabela completa em: {path}")

    best = result.best_for(engine)
    if best is not None:
        s = best.substrate
        base = result.rows[0]
        ganho = base.result.critical_volume_m3 / best.result.critical_volume_m3
        print(f"\nMelhor par: CPSI {s.cpsi:g} / parede {s.wall_thickness_m * 1e3:.2f} mm")
        print(f"  V crítico = {best.result.critical_volume_m3:.3f} m³ "
              f"(A = {best.result.critical_area_m2:.3f} m²)")
        print(f"  Contra o par de referência: volume crítico {ganho:.2f}x menor.")


if __name__ == "__main__":
    main()
