"""
Exemplo 1 -- UM ponto de operacao numa geometria.

Mostra o nivel mais baixo da API: o solver 1-D estacionario, com TODOS os
inputs explicitos. Nenhum valor vem de ficheiro.

    python examples/01_ponto_unico.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvscr import KineticParameters, SolverOptions, SubstrateGeometry, solve_point

# --------------------------------------------------------------------- #
#  INPUTS -- e isto que uma interface teria de pedir
# --------------------------------------------------------------------- #
OPERACAO = dict(
    T_K=360 + 273.15,        # temperatura a entrada do SCR       [K]
    pressure_Pa=101_325.0,   # pressao                            [Pa]
    mass_flow_kgs=0.80,      # caudal massico de escape           [kg/s]
    NO_in_ppm=560.0,         # NO a entrada                       [ppm]
    alpha=1.0,               # razao molar NH3/NO                 [-]
)

GEOMETRIA = dict(
    length_m=0.15,           # comprimento do monolito            [m]
    frontal_area_m2=1.0,     # area frontal EFETIVA               [m2]
)

SUBSTRATO = SubstrateGeometry(
    cpsi=(0.0254 / 7.5e-3) ** 2,   # pitch de 7.5 mm -> CPSI 11.47
    wall_thickness_m=1.2e-3,       # parede de 1.2 mm
)

CINETICA = KineticParameters(     # Tabela 2, catalisador 1 (Tronconi 1998)
    k0ads=8.5e6, Eads=9.0e3,
    k0NO=2.5e10, ENO=18.6e3,
    aging_KK0=1.0,                # 1.0 = catalisador novo
    k0d=8.0e8, E0d=2.6e4, beta=0.32,
    f=0.01, Deff=1e-6, Dmol=8e-5, M_bar_kg_mol=0.02896,
)

NUMERICA = SolverOptions(n_nodes=120)


def main() -> None:
    p = solve_point(substrate=SUBSTRATO, kinetics=CINETICA, options=NUMERICA,
                    **OPERACAO, **GEOMETRIA)

    print("=" * 68)
    print(" DIMENSIONAMENTO SCR (estacionario) -- ponto unico")
    print("=" * 68)
    print(f" Geometria : {SUBSTRATO.describe()}")
    print(f"             L = {GEOMETRIA['length_m'] * 1e3:.0f} mm  "
          f"A = {GEOMETRIA['frontal_area_m2']:.2f} m2")
    print(f" Escoamento: Q = {p.Q_m3s:.3f} m3/s  rho = {p.rho_kgm3:.4f} kg/m3")
    print(f"             v = {p.velocity_ms:.3f} m/s  AV = {p.AV_Nmh:.2f} Nm/h  "
          f"tau = {p.tau_s:.4f} s")
    print(f" Entrada   : T = {p.T_K:.0f} K  C_NO = {p.NO_in_ppm:.0f} ppm  "
          f"alpha = {p.alpha:.2f}")
    print(f" Cinetica  : kads = {p.kads:.3e}  kNO = {p.kNO:.3e}")
    print("-" * 68)
    print(f" X_NO     = {p.X_NO:6.2f} %   (teto estequiometrico "
          f"{p.X_NO_ceiling:.1f} %)")
    print(f" X_NH3    = {p.X_NH3:6.2f} %")
    print(f" NH3 slip = {p.slip_ppm:6.2f} ppm")
    print(f" regime   : eta_NO = {p.etaO_bar:.3f}  Bi_m = {p.Bim_bar:.3f}  "
          f"k_ov = {p.kov:.4f} m/s")
    print(f" numerico : resnorm_max = {p.max_resnorm:.2e}  "
          f"valid = {p.valid}  valid_strict = {p.valid_strict}")
    print("=" * 68)

    # Perfis axiais (opcional -- precisa de matplotlib)
    try:
        from tvscr.plotting import plot_axial_profiles
        out = Path(__file__).with_name("perfis_ponto_unico.png")
        plot_axial_profiles(p, out)
        print(f" Perfis axiais em: {out}")
    except ImportError:
        print(" (matplotlib nao disponivel: figura ignorada)")


if __name__ == "__main__":
    main()
