"""
Exemplo 4 -- motor NOVO, sem ficheiro de inputs (escalabilidade).

Demonstra que nada no calculo depende do dataset original: aqui o ciclo tem
5 modos (nao 4), o motor nao se chama DG*, o substrato e outro, o combustivel
e MGO e o limite regulamentar sai da rotacao nominal pela regra MARPOL
completa (com os patamares de n < 130 e n >= 2000 rpm).

Tambem mostra a calibracao de alpha contra conversoes medidas, que passa a ser
opcional -- ao contrario do MATLAB, que exigia um ``alpha_DG<k>.mat`` so para
poder correr o varrimento.

    python examples/04_motor_novo_sem_ficheiro.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from tvscr import (AlphaLoopOptions, CalibrationOptions, EmissionTargets,
                   EngineCase, KineticParameters, ReactorGeometry,
                   SubstrateGeometry, VolumeSweepOptions, calibrate_alpha,
                   run_cycle, volume_sweep)

# --------------------------------------------------------------------- #
#  INPUTS -- ciclo de ensaio de 5 modos, medido em banco
# --------------------------------------------------------------------- #
SUBSTRATO = SubstrateGeometry(cpsi=64, wall_thickness_m=0.35e-3)

GEOMETRIA = ReactorGeometry(
    length_m=1.0,             # comprimento instalado          [m]
    frontal_area_m2=2.2,      # area frontal instalada         [m2]
    substrate=SUBSTRATO,
    fouling=0.10,             # 10 % de derate                 [-]
)

CASO = EngineCase.from_arrays(
    "MG-A",
    GEOMETRIA,
    load_pct=[10.0, 25.0, 50.0, 75.0, 100.0],
    weight=[10.0, 25.0, 30.0, 25.0, 10.0],
    power_kW=[520.0, 1300.0, 2600.0, 3900.0, 5200.0],
    T_in_K=[560.0, 610.0, 655.0, 685.0, 700.0],
    NO_in_ppm=[480.0, 760.0, 1080.0, 1210.0, 1260.0],
    NO_out_ppm=[95.0, 130.0, 165.0, 190.0, 205.0],   # medido (para calibrar)
    sfoc_g_per_kWh=[235.0, 220.0, 205.0, 198.0, 196.0],
    lambda_=[3.60, 2.80, 2.40, 2.20, 2.10],
    fuel="MGO",
    engine_speed_rpm=720.0,        # -> Tier III pela regra MARPOL completa
    kinetics=KineticParameters(aging_KK0=0.85),
    pressure_Pa=101_325.0,
)


def main() -> None:
    print(CASO.describe())
    print(f"\n Limite Tier III a {CASO.engine_speed_rpm:.0f} rpm = "
          f"{CASO.nox_limit_gkWh:.4f} g/kWh")

    # ---- 1. calibrar alpha contra a conversao medida ------------------ #
    print("\n--- Calibracao de alpha (erro minimo em X_NO) ---")
    cal = calibrate_alpha(CASO, options=CalibrationOptions(err_tol=0.005))
    print(cal.describe())
    CASO.alpha_calibrated = cal.alpha

    # ---- 2. curva de implementacao: ciclo com o alpha calibrado ------- #
    r = run_cycle(CASO)
    print(f"\n Com o alpha calibrado: {r.describe()}")

    # ---- 3. varrimento em volume com alpha adaptativo ----------------- #
    s = volume_sweep(
        CASO,
        EmissionTargets(cycle_NO_frac=0.60, mode_NO_frac=0.80,
                        cycle_slip_ppm=10.0, mode_slip_ppm=20.0),
        VolumeSweepOptions(volume_max_m3=3.00, volume_step_m3=0.20,
                           refine=True, refine_tol_m3=0.02, verbose=True),
        AlphaLoopOptions(alpha0=0.80, dalpha=0.02))

    if np.isfinite(s.critical_volume_m3):
        crit = s.at_critical()
        print(f"\n VOLUME CRITICO = {s.critical_volume_m3:.3f} m3 "
              f"(A = {s.critical_area_m2:.3f} m2, L = {s.length_m:.2f} m)")
        print(f" Nesse volume: NOx = {crit['NOx_ciclo_gkWh']:.4f} g/kWh, "
              f"slip = {crit['slip_ciclo_ppm']:.3f} ppm, "
              f"ureia = {crit['urea_ciclo_Lh']:.2f} L/h")
    else:
        print("\n Nenhum volume admissivel no intervalo varrido: nem o maior "
              "volume considerado cumpre os alvos neste cenario.")
        print(" Suba o volume maximo, ou alivie os alvos / o cenario de "
              "envelhecimento e fouling.")
        print(" Motivo do primeiro volume avaliado:", s.why[0])


if __name__ == "__main__":
    main()
