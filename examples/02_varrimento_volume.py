"""
Exemplo 2 -- varrimento em volume de UM motor, com alpha adaptativo.

Equivalente a ``run_volume_sweep_alpha(1)`` no MATLAB. Todos os inputs sao
explicitos: os que vem do ficheiro (condicoes de operacao, geometria
instalada) e os que sao escolha de projecto (substrato, cinetica, alvos,
cenario de fouling/envelhecimento).

    python examples/02_varrimento_volume.py [DG1] [caminho/para/inputs.csv]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import (AlphaLoopOptions, EmissionTargets, EngineDataset,
                   KineticParameters, KineticTuning, SubstrateGeometry,
                   VolumeSweepOptions, volume_sweep, write_sweep_outputs)

# --------------------------------------------------------------------- #
#  INPUTS
# --------------------------------------------------------------------- #
CSV_POR_OMISSAO = Path(
    r"D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\Tronconi1998"
    r"\Data Set\Tabela_Inputs_Final.csv")

# --- substrato: escolha de projecto, NAO vem do ficheiro ---
SUBSTRATO = SubstrateGeometry(cpsi=46, wall_thickness_m=0.43e-3)

# --- cinetica de referencia (Tabela 2, Tronconi 1998) ---
CINETICA = KineticParameters()

# --- alvos: dois niveis (ciclo mais apertado que os modos) ---
ALVOS = EmissionTargets(
    cycle_NO_frac=0.60,    # NOx do ciclo <= 60 % do limite Tier III
    mode_NO_frac=0.80,     # NOx de cada modo <= 80 % do limite
    cycle_slip_ppm=10.0,   # slip ponderado
    mode_slip_ppm=20.0,    # slip em cada modo
)

# --- cenario do varrimento (os defaults dos scripts MATLAB) ---
VARRIMENTO = VolumeSweepOptions(
    volume_max_m3=3.50,           # maior volume a considerar
    volume_step_m3=0.20,          # decremento
    volume_min_m3=0.20,           # piso
    refine=True,                  # bisseccao em V para afinar o V critico
    refine_tol_m3=0.02,
    fouling=0.15,                 # 15 % de derate da area frontal efetiva
    aging_KK0=0.80,               # envelhecimento: k0NO *= KK0^2
    tuning=KineticTuning(),       # tudo a 1 = cinetica de referencia
    verbose=True,
)

LOOP_ALPHA = AlphaLoopOptions(
    alpha0=0.80, dalpha=0.02, alpha_min=0.30, alpha_max=1.20,
    max_iter=200, bracket_tol=1e-4,
    minimize_alpha=False,   # True -> devolve o alpha MINIMO admissivel
)


def main() -> None:
    engine = sys.argv[1] if len(sys.argv) > 1 else "DG1"
    csv = Path(sys.argv[2]) if len(sys.argv) > 2 else CSV_POR_OMISSAO
    if not csv.is_file():
        raise SystemExit(f"Ficheiro de inputs nao encontrado: {csv}")

    ds = EngineDataset.from_csv(csv)
    print("Motores no ficheiro:", ds.engines())

    case = ds.build_case(
        engine,
        fuel="HFO",
        substrate=SUBSTRATO,
        kinetics=CINETICA,
        pressure_Pa=101_325.0,
        tier="III",
        tier_power_law_only=True,   # reproduz o 9*n^-0.2 dos scripts MATLAB
    )
    print(case.describe())

    result = volume_sweep(case, ALVOS, VARRIMENTO, LOOP_ALPHA)

    outdir = Path(__file__).with_name("Resultados")
    paths = write_sweep_outputs(result, outdir)
    print(f"\n CSV em: {outdir / engine}")

    try:
        from tvscr.plotting import plot_volume_sweep
        png = outdir / engine / f"volume_sweep_{engine}.png"
        plot_volume_sweep(result, png)
        print(f" Figura: {png}")
    except ImportError:
        print(" (matplotlib nao disponivel: figura ignorada)")

    crit = result.at_critical()
    print(f"\n VOLUME CRITICO = {result.critical_volume_m3:.3f} m3 "
          f"(A = {result.critical_area_m2:.3f} m2, L = {result.length_m:.2f} m)")
    print(f" Nesse volume: NOx = {crit['NOx_ciclo_gkWh']:.4f} g/kWh, "
          f"slip = {crit['slip_ciclo_ppm']:.3f} ppm, "
          f"X_NO = {crit['XNO_ciclo_perc']:.2f} %, "
          f"ureia = {crit['urea_ciclo_Lh']:.2f} L/h")


if __name__ == "__main__":
    main()
