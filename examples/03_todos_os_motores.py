"""
Exemplo 3 -- varrimento de TODOS os motores do ficheiro + tabela-resumo.

Equivalente a ``run_all_volume_sweeps_alpha()`` no MATLAB, mas sem numero de
motores fixo: corre os que existirem no ficheiro.

Usa o cenario declarativo (:class:`tvscr.RunScenario`), que e o contrato de
inputs que uma interface tera de preencher -- e que se serializa para JSON.

    python examples/03_todos_os_motores.py [caminho/para/inputs.csv]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (AlphaLoopOptions, EmissionTargets, KineticParameters,
                   RunScenario, SubstrateGeometry, VolumeSweepOptions)

CSV_POR_OMISSAO = Path(
    r"D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\Tronconi1998"
    r"\Data Set\Tabela_Inputs_Final.csv")


def main() -> None:
    csv = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_POR_OMISSAO
    if not csv.is_file():
        raise SystemExit(f"Ficheiro de inputs nao encontrado: {csv}")

    outdir = Path(__file__).with_name("Resultados")

    scn = RunScenario(
        dataset_path=csv,
        engines=None,               # None = todos os motores do ficheiro
        fuel="HFO",
        substrate=SubstrateGeometry(cpsi=46, wall_thickness_m=0.43e-3),
        kinetics=KineticParameters(),
        targets=EmissionTargets(cycle_NO_frac=0.60, mode_NO_frac=0.80,
                                cycle_slip_ppm=10.0, mode_slip_ppm=20.0),
        sweep=VolumeSweepOptions(volume_max_m3=4.90, volume_step_m3=0.20,
                                 refine=True, refine_tol_m3=0.02,
                                 fouling=0.15, aging_KK0=0.80, verbose=True),
        alpha_loop=AlphaLoopOptions(alpha0=0.80, dalpha=0.02),
        tier="III",
        tier_power_law_only=True,   # reproduz o 9*n^-0.2 dos scripts MATLAB
        output_dir=outdir,
    )

    # O cenario e serializavel: e isto que uma interface guardaria/carregaria.
    cfg = outdir / "cenario.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(scn.to_dict(), indent=2, default=str),
                   encoding="utf-8")
    print(f"Cenario gravado em: {cfg}\n")

    batch = scn.run()

    try:
        from tvscr.plotting import plot_critical_volumes, plot_volume_sweep
        plot_critical_volumes(batch, outdir / "resumo_volumes_criticos.png")
        for name, s in batch.sweeps.items():
            plot_volume_sweep(s, outdir / name / f"volume_sweep_{name}.png")
        print(f"\nFiguras em: {outdir}")
    except ImportError:
        print("\n(matplotlib nao disponivel: figuras ignoradas)")

    print(f"\nResultados em: {outdir}")


if __name__ == "__main__":
    main()
