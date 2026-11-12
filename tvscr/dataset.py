"""
Leitura do dataset de motores (porte de ``get_mass_dot_v3.m``).

O leitor e TOTALMENTE parametrizavel: nome das colunas, separador, simbolo
decimal, unidades e o proprio conjunto de motores sao inputs. Os valores por
omissao reproduzem ``Tabela_Inputs_Final.csv`` (5 motores DG1..DG5, 4 modos D2
por motor, separador ``;``, virgula decimal), mas nada no codigo assume esse
ficheiro, nem 5 motores, nem 4 modos.

Colunas logicas
---------------
=====================  ==========================================
chave                  significado
=====================  ==========================================
``engine``             etiqueta do motor (filtro)
``length``             comprimento do monolito instalado    [m]
``volume``             volume de catalisador instalado      [m3]
``area``               area frontal instalada               [m2]
``engine_speed``       rotacao nominal                      [rpm]
``rated_power``        potencia nominal                     [kW]
``load``               carga de ensaio (fraccao 0..1 ou %)
``weight``             peso do modo no ciclo                [%]
``power``              potencia de TRAVAO do ponto          [kW]
``lambda``             excesso de ar                        [-]
``sfoc``               consumo especifico                   [g/kWh]
``fuel_consumption``   consumo de combustivel (opcional)    [kg/h]
``T_in``               temperatura a entrada do SCR         [degC ou K]
``NO_in``              NO a entrada do SCR                  [ppm]
``NO_out``             NO a saida medido                    [ppm]
=====================  ==========================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

from .fuels import FuelComposition, get_fuel
from .geometry import ReactorGeometry, SubstrateGeometry
from .kinetics import KineticParameters
from .numerics import matlab_mode
from .operating import EngineCase, OperatingMode, exhaust_mass_flow, nox_limit_gkwh

__all__ = ["ColumnMap", "DatasetFormat", "EngineDataset", "load_engine_case"]


# ====================================================================== #
#  Mapeamento de colunas e formato do ficheiro
# ====================================================================== #
@dataclass
class ColumnMap:
    """Nome (ou indice 0-based) de cada coluna logica no ficheiro."""

    engine: Union[str, int] = "Engine"
    length: Union[str, int] = "Implemented_Lenght_[m]"
    volume: Union[str, int] = "Implemented_Volume_[m3]"
    area: Union[str, int] = "Implemented_Area_[m2]"
    engine_speed: Union[str, int] = "Engine_Speed_[rpm]"
    rated_power: Union[str, int] = "Rated_Power_[kW]"
    load: Union[str, int] = "LoadTest"
    weight: Union[str, int] = "Weight"
    power: Union[str, int] = "Engine_Power_[kW]"
    lambda_: Union[str, int] = "Lamda"
    sfoc: Union[str, int] = "SFOC_[g/kWh]"
    fuel_consumption: Optional[Union[str, int]] = "Fuel_Consumption_[kgh]"
    T_in: Union[str, int] = "T_in_[C]"
    NO_in: Union[str, int] = "NO_in_[ppm]"
    NO_out: Optional[Union[str, int]] = "NO_out_[ppm]"

    def resolve(self, frame: pd.DataFrame, key: Union[str, int]) -> pd.Series:
        """Devolve a coluna, aceitando nome exacto ou indice posicional."""
        if isinstance(key, int):
            return frame.iloc[:, key]
        if key in frame.columns:
            return frame[key]
        # tolerancia a espacos/maiusculas
        norm = {str(c).strip().lower(): c for c in frame.columns}
        hit = norm.get(str(key).strip().lower())
        if hit is None:
            raise KeyError(
                f'Coluna "{key}" nao existe no ficheiro. '
                f"Colunas disponiveis: {list(frame.columns)}")
        return frame[hit]


@dataclass
class DatasetFormat:
    """Dialecto do ficheiro e unidades das colunas."""

    separator: str = ";"
    decimal: str = ","
    encoding: str = "utf-8-sig"
    load_is_fraction: bool = True     # LoadTest vem em 0..1 -> converter para %
    weight_is_percent: bool = True    # Weight ja vem em %
    temperature_unit: str = "C"       # "C" ou "K"

    def to_kelvin(self, values: np.ndarray) -> np.ndarray:
        unit = self.temperature_unit.strip().upper()
        if unit in ("K", "KELVIN"):
            return values
        if unit in ("C", "DEGC", "CELSIUS"):
            return values + 273.15
        raise ValueError(f'temperature_unit desconhecida: "{self.temperature_unit}"')


# ====================================================================== #
#  Dataset
# ====================================================================== #
@dataclass
class EngineDataset:
    """Tabela de motores lida de ficheiro, pronta a produzir ``EngineCase``."""

    frame: pd.DataFrame
    columns: ColumnMap = field(default_factory=ColumnMap)
    fmt: DatasetFormat = field(default_factory=DatasetFormat)
    source: Optional[Path] = None

    # ---------------- leitura ------------------------------------------ #
    @classmethod
    def from_csv(cls, path: Union[str, Path],
                 columns: Optional[ColumnMap] = None,
                 fmt: Optional[DatasetFormat] = None) -> "EngineDataset":
        """Le o ficheiro de inputs."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Ficheiro nao encontrado: {path}")
        fmt = fmt or DatasetFormat()
        frame = pd.read_csv(path, sep=fmt.separator, decimal=fmt.decimal,
                            encoding=fmt.encoding)
        frame.columns = [str(c).strip() for c in frame.columns]
        return cls(frame=frame, columns=columns or ColumnMap(), fmt=fmt, source=path)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame,
                   columns: Optional[ColumnMap] = None,
                   fmt: Optional[DatasetFormat] = None) -> "EngineDataset":
        return cls(frame=frame.copy(), columns=columns or ColumnMap(),
                   fmt=fmt or DatasetFormat())

    # ---------------- consultas ---------------------------------------- #
    def engines(self) -> List[str]:
        """Etiquetas de motor presentes, pela ordem de aparecimento."""
        col = self.columns.resolve(self.frame, self.columns.engine)
        return list(pd.unique(col.astype(str).str.strip()))

    def rows_for(self, engine: str) -> pd.DataFrame:
        col = self.columns.resolve(self.frame, self.columns.engine)
        mask = col.astype(str).str.strip().str.casefold() == str(engine).strip().casefold()
        sub = self.frame.loc[mask]
        if sub.empty:
            raise ValueError(
                f'Nenhuma linha do motor "{engine}". '
                f"Motores no ficheiro: {self.engines()}")
        return sub

    # ---------------- construcao do caso -------------------------------- #
    def build_case(self, engine: str, *,
                   fuel: Union[str, FuelComposition] = "HFO",
                   kinetics: Optional[KineticParameters] = None,
                   substrate: Optional[SubstrateGeometry] = None,
                   fouling: float = 0.0,
                   pressure_Pa: float = 101325.0,
                   tier: str = "III",
                   tier_power_law_only: bool = False,
                   nox_limit_gkWh: Optional[float] = None,
                   alpha_calibrated: Optional[Sequence[float]] = None,
                   length_m: Optional[float] = None,
                   frontal_area_m2: Optional[float] = None,
                   volume_m3: Optional[float] = None,
                   strict_geometry: bool = False) -> EngineCase:
        """Constroi o :class:`~tvscr.operating.EngineCase` de um motor.

        Parameters
        ----------
        engine:
            Etiqueta do motor no ficheiro (p.ex. ``"DG1"``).
        fuel:
            Nome no catalogo ou :class:`~tvscr.fuels.FuelComposition`.
        substrate:
            Geometria da celula. NAO vem do ficheiro (o CSV so traz L, A e V)
            -- e um input da aplicacao. Por omissao CPSI 46 / parede 0.43 mm.
        fouling:
            Derate da area frontal efetiva [-].
        length_m, frontal_area_m2, volume_m3:
            Sobrepoem-se a geometria lida do ficheiro. Se der dois deles, o
            terceiro e derivado; se der so o volume, mantem-se o ``L`` do
            ficheiro.
        strict_geometry:
            Se ``True``, ``V != A*L`` no ficheiro passa de aviso a erro.
        """
        rows = self.rows_for(engine)
        cm, fmt = self.columns, self.fmt

        def col(key) -> np.ndarray:
            return cm.resolve(rows, key).to_numpy(dtype=float)

        load = col(cm.load) * (100.0 if fmt.load_is_fraction else 1.0)
        weight = col(cm.weight)
        power = col(cm.power)
        lam = col(cm.lambda_)
        sfoc = col(cm.sfoc)
        T_K = fmt.to_kelvin(col(cm.T_in))
        NO_in = col(cm.NO_in)
        NO_out = col(cm.NO_out) if cm.NO_out is not None else np.full(load.shape, np.nan)

        speed = matlab_mode(col(cm.engine_speed))
        rated = matlab_mode(col(cm.rated_power))

        # ---- geometria ------------------------------------------------ #
        # As colunas de geometria sao OPCIONAIS: um ficheiro so com condicoes
        # de operacao e valido, e a geometria vem entao dos argumentos.
        def optional(key):
            if key is None:
                return None
            try:
                return matlab_mode(col(key))
            except (KeyError, ValueError, TypeError):
                return None

        L_file = optional(cm.length)
        A_file = optional(cm.area)
        V_file = optional(cm.volume)
        if None not in (L_file, A_file, V_file) and abs(A_file * L_file - V_file) > 1e-6:
            msg = (f'{engine}: Area*L = {A_file * L_file:.4f} m3 nao bate com o '
                   f"volume tabelado ({V_file:.4f} m3). Confirmar as colunas do ficheiro.")
            if strict_geometry:
                raise ValueError(msg)
            import warnings
            warnings.warn(msg, RuntimeWarning, stacklevel=2)

        L = float(length_m) if length_m is not None else L_file
        if L is None:
            raise ValueError(
                f'{engine}: o ficheiro nao traz o comprimento do monolito. '
                f"Indique length_m.")
        if frontal_area_m2 is not None:
            A = float(frontal_area_m2)
        elif volume_m3 is not None:
            A = float(volume_m3) / L
        elif A_file is not None:
            A = A_file
        elif V_file is not None:
            A = V_file / L
        else:
            raise ValueError(
                f'{engine}: o ficheiro nao traz a area frontal nem o volume. '
                f"Indique frontal_area_m2 ou volume_m3.")
        geometry = ReactorGeometry(
            length_m=L, frontal_area_m2=A,
            substrate=substrate or SubstrateGeometry(), fouling=fouling)

        # ---- caudais --------------------------------------------------- #
        fuel_comp = get_fuel(fuel)
        fuel_flow = sfoc * power / 3.6e6
        mdot = exhaust_mass_flow(sfoc, power, lam, fuel_comp.afr_stoich)

        modes = [
            OperatingMode(
                load_pct=float(load[i]), weight=float(weight[i]),
                power_kW=float(power[i]), exhaust_mass_flow_kgs=float(mdot[i]),
                T_in_K=float(T_K[i]), NO_in_ppm=float(NO_in[i]),
                NO_out_ppm=None if np.isnan(NO_out[i]) else float(NO_out[i]),
                fuel_mass_flow_kgs=float(fuel_flow[i]), lambda_=float(lam[i]),
                sfoc_g_per_kWh=float(sfoc[i]),
            )
            for i in range(load.size)
        ]

        limit = (nox_limit_gkWh if nox_limit_gkWh is not None
                 else nox_limit_gkwh(speed, tier, tier_power_law_only))

        return EngineCase(
            name=str(engine),
            modes=modes,
            geometry=geometry,
            kinetics=kinetics or KineticParameters(),
            nox_limit_gkWh=limit,
            engine_speed_rpm=speed,
            rated_power_kW=rated,
            pressure_Pa=pressure_Pa,
            fuel=fuel_comp.name,
            alpha_calibrated=(None if alpha_calibrated is None
                              else np.asarray(alpha_calibrated, dtype=float)),
            tier=tier,
            tier_power_law_only=tier_power_law_only,
        )

    def build_all(self, engines: Optional[Sequence[str]] = None,
                  **kwargs) -> Dict[str, EngineCase]:
        """Constroi os casos de todos os motores (ou dos indicados)."""
        names = list(engines) if engines is not None else self.engines()
        return {name: self.build_case(name, **kwargs) for name in names}


def load_engine_case(csv_path: Union[str, Path], engine: str, **kwargs) -> EngineCase:
    """Atalho: le o ficheiro e devolve o caso de um motor."""
    columns = kwargs.pop("columns", None)
    fmt = kwargs.pop("fmt", None)
    return EngineDataset.from_csv(csv_path, columns, fmt).build_case(engine, **kwargs)
