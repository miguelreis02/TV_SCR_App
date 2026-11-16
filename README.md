# TECNOVERITAS SCR DIMENSIONING TOOL

Porte para Python dos scripts MATLAB **não binned** de
`Tronconi1998/DGX_Simulations/Geometric_Sweep_Alpha_Loop`, com todos os inputs
— geometria, condições de operação, cinética e alvos — expostos como
parâmetros.

O objetivo desta fase é **a compatibilização do solver**: o Python reproduz o
MATLAB e nada é assumido em silêncio. Por cima da biblioteca há uma interface
gráfica simples (`tvscr_ui`), que só recolhe inputs e mostra resultados.

Para abrir: **duplo clique em `TV_SCR.bat`** (procura sozinho um Python com as
bibliotecas), ou, num terminal onde o Python certo esteja no PATH — no Windows
com Anaconda, o *Anaconda Prompt*:

```bash
python app.py
```

A documentação oficial do programa está em **[INSTRUCOES.md](INSTRUCOES.md)**
— utilização, parâmetros, modelo e método, ficheiros de entrada e de saída,
limitações — e lê-se também dentro da aplicação (entrada «Documentação» da
barra lateral, ou `F1`). Este README documenta o porte a partir do MATLAB e a
paridade numérica.

---

## 1. Estado: paridade verificada

Comparação contra os CSV de referência gerados pelo MATLAB
(`Geometric_Sweep_Alpha_Loop/Results/`), cenário `Fouling = 0.15`,
`KK0 = 0.80`, CPSI 46, parede 0.43 mm:

| motor | linhas | erro rel. máx. (ciclo) | erro rel. máx. (modos) | V_crit Python | V_crit MATLAB |
|-------|--------|------------------------|------------------------|---------------|---------------|
| DG1   | 14     | 4.0e-15                | 1.3e-13                | 1.5400        | 1.5400        |
| DG2   | 14     | 8.9e-15                | 1.9e-13                | 3.0850        | 3.0850        |
| DG3   | 20     | 4.9e-14                | 5.1e-13                | 2.0600        | 2.0600        |
| DG4   | 12     | 1.1e-14                | 1.9e-13                | 1.9025        | 1.9025        |
| DG5   | 12     | 2.5e-14                | 1.9e-13                | 1.8775        | 1.8775        |

Coincidem **exatamente** (igualdade inteira) a situação de cada volume, o
número de iterações do loop de α, a fase (varrimento vs refinamento) e a
situação de cada modo. O resíduo de ~1e-13 é apenas arredondamento entre a
`libm` do MSVC e a do Python.

A **calibração de α** (`get_NOx_DG<k>.m` → `tvscr.calibrate_alpha`) reproduz os
`alpha_DG<k>.csv` com erro relativo ≤ 8e-16 nos cinco motores.

---

## 2. Correspondência com o MATLAB

| módulo Python            | origem MATLAB                              |
|--------------------------|--------------------------------------------|
| `tvscr/solver.py`        | `tronconi_sizing_forward_v2.m`             |
| `tvscr/cycle.py`         | `run_D2_geom.m`                            |
| `tvscr/alpha_loop.py`    | `alpha_event_loop.m`                       |
| `tvscr/sweep.py`         | `run_volume_sweep_alpha.m`                 |
| `tvscr/batch.py`         | `run_all_volume_sweeps_alpha.m`            |
| `tvscr/dataset.py`       | `get_mass_dot_v3.m` (leitura do CSV)       |
| `tvscr/exhaust.py`       | `get_mass_dot_v3.m` (cálculo dos caudais)  |
| `tvscr/operating.py`     | `precompute_D2_inputs_DGX.m`               |
| `tvscr/urea.py`          | `urea_flow_Lh.m` + `nh3_ppm.m`             |
| `tvscr/calibration.py`   | `Alphas/get_NOx_DG<k>.m`                   |
| `tvscr/reporting.py`     | `write_outputs` / `writetable`             |
| `tvscr/plotting.py`      | `make_figures` + figura-resumo             |
| `tvscr/numerics.py`      | semântica de `mode`, `a:d:b`, `interp1`, `\` |
| `tvscr/scenario.py`      | (novo) contrato declarativo de inputs      |
| `tvscr/substrate_sweep.py` | (novo) comparação de pares CPSI / parede |
| `tvscr_ui/`              | (novo) interface gráfica — não existia no MATLAB |
| `tvscr_ui/paged.py`      | (novo) separadores e tabela de introdução manual |
| `tvscr_ui/results.py`    | (novo) painel de resultados: resumo, modos, varrimento, gráfico e registo |
| `tvscr_ui/docs.py`       | (novo) leitor da documentação (`INSTRUCOES.md`) dentro da aplicação |

`sweep_engine.m` **não** foi portado: destinava-se a varrimentos 1-D/2-D em L e
A, que deixaram de existir quando o método passou a varrer o volume.
Os scripts *binned* também ficam de fora, como pedido.

---

## 3. Instalação

Requer Python ≥ 3.9 com `numpy`, `scipy` e `pandas`; `matplotlib` só é
necessário para as figuras e `pytest` para os testes.

```bash
pip install -r requirements.txt
```

Não há instalação do pacote: basta ter `TV_SCR_APP` no `sys.path`
(os exemplos e testes já o fazem sozinhos).

---

## 4. Arranque rápido

### Interface gráfica

Duplo clique em `TV_SCR.bat`, ou `python app.py` num terminal com o Python
certo (ver [INSTRUCOES.md](INSTRUCOES.md) §3).

Fundos claros e texto preto, com os pormenores no azul e no vermelho do
logótipo da TecnoVeritas; um rótulo por parâmetro e ajuda ao passar o rato.
As oito secções de inputs são páginas escondidas, escolhidas nos separadores da
barra lateral, agrupados em três blocos (dados do projeto, modelo do
catalisador, cálculo). Os dados do motor vêm de um CSV ou são introduzidos à
mão numa tabela. O cálculo corre numa *thread* separada. Por baixo do
formulário, o painel de resultados mostra o volume crítico em destaque
(*Resumo*), o ponto de operação por modo, a tabela e o gráfico do varrimento, e
o *Registo* — a consola, com a mesma tabela que os scripts MATLAB imprimiam.
Os inputs completos gravam-se e carregam-se como `.json` (o mesmo `RunScenario`
que a biblioteca usa) — e, em introdução manual, esse `.json` leva os dados do
motor dentro, ficando auto-suficiente. A entrada «Documentação» mostra o
`INSTRUCOES.md` na própria janela, com índice e procura.

A interface não calcula nada: monta um `RunScenario` e chama a biblioteca.
Ver [INSTRUCOES.md](INSTRUCOES.md) para o guia campo a campo e
[ALTERACOES_LAYOUT.md](ALTERACOES_LAYOUT.md) para o registo das alterações ao
layout da janela.

### Biblioteca

```python
from tvscr import (EngineDataset, SubstrateGeometry, EmissionTargets,
                   VolumeSweepOptions, AlphaLoopOptions, volume_sweep)

ds   = EngineDataset.from_csv("Tabela_Inputs_Final.csv")
case = ds.build_case("DG1", substrate=SubstrateGeometry(cpsi=46,
                                                        wall_thickness_m=0.43e-3))

s = volume_sweep(
        case,
        EmissionTargets(cycle_NO_frac=0.60, mode_NO_frac=0.80,
                        cycle_slip_ppm=10.0, mode_slip_ppm=20.0),
        VolumeSweepOptions(fouling=0.15, aging_KK0=0.80),
        AlphaLoopOptions(alpha0=0.80, dalpha=0.02))

print(s.critical_volume_m3, s.oversize)
s.to_dataframe()        # uma linha por volume
s.modes_dataframe()     # uma linha por (volume, modo)
```

Exemplos executáveis em `examples/`:

| ficheiro                          | mostra                                              |
|-----------------------------------|-----------------------------------------------------|
| `01_ponto_unico.py`               | solver 1-D num ponto, todos os inputs explícitos     |
| `02_varrimento_volume.py`         | varrimento de um motor + CSV + figura                |
| `03_todos_os_motores.py`          | todos os motores do ficheiro + resumo + `cenario.json` |
| `04_motor_novo_sem_ficheiro.py`   | motor novo com 5 modos, sem CSV; calibração de α     |
| `05_varrimento_substratos.py`     | compara pares CPSI / espessura de parede             |

O resultado do dimensionamento é o **volume crítico** — o menor reator que
cumpre os alvos — e o ponto de operação é reportado nesse volume. Não há
conceito de "volume instalado" nem de sobredimensionamento: a aplicação é de
projeto, não de validação de um reator existente.

---

## 5. O que é input (e onde)

Nada de físico está fixado no código de cálculo. O que uma interface tem de
recolher:

**Condições de operação — por modo do ciclo** (`OperatingMode`, ou colunas do
CSV via `ColumnMap`): carga [%], peso do modo, potência de travão [kW],
temperatura à entrada [°C ou K], NO à entrada [ppm], NO à saída medido [ppm]
(opcional), e `SFOC` + `λ` (donde sai o caudal de escape) **ou** diretamente o
caudal de escape [kg/s].

**Motor**: rotação nominal [rpm], potência nominal [kW], combustível.

**Geometria** (`SubstrateGeometry`, `ReactorGeometry`): CPSI, espessura de
parede [m], comprimento [m], área frontal [m²] (ou volume), *fouling* [-].
Note que **CPSI e parede não vêm do CSV** — são escolha de projeto, e por isso
`substrate_sweep` permite compará-las em vez de as arbitrar.

**Cinética** (`KineticParameters`): `k0ads`, `Eads`, `k0NO`, `ENO`, `KK0`,
`k0d`, `E0d`, `β`, `f`, `Deff`, `Dmol`, `M̄`, e as constantes de gás. Os
defaults são a Tabela 2 de Tronconi 1998 (catalisador 1).

**Alvos** (`EmissionTargets`): frações do limite regulamentar e slip [ppm], nos
dois níveis (por modo e no ciclo ponderado).

**Numérico** (`SolverOptions`, `AlphaLoopOptions`, `VolumeSweepOptions`): nós
axiais, tolerâncias, α de arranque e passo, passo e refinamento do volume.

**Doseamento** (`UreaSolution`): fração mássica, densidade, massas molares.

`RunScenario` junta tudo num objeto serializável para JSON
(`RunScenario.from_dict` / `.to_dict`) — é o contrato que a futura interface
preenche.

### Leitor de CSV parametrizável

`ColumnMap` mapeia cada coluna lógica para um nome (ou índice) do ficheiro, e
`DatasetFormat` define separador, símbolo decimal, codificação, unidade de
temperatura e se a carga vem em fração ou em percentagem. Os defaults
reproduzem `Tabela_Inputs_Final.csv`, mas **nada assume 5 motores nem 4 modos**:
`EngineDataset.engines()` descobre os que existirem e o ciclo tem os modos que
tiver.

---

## 6. Método: varrimento em volume com α adaptativo

Com α congelado, a pergunta é *«o que acontece a este reator se o encolher sem
mexer no doseamento»*. Com α adaptativo é *«qual é o menor reator viável»* —
porque um reator menor seria, na prática, operado com outro doseamento.

Em cada volume, `alpha_event_loop` procura o vetor de α (um por modo) que
cumpre simultaneamente NO_out e slip, em dois níveis:

|            | por modo              | ciclo ponderado        |
|------------|-----------------------|------------------------|
| NO_out     | ≤ 80 % do limite      | ≤ 60 % do limite       |
| NH₃ slip   | ≤ 20 ppm              | ≤ 10 ppm               |

**Situações** — A: NO_out abaixo do alvo · B: acima · C: slip abaixo · D: acima.

| situação | eventos | ação                                        |
|----------|---------|---------------------------------------------|
| 1        | A + C   | alvos cumpridos → fecha o loop              |
| 2        | B + C   | falta conversão → aumentar α                |
| 3        | A + D   | slip excessivo → reduzir α                  |
| 4        | B + D   | janela de α vazia → **volume inadmissível** |

Duas decisões de arquitetura herdadas do MATLAB, ambas deliberadas:

- **A situação 4 é avaliada por modo, não por agregação.** Cada modo tem o seu
  próprio α; ter o modo *i* em situação 2 e o modo *j* em situação 3 não é
  inviabilidade. Agregar `any(B)` com `any(D)` declararia falsas inviabilidades.
- **Bracketing + bisseção geométrica.** Um passo multiplicativo puro de ±2 %
  pode oscilar 2↔3 sem nunca cair na 1 nem na 4 se a janela viável for mais
  estreita que o passo. Guardando `[lo, hi]` por modo e passando a bisseção
  quando ambos existem, a situação 4 torna-se **deteção fiável de
  inviabilidade** e não um acaso do passo.

O varrimento desce em volume (L fixo, `A = V/L`) até ao primeiro volume
inadmissível e depois **bisseta em V** entre o último admissível e o primeiro
falhado, para afinar o volume crítico além da resolução do passo.

### α no arranque

Enquanto o reator tem folga, o α de arranque (0.80) já cumpre tudo e o loop
fecha com **1 iteração** — o caudal de ureia fica no valor de arranque em vez
de num ponto de operação determinado. É fiel ao enunciado, mas torna a ureia
pouco informativa longe do volume crítico. `AlphaLoopOptions(minimize_alpha=True)`
desce o α por modo enquanto os alvos se mantiverem, devolvendo o **α mínimo
admissível**. Não altera o volume crítico — só o ponto de operação reportado.

---

## 7. Fidelidade: o que foi preservado tal e qual

Estas escolhas do MATLAB foram **mantidas** para garantir paridade. Estão aqui
documentadas porque algumas surpreendem à leitura:

1. **`x*` vem do módulo de Thiele do NH₃**, e é reutilizado no termo do NO. Não
   é lapso: `x*` é a fronteira da zona com NH₃ adsorvido, e é essa que delimita
   onde o NO pode reagir.
2. **`AV_Nmh = AV · 3600 · 273.15`.** É a convenção usada nos resultados de
   referência. Uma normalização a 0 °C dividiria por `T` em vez de multiplicar
   por 273.15, pelo que a coluna `AV_Nmh` deve ser lida como um indicador
   relativo, não como um caudal normalizado em Nm³/h/m². Foi mantida para que
   os CSV coincidam com os do MATLAB.
3. **A temperatura passada ao solver é KELVIN**, apesar do argumento se chamar
   `T_C` no cabeçalho MATLAB (que o usava diretamente como `T`). Aqui chama-se
   `T_K`.
4. **Newton 2×2 amortecido com projeção**, reproduzido passo a passo (mesmo
   jacobiano por diferenças finitas com `h = 1e-7·max(|x|, escala)`, mesmo
   *line search*, mesma deteção de restrição ativa), porque os diagnósticos
   `valid` / `valid_strict` dependem dele. `solve2x2` reproduz o `\` do MATLAB
   com a mesma ordem de operações do LAPACK.
5. **Quando o loop fecha por colapso do intervalo, saturação ou estagnação**, o
   α devolvido já é o *atualizado* mas o ciclo `r` é o da iteração anterior.
   Comportamento do original, preservado — a ureia usa o α devolvido e as
   restantes colunas usam `r`.
6. **`XNO_ciclo` é média ponderada direta**, enquanto `NOx_ciclo` e
   `slip_ciclo` passam pela interpolação em carga. Coincidem quando os modos
   *são* os pontos do ciclo (o caso do dataset); ambos os caminhos foram
   portados.

---

## 8. Diferenças deliberadas face ao MATLAB

| tema | MATLAB | aqui | porquê |
|---|---|---|---|
| α calibrado | `precompute` **exigia** `alpha_DG<k>.mat`, mesmo sendo depois substituído a cada iteração do loop | opcional (`case.alpha_calibrated`); `calibrate_alpha` recalibra a partir das medições | um motor novo não tem `.mat`, e o varrimento não usa esse α |
| limite Tier III | `9·n^-0.2` em toda a gama | regra MARPOL completa por omissão (patamares em `n < 130` e `n ≥ 2000`); `tier_power_law_only=True` volta ao original | coincidem entre 130 e 2000 rpm (os 513 rpm do dataset); fora dessa gama a lei de potência dá o valor errado |
| `Fouling` / `KK0` | defaults escondidos (0.15 / 0.80) dentro de `fill_defaults` | `VolumeSweepOptions(fouling=..., aging_KK0=...)`, sem omissão implícita (caso limpo por omissão) | um cenário de projeto não deve estar escondido num default |
| nº de motores / modos | `DGlist = 1:5`, 4 modos D2 | descoberto do ficheiro; qualquer nº de modos | escalabilidade |
| saídas | `.mat` + `.csv` + `.png` | `.csv` + `.png`; os resultados vivem em dataclasses/DataFrames | `.mat` deixa de fazer sentido fora do MATLAB |

---

## 9. Saídas

Por motor, em `<outdir>/<motor>/`:

- `volume_sweep_<motor>.csv` — uma linha por volume: V, A, situação,
  admissível, NOx/slip/X_NO/ureia do ciclo, nº de iterações e fase.
- `volume_sweep_<motor>_modos.csv` — uma linha por (volume, modo): α, X_NO,
  NO [g/kWh], slip, ureia, τ, AV, η, situação do modo.
- `volume_sweep_<motor>.png` — painel 2×2 (NOx, slip em log, α por modo, ureia).

Na raiz: `resumo_volumes_criticos.csv` e `.png`.

Os nomes de ficheiro e de coluna são os do MATLAB, para comparação direta.

---

## 10. Testes

```bash
python -m pytest tests -q
```

- `tests/test_units.py` — invariantes físicas, helpers de compatibilidade,
  ponto de regressão do solver, loop de α, cenário. **Não** depende do MATLAB.
- `tests/test_matlab_parity.py` — compara os cinco motores contra os CSV de
  referência. Corre também isolado, imprimindo o erro máximo:
  `python tests/test_matlab_parity.py`
- `tests/test_alpha_calibration_parity.py` — compara `calibrate_alpha` contra
  `Alphas/alpha_DG<k>.csv`.
- `tests/test_substrate_sweep.py` — cada par reproduz um varrimento normal com
  esse substrato, e pares impossíveis são registados em vez de rebentarem.
- `tests/test_exhaust.py` — o cálculo do caudal de escape, incluindo o AFR por
  balanço elementar e a margem de 10 % da coluna de consumo do dataset.
- `tests/test_ui.py` — a janela monta o `RunScenario` certo a partir do
  formulário, rejeita valores inválidos levando o utilizador ao campo, e o
  painel de resultados mostra os números que a biblioteca devolveu. Verifica
  também a documentação: todas as ligações resolvem, todos os campos do
  formulário estão documentados e os valores por omissão escritos coincidem
  com os da aplicação.

Os testes de paridade são automaticamente ignorados se os ficheiros MATLAB não
estiverem presentes; os da interface, se não houver `tkinter` ou ecrã.

---

## 11. Desempenho

Cada chamada ao solver é uma marcha sequencial em 120 nós com um Newton 2×2 por
nó — não vetorizável ao longo de `z`. Na prática: ~0,2 s por ponto de operação,
~0,9 s por ciclo de 4 modos, **~4 s por varrimento completo de um motor** e
~25 s pelos cinco. Suficiente para uso interativo; se um dia for preciso mais,
o alvo natural é compilar `effective_rates` + `_newton2` (numba ou Cython),
que dominam o tempo.
