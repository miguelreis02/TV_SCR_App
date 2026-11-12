"""
Geometria do monolito: substrato (CPSI + parede) e reator (L, area frontal).

Todos os campos sao inputs explicitos -- nada e fixado no codigo. Os valores
por omissao reproduzem o caso de referencia dos scripts MATLAB
(``CPSI = 46``, parede ``0.43 mm``), mas devem ser passados pela aplicacao.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

__all__ = ["SubstrateGeometry", "ReactorGeometry"]

INCH_M = 0.0254   # 1 polegada [m] -- CPSI = celulas por polegada quadrada


@dataclass(frozen=True)
class SubstrateGeometry:
    """Celula do monolito de canais quadrados.

    Parameters
    ----------
    cpsi:
        Densidade celular [celulas/in^2]. ``pitch = 1 in / sqrt(CPSI)``.
    wall_thickness_m:
        Espessura TOTAL da parede [m]. A semi-espessura ``s = w/2`` e a
        dimensao caracteristica da difusao intraporo no modelo de Tronconi.
    """

    cpsi: float = 46.0
    wall_thickness_m: float = 0.43e-3

    @property
    def pitch_m(self) -> float:
        """Passo de celula [m] = 1 in / sqrt(CPSI)."""
        return INCH_M / self.cpsi ** 0.5

    @property
    def half_wall_m(self) -> float:
        """Semi-espessura da parede ``s`` [m]."""
        return self.wall_thickness_m / 2.0

    @property
    def hydraulic_diameter_m(self) -> float:
        """Diametro hidraulico do canal quadrado ``dh = pitch - w`` [m]."""
        return self.pitch_m - 2.0 * self.half_wall_m

    @property
    def open_frontal_fraction(self) -> float:
        """Fraccao de area frontal aberta ``eps = (dh/pitch)^2`` [-]."""
        return (self.hydraulic_diameter_m / self.pitch_m) ** 2

    @property
    def is_valid(self) -> bool:
        """``dh > 0``: CPSI e/ou parede admissiveis."""
        return self.hydraulic_diameter_m > 0.0

    def describe(self) -> str:
        return (f"CPSI={self.cpsi:.1f}  pitch={self.pitch_m * 1e3:.2f} mm  "
                f"parede={self.wall_thickness_m * 1e3:.2f} mm  "
                f"dh={self.hydraulic_diameter_m * 1e3:.2f} mm  "
                f"eps_void={self.open_frontal_fraction:.3f}")


@dataclass(frozen=True)
class ReactorGeometry:
    """Um monolito concreto: comprimento, area frontal e derate por fouling.

    No varrimento em volume esta e a geometria AVALIADA a cada passo, nao um
    reator ja instalado: o resultado do dimensionamento e o volume critico.

    Parameters
    ----------
    length_m:
        Comprimento do monolito ``L`` [m].
    frontal_area_m2:
        Area frontal GEOMETRICA ``A`` [m^2].
    substrate:
        Geometria da celula.
    fouling:
        Derate da area frontal EFETIVA [-]. ``A_ef = A * (1 - fouling)``.
        ``0`` = catalisador limpo; ``0.15`` = 15 % de canais obstruidos.
    """

    length_m: float
    frontal_area_m2: float
    substrate: SubstrateGeometry = field(default_factory=SubstrateGeometry)
    fouling: float = 0.0

    @property
    def volume_m3(self) -> float:
        return self.length_m * self.frontal_area_m2

    @property
    def effective_frontal_area_m2(self) -> float:
        """Area frontal vista pelo escoamento, ja com o derate de fouling."""
        return self.frontal_area_m2 * (1.0 - self.fouling)

    @property
    def is_valid(self) -> bool:
        return self.substrate.is_valid and self.length_m > 0.0 and self.frontal_area_m2 > 0.0

    # ---------------- construtores / variantes -----------------------------
    @classmethod
    def from_volume(cls, volume_m3: float, length_m: float,
                    substrate: SubstrateGeometry | None = None,
                    fouling: float = 0.0) -> "ReactorGeometry":
        """Constroi a geometria a partir do VOLUME, com ``L`` fixo (``A = V/L``).

        E a convencao do varrimento em volume: os motores diferem so na area
        frontal para o mesmo comprimento instalado.
        """
        if length_m <= 0.0:
            raise ValueError("ReactorGeometry.from_volume: L tem de ser > 0.")
        return cls(length_m=length_m,
                   frontal_area_m2=volume_m3 / length_m,
                   substrate=substrate if substrate is not None else SubstrateGeometry(),
                   fouling=fouling)

    def with_volume(self, volume_m3: float) -> "ReactorGeometry":
        """Nova geometria com o mesmo ``L`` e o volume pedido."""
        return replace(self, frontal_area_m2=volume_m3 / self.length_m)

    def with_frontal_area(self, frontal_area_m2: float) -> "ReactorGeometry":
        return replace(self, frontal_area_m2=frontal_area_m2)

    def with_length(self, length_m: float) -> "ReactorGeometry":
        return replace(self, length_m=length_m)

    def with_fouling(self, fouling: float) -> "ReactorGeometry":
        return replace(self, fouling=fouling)

    def with_substrate(self, substrate: SubstrateGeometry) -> "ReactorGeometry":
        return replace(self, substrate=substrate)

    def describe(self) -> str:
        return (f"L={self.length_m:.3f} m  A={self.frontal_area_m2:.3f} m2  "
                f"V={self.volume_m3:.3f} m3  fouling={self.fouling:.0%}  "
                f"| {self.substrate.describe()}")
