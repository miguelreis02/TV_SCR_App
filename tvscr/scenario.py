"""
Cenario de calculo declarativo -- o contrato de INPUTS da aplicacao.

Junta num unico objecto tudo o que e preciso pedir ao utilizador para correr
um dimensionamento, e sabe converter-se de/para ``dict`` (logo, de/para JSON,
formulario web, ficheiro de configuracao...). Nao ha interface aqui: e apenas
o esquema de dados que qualquer interface tera de preencher.

Uso::

    scn = RunScenario.from_dict(json.load(open("cenario.json")))
    batch = scn.run()

Todos os campos tem valor por omissao documentado, mas nenhum e imposto pelo
codigo de calculo: o que nao for dado usa o default do cenario, nao um numero
escondido no solver.
"""

from __future__ import annotations

from dataclasses import (asdict, dataclass, field, fields, is_dataclass,
                         replace)
from pathlib import Path
from typing import (Any, Dict, List, Optional, Sequence, Union, get_args,
                    get_origin, get_type_hints)

from .alpha_loop import AlphaLoopOptions
from .batch import BatchResult, run_all_volume_sweeps
from .dataset import ColumnMap, DatasetFormat, EngineDataset
from .geometry import ReactorGeometry, SubstrateGeometry
from .kinetics import KineticParameters, KineticTuning
from .operating import EngineCase
from .solver import SolverOptions
from .substrate_sweep import SubstrateSweepResult, substrate_sweep
from .sweep import VolumeSweepOptions, VolumeSweepResult, volume_sweep
from .targets import EmissionTargets
from .urea import UreaSolution

__all__ = ["RunScenario"]


def _unwrap_optional(tp):
    """``Optional[X]`` / ``Union[X, None]`` -> ``X``; caso contrario, ``tp``."""
    args = [a for a in get_args(tp) if a is not type(None)]  # noqa: E721
    if get_origin(tp) is Union and len(args) == 1:
        return args[0]
    return tp


def _build(cls, value):
    """Constroi um dataclass a partir de ``dict``, recursivamente.

    Campos cujo tipo declarado e, ele proprio, um dataclass (p.ex.
    ``KineticParameters.gas`` ou ``VolumeSweepOptions.tuning``) sao
    construidos a partir do sub-dicionario correspondente.
    """
    if value is None:
        return cls()
    if isinstance(value, cls):
        return value
    if not isinstance(value, dict):
        raise TypeError(f"{cls.__name__}: esperava dict, recebi {type(value).__name__}")

    known = {f.name for f in fields(cls)}
    unknown = set(value) - known
    if unknown:
        raise KeyError(f"{cls.__name__}: campos desconhecidos {sorted(unknown)}. "
                       f"Aceites: {sorted(known)}")

    try:
        hints = get_type_hints(cls, include_extras=False)
    except Exception:                     # anotacoes nao resolviveis: sem recursao
        hints = {}

    kwargs = {}
    for key, raw in value.items():
        tp = _unwrap_optional(hints.get(key))
        if isinstance(raw, dict) and is_dataclass(tp) and isinstance(tp, type):
            kwargs[key] = _build(tp, raw)
        else:
            kwargs[key] = raw
    return cls(**kwargs)


@dataclass
class RunScenario:
    """Tudo o que um dimensionamento precisa de receber do exterior.

    Parameters
    ----------
    dataset_path:
        Ficheiro de inputs dos motores. ``None`` se os casos forem construidos
        pela aplicacao (ver :meth:`RunScenario.with_cases`).
    engines:
        Motores a correr. ``None`` = todos os que existirem no ficheiro.
    fuel:
        Combustivel (nome do catalogo).
    substrate:
        Geometria da celula do monolito (CPSI, espessura de parede). NAO vem
        do ficheiro de inputs -- e escolha de projecto.
    kinetics:
        Cinetica e transporte.
    tuning:
        Multiplicadores de calibracao da cinetica.
    targets:
        Alvos de emissao e de slip.
    sweep, alpha_loop, solver:
        Opcoes do varrimento, do loop de alpha e numericas.
    urea:
        Propriedades da solucao doseada.
    pressure_Pa:
        Pressao de operacao.
    tier, tier_power_law_only:
        Regulamento de referencia. ``tier_power_law_only=True`` reproduz o
        MATLAB (lei de potencia em toda a gama de rotacoes).
    output_dir:
        Pasta onde gravar CSV e figuras; ``None`` = nao grava.
    """

    dataset_path: Optional[Union[str, Path]] = None
    engines: Optional[Sequence[str]] = None
    fuel: str = "HFO"

    substrate: SubstrateGeometry = field(default_factory=SubstrateGeometry)
    kinetics: KineticParameters = field(default_factory=KineticParameters)
    tuning: KineticTuning = field(default_factory=KineticTuning)
    targets: EmissionTargets = field(default_factory=EmissionTargets)
    sweep: VolumeSweepOptions = field(default_factory=VolumeSweepOptions)
    alpha_loop: AlphaLoopOptions = field(default_factory=AlphaLoopOptions)
    solver: SolverOptions = field(default_factory=SolverOptions)
    urea: UreaSolution = field(default_factory=UreaSolution)

    columns: ColumnMap = field(default_factory=ColumnMap)
    dataset_format: DatasetFormat = field(default_factory=DatasetFormat)

    pressure_Pa: float = 101325.0
    tier: str = "III"
    tier_power_law_only: bool = False
    output_dir: Optional[Union[str, Path]] = None

    #: Sobrepoem-se a geometria INSTALADA lida do ficheiro (``None`` = usa a do
    #: ficheiro). Aplicam-se a todos os motores do cenario, pelo que so fazem
    #: sentido quando se corre um motor de cada vez.
    length_m: Optional[float] = None
    frontal_area_m2: Optional[float] = None
    volume_m3: Optional[float] = None

    #: Substratos a COMPARAR, em vez do unico ``substrate``. Cada elemento e
    #: ``{"cpsi": .., "wall_thickness_m": ..}``. Quando preenchido,
    #: :meth:`run_substrate_sweep` corre o varrimento em volume uma vez por
    #: par (motor, substrato).
    substrates: Optional[List[Dict[str, Any]]] = None

    #: Dados de motor EMBUTIDOS no cenario, em vez de lidos de um ficheiro.
    #: Cada elemento e um dicionario com ``name``, ``engine_speed_rpm``,
    #: opcionalmente ``rated_power_kW``, ``length_m``, ``frontal_area_m2``, e
    #: ``modes`` -- uma lista com um dicionario por modo do ciclo contendo
    #: ``load_pct``, ``weight``, ``power_kW``, ``T_in_K``, ``NO_in_ppm`` e, para
    #: o caudal de escape, ``exhaust_mass_flow_kgs`` OU ``sfoc_g_per_kWh`` +
    #: ``lambda_``. ``NO_out_ppm`` e opcional (so serve para calibrar).
    #: Torna o cenario auto-suficiente: o JSON corre sem CSV nenhum.
    inline_engines: Optional[List[Dict[str, Any]]] = None

    #: Casos ja construidos pela aplicacao (alternativa aos dois anteriores).
    cases: Optional[List[EngineCase]] = None

    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunScenario":
        """Constroi o cenario a partir de um dicionario aninhado (p.ex. JSON)."""
        data = dict(data)
        nested = {
            "substrate": SubstrateGeometry, "kinetics": KineticParameters,
            "tuning": KineticTuning, "targets": EmissionTargets,
            "sweep": VolumeSweepOptions, "alpha_loop": AlphaLoopOptions,
            "solver": SolverOptions, "urea": UreaSolution,
            "columns": ColumnMap, "dataset_format": DatasetFormat,
        }
        for key, klass in nested.items():
            if key in data:
                data[key] = _build(klass, data[key])
        # a cinetica pode trazer o envelhecimento no cenario do varrimento
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa o cenario (os dataclasses viram dicionarios)."""
        out: Dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "cases":
                continue
            if is_dataclass(value) and not isinstance(value, type):
                out[f.name] = asdict(value)
            elif isinstance(value, Path):
                out[f.name] = str(value)
            else:
                out[f.name] = value
        return out

    # ------------------------------------------------------------------ #
    def with_cases(self, cases: Sequence[EngineCase]) -> "RunScenario":
        """Usa casos construidos pela aplicacao em vez de ler um ficheiro."""
        self.cases = list(cases)
        return self

    def build_case_from_spec(self, spec: Dict[str, Any]) -> EngineCase:
        """Constroi um :class:`EngineCase` a partir de dados embutidos.

        Ver :attr:`inline_engines` para o formato do dicionario.
        """
        modes = spec.get("modes") or []
        if not modes:
            raise ValueError(
                f'Motor "{spec.get("name", "?")}": nenhum modo do ciclo indicado.')

        def column(key: str):
            values = [m.get(key) for m in modes]
            return None if any(v is None for v in values) else values

        length = spec.get("length_m", self.length_m)
        area = spec.get("frontal_area_m2", self.frontal_area_m2)
        volume = spec.get("volume_m3", self.volume_m3)
        if length is None:
            raise ValueError(
                f'Motor "{spec.get("name", "?")}": falta o comprimento (length_m).')
        if area is None:
            if volume is None:
                raise ValueError(
                    f'Motor "{spec.get("name", "?")}": falta a area frontal '
                    f"(frontal_area_m2) ou o volume (volume_m3).")
            area = float(volume) / float(length)

        geometry = ReactorGeometry(
            length_m=float(length), frontal_area_m2=float(area),
            substrate=self.substrate, fouling=0.0)   # o fouling e do varrimento

        return EngineCase.from_arrays(
            str(spec.get("name", "motor")), geometry,
            load_pct=column("load_pct"), weight=column("weight"),
            power_kW=column("power_kW"), T_in_K=column("T_in_K"),
            NO_in_ppm=column("NO_in_ppm"),
            exhaust_mass_flow_kgs=column("exhaust_mass_flow_kgs"),
            sfoc_g_per_kWh=column("sfoc_g_per_kWh"),
            lambda_=column("lambda_"),
            NO_out_ppm=column("NO_out_ppm"),
            fuel=self.fuel,
            kinetics=self.kinetics,
            engine_speed_rpm=spec.get("engine_speed_rpm"),
            rated_power_kW=spec.get("rated_power_kW"),
            nox_limit_gkWh=spec.get("nox_limit_gkWh"),
            pressure_Pa=self.pressure_Pa,
            tier=self.tier, tier_power_law_only=self.tier_power_law_only)

    def build_cases(self) -> List[EngineCase]:
        """Constroi os :class:`EngineCase` do cenario."""
        if self.cases:
            return list(self.cases)
        if self.inline_engines:
            specs = self.inline_engines
            if self.engines:
                wanted = {str(e) for e in self.engines}
                specs = [s for s in specs if str(s.get("name")) in wanted]
                if not specs:
                    raise ValueError(
                        f"Nenhum dos motores {sorted(wanted)} existe nos dados "
                        f"embutidos.")
            return [self.build_case_from_spec(spec) for spec in specs]
        if self.dataset_path is None:
            raise ValueError(
                "RunScenario: indique dataset_path, inline_engines, ou forneca "
                "casos com with_cases().")
        ds = EngineDataset.from_csv(self.dataset_path, self.columns, self.dataset_format)
        names = list(self.engines) if self.engines else ds.engines()
        return [
            ds.build_case(name, fuel=self.fuel, kinetics=self.kinetics,
                          substrate=self.substrate, pressure_Pa=self.pressure_Pa,
                          tier=self.tier, tier_power_law_only=self.tier_power_law_only,
                          length_m=self.length_m,
                          frontal_area_m2=self.frontal_area_m2,
                          volume_m3=self.volume_m3)
            for name in names
        ]

    def _sweep_options(self) -> VolumeSweepOptions:
        """Opcoes do varrimento com o tuning do cenario, sem mutar o original.

        ``VolumeSweepOptions.tuning`` so e substituido se estiver por preencher
        (ausente ou identidade): um tuning definido no varrimento tem
        precedencia sobre o do cenario.
        """
        opts = self.sweep
        if opts.tuning is None or opts.tuning.is_identity:
            return replace(opts, tuning=self.tuning)
        return opts

    # ------------------------------------------------------------------ #
    def run(self) -> BatchResult:
        """Corre o varrimento em volume de todos os motores do cenario."""
        sweep_opts = self._sweep_options()

        batch = run_all_volume_sweeps(
            self.build_cases(), self.targets, sweep_opts, self.alpha_loop,
            solver_options=self.solver, urea=self.urea)

        if self.output_dir is not None:
            from .reporting import write_all
            write_all(batch, self.output_dir)
        return batch

    def run_substrate_sweep(self) -> SubstrateSweepResult:
        """Compara varios pares CPSI / espessura de parede.

        Usa :attr:`substrates`; se estiver vazio, compara apenas o
        :attr:`substrate` unico (o resultado e entao equivalente a
        :meth:`run`, mas na forma de tabela de substratos).
        """
        from .geometry import SubstrateGeometry

        specs = self.substrates or [{"cpsi": self.substrate.cpsi,
                                     "wall_thickness_m": self.substrate.wall_thickness_m}]
        subs = [SubstrateGeometry(cpsi=float(s["cpsi"]),
                                  wall_thickness_m=float(s["wall_thickness_m"]))
                for s in specs]
        result = substrate_sweep(
            self.build_cases(), subs, self.targets, self._sweep_options(),
            self.alpha_loop, solver_options=self.solver, urea=self.urea,
            verbose=self.sweep.verbose)

        if self.output_dir is not None:
            from pathlib import Path as _Path
            out = _Path(self.output_dir)
            out.mkdir(parents=True, exist_ok=True)
            result.summary.to_csv(out / "resumo_substratos.csv", index=False)
        return result

    def run_one(self, engine: str) -> VolumeSweepResult:
        """Corre so um motor do cenario."""
        cases = {c.name: c for c in self.build_cases()}
        if engine not in cases:
            raise KeyError(f'Motor "{engine}" nao esta no cenario. '
                           f"Disponiveis: {sorted(cases)}")
        sweep_opts = self._sweep_options()
        return volume_sweep(cases[engine], self.targets, sweep_opts,
                            self.alpha_loop, solver_options=self.solver,
                            urea=self.urea)
