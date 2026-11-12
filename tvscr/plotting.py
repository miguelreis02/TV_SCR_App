"""
Figuras de diagnostico (porte de ``make_figures`` / figura-resumo do MATLAB).

Opcional: o pacote funciona sem matplotlib -- estas funcoes so o importam
quando sao chamadas. Nao ha interface aqui, apenas as mesmas figuras que os
scripts originais produziam.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np

from .batch import BatchResult
from .sweep import VolumeSweepResult

__all__ = ["plot_volume_sweep", "plot_critical_volumes", "plot_axial_profiles"]


def plot_volume_sweep(result: VolumeSweepResult,
                      path: Optional[Union[str, Path]] = None,
                      dpi: int = 150, show: bool = False):
    """Painel 2x2: NOx do ciclo, slip (log), alpha por modo e ureia vs volume."""
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = result.ok
    V = result.volume_m3
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.8))
    fig.patch.set_facecolor("w")

    # (1) NOx do ciclo -------------------------------------------------- #
    ax = axes[0, 0]
    ax.plot(V[ok], result.NO_cycle[ok], "o-", lw=1.6, label="admissivel")
    ax.plot(V[~ok], result.NO_cycle[~ok], "x", ms=11, lw=2,
            color=(0.85, 0, 0), label="inadmissivel")
    ax.axhline(result.targets.cycle_NO_gkWh, ls="--", color="r", lw=1.4)
    ax.axhline(result.nox_limit_gkWh, ls=":", color="k", lw=1.2)
    if np.isfinite(result.critical_volume_m3):
        ax.axvline(result.critical_volume_m3, ls="-.", lw=1.4, color="0.3")
        j = result.critical_index
        ax.plot(V[j], result.NO_cycle[j], "*", ms=14, mfc="y", mec="k")
    ax.set_xlabel("V [m$^3$]")
    ax.set_ylabel("NOx do ciclo [g/kWh]")
    ax.set_title(f"{result.engine} - NOx do ciclo vs volume")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best")

    # (2) slip do ciclo (log) ------------------------------------------- #
    ax = axes[0, 1]
    ax.plot(V[ok], np.maximum(result.slip_cycle[ok], 1e-3), "s-", lw=1.6)
    ax.plot(V[~ok], np.maximum(result.slip_cycle[~ok], 1e-3), "x", ms=11, lw=2,
            color=(0.85, 0, 0))
    ax.axhline(result.targets.cycle_slip_ppm, ls="--", color="r", lw=1.4)
    if np.isfinite(result.critical_volume_m3):
        ax.axvline(result.critical_volume_m3, ls="-.", lw=1.4, color="0.3")
    ax.set_yscale("log")
    ax.set_xlabel("V [m$^3$]")
    ax.set_ylabel("NH$_3$ slip do ciclo [ppm]")
    ax.set_title("slip do ciclo vs volume")
    ax.grid(True, which="both", alpha=0.3)

    # (3) alpha por modo ------------------------------------------------ #
    ax = axes[1, 0]
    for m, load in enumerate(result.load_pct):
        ax.plot(V, result.alpha[:, m], "o-", lw=1.4, label=f"carga {load:.0f} %")
    if np.isfinite(result.critical_volume_m3):
        ax.axvline(result.critical_volume_m3, ls="-.", lw=1.4, color="0.3")
    ax.set_xlabel("V [m$^3$]")
    ax.set_ylabel(r"$\alpha$ [-]")
    ax.set_title(r"$\alpha$ por modo (adaptativo)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best")

    # (4) ureia --------------------------------------------------------- #
    ax = axes[1, 1]
    ax.plot(V, result.urea_cycle, "d-", lw=1.6)
    if np.isfinite(result.critical_volume_m3):
        ax.axvline(result.critical_volume_m3, ls="-.", lw=1.4, color="0.3")
    ax.set_xlabel("V [m$^3$]")
    ax.set_ylabel("ureia 40 % [L/h] (ciclo)")
    ax.set_title("consumo de ureia vs volume")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=dpi)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig


def plot_critical_volumes(batch: BatchResult,
                          path: Optional[Union[str, Path]] = None,
                          dpi: int = 150, show: bool = False):
    """Barras: volume critico por motor, anotadas com a area frontal."""
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = batch.summary
    n = len(df)
    x = np.arange(n)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    fig.patch.set_facecolor("w")
    ax.bar(x, df["V_crit_m3"], width=0.55, color=(0.85, 0.45, 0.15))
    for i, row in enumerate(df.itertuples(index=False)):
        ax.text(i, row.V_crit_m3, f"  A = {row.A_crit_m2:.2f} m$^2$",
                ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(df["Engine"])
    ax.set_ylabel("Volume critico de catalisador [m$^3$]")
    ax.set_title("Volume critico por motor")
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=dpi)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig


def plot_axial_profiles(point, path: Optional[Union[str, Path]] = None,
                        dpi: int = 150, show: bool = False):
    """Perfis axiais de um :class:`~tvscr.solver.PointResult`."""
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(6.6, 5.6), sharex=True)
    fig.patch.set_facecolor("w")

    axes[0].plot(point.z, point.CNO_ppm_z, "k-", lw=1.6, label="NO")
    axes[0].plot(point.z, point.CNH3_ppm_z, "k--", lw=1.6, label="NH$_3$")
    axes[0].set_ylabel("Concentracao [ppm]")
    axes[0].set_title("Perfis axiais - estado estacionario")
    axes[0].legend(loc="best")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(point.z, point.theta_z, "k-", lw=1.6)
    axes[1].set_xlabel("Z (coordenada axial adimensional)")
    axes[1].set_ylabel(r"$\theta$ (cobertura de NH$_3$)")
    axes[1].set_xlim(0, 1)
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=dpi)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig
