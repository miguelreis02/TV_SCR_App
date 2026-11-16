# TECNOVERITAS SCR DIMENSIONING TOOL — Documentação

Documentação oficial do programa, versão **0.1.0**. Descreve a utilização da
aplicação, todos os parâmetros, o modelo e o método de cálculo, os ficheiros de
entrada e de saída, e os limites de validade dos resultados.

Esta documentação lê-se também **dentro da aplicação**: entrada «Documentação»
da barra lateral, ou tecla `F1` (ver §4).

O [README](README.md) complementa-a com a correspondência entre o código Python
e os scripts MATLAB de origem e com a verificação de paridade numérica.

---

## Índice

**Utilização**

- [1. O que a aplicação faz](#1-o-que-a-aplicação-faz)
- [2. Requisitos e instalação](#2-requisitos-e-instalação)
- [3. Abrir a aplicação](#3-abrir-a-aplicação)
- [4. O ecrã](#4-o-ecrã)
- [5. Primeiro dimensionamento, passo a passo](#5-primeiro-dimensionamento-passo-a-passo)
- [6. Os campos, um a um](#6-os-campos-um-a-um)
- [7. Ler os resultados](#7-ler-os-resultados)
- [8. Guardar e repetir um estudo](#8-guardar-e-repetir-um-estudo)
- [9. Quando não há volume admissível](#9-quando-não-há-volume-admissível)
- [10. Erros comuns](#10-erros-comuns)

**Referência**

- [11. Modelo e método de cálculo](#11-modelo-e-método-de-cálculo)
- [12. Ficheiro de inputs (CSV)](#12-ficheiro-de-inputs-csv)
- [13. Ficheiros de saída](#13-ficheiros-de-saída)
- [14. Ficheiro de cenário (.json)](#14-ficheiro-de-cenário-json)
- [15. Reproduzir os resultados do MATLAB](#15-reproduzir-os-resultados-do-matlab)
- [16. Usar sem interface](#16-usar-sem-interface)
- [17. Pressupostos e limitações](#17-pressupostos-e-limitações)
- [18. Nomenclatura](#18-nomenclatura)
- [19. Estrutura do projeto e testes](#19-estrutura-do-projeto-e-testes)
- [20. Referências](#20-referências)
- [21. Ficha técnica](#21-ficha-técnica)

---

## 1. O que a aplicação faz

Dado um motor — o seu ciclo de operação, as condições de escape e o
catalisador escolhido — a aplicação responde a **uma** pergunta:

> **Qual é o menor reator SCR que cumpre os alvos de NOx e de NH₃ slip?**

Esse é o **volume crítico**. Do resultado saem também a área frontal
correspondente (`A = V / L`), o doseamento (α por modo), o consumo de ureia e a
conversão, todos avaliados **nesse volume** — que é o reator a instalar.

Fá-lo varrendo o volume para baixo, com o doseamento a adaptar-se a cada
geometria, sujeito aos limites de emissão e de slip. Um reator maior que o
crítico cumpre com folga; um menor não cumpre de todo.

> **Não há aqui nenhuma validação experimental.** O NO à saída, a conversão e o
> slip são **calculados pelo modelo**, não medidos: são o resultado, não uma
> referência contra a qual comparar. A qualidade do dimensionamento depende de
> os inputs (condições de escape, cinética, envelhecimento, fouling) descreverem
> o caso real.

**Âmbito.** A aplicação é de **projeto**: dimensiona o volume de catalisador de
um reator SCR-deNOx de monolito, a jusante de um motor diesel marítimo, para um
ciclo de ensaio em regime estacionário. Não simula transitórios, não calcula a
perda de carga nem o sistema de injeção e mistura de ureia, e não valida um
reator já instalado. Os pressupostos e os limites de validade estão na §17.

---

## 2. Requisitos e instalação

- Python 3.9 ou mais recente, com `tkinter` (vem no instalador oficial de
  Windows e no Anaconda).
- Bibliotecas: `numpy`, `scipy`, `pandas`. `matplotlib` só é preciso para as
  figuras (o separador «Gráfico» e os ficheiros `.png`).

| biblioteca | versão mínima | para quê |
|---|---|---|
| `numpy` | 1.22 | Cálculo |
| `scipy` | 1.8 | Cálculo |
| `pandas` | 1.4 | Leitura do CSV e tabelas de resultados |
| `matplotlib` | 3.5 | Opcional: figuras |
| `pytest` | 7.0 | Opcional: testes |

Se usa Anaconda, já tem tudo. Caso contrário, no Anaconda Prompt (ou no
terminal onde o Python certo esteja acessível), a partir da pasta do projeto:

```bash
pip install -r requirements.txt
```

Não há instalação do programa propriamente dita: basta a pasta do projeto, com
os pacotes `tvscr` (cálculo) e `tvscr_ui` (interface) lado a lado.

---

## 3. Abrir a aplicação

### Modo mais simples: duplo clique

Abra a pasta `TV_SCR_APP` no Explorador do Windows e faça **duplo clique em
`TV_SCR.bat`**. O lançador procura sozinho um Python com as bibliotecas
necessárias e abre a janela. Não é preciso terminal nenhum.

Se quiser, arraste o `TV_SCR.bat` para o Ambiente de Trabalho com o botão
direito → *Criar atalhos aqui*.

### Por terminal

Abra o **Anaconda Prompt** (Menu Iniciar → «Anaconda Prompt») e escreva:

```bash
cd /d "D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\TV_SCR_APP"
```

```bash
python app.py
```

> **Atenção — PowerShell e Linha de Comandos normais não servem sem mais nada.**
> O `python` que está no PATH do Windows é o atalho da Microsoft Store, que não
> tem numpy nem scipy: responde *«Python não foi encontrado»*. Ou usa o Anaconda
> Prompt (que põe o Python certo no PATH), ou o `TV_SCR.bat`, ou indica o
> caminho completo do interpretador:

```bash
& "C:\Users\migue\anaconda3\python.exe" app.py
```

(o `&` é só necessário no PowerShell, por causa das aspas; na Linha de Comandos
escreve-se sem ele.)

Alternativa equivalente ao `app.py`, a partir da mesma pasta:

```bash
python -m tvscr_ui
```

Se faltar alguma dependência, o programa diz qual e não abre a janela.

---

## 4. O ecrã

```
┌────────────────────────────────────────────────────────────────────────┐
│ TECNOVERITAS SCR DIMENSIONING TOOL                           [logo TV] │ título
├─────────────────┬──────────────────────────────────────────────────────┤
│ DADOS DO PROJETO│ 1 · Dados do motor            [◀ Anterior] 1/8 [▶]   │
│ ▌1 · Motor      │ ┌──────────────────────────┐ ┌───────────────────┐   │ página de
│  2 · Geometria  │ │ cartão                   │ │ cartão            │   │ inputs
│  3 · Alvos      │ │ rótulo ⓘ [campo] unidade │ │                   │   │ (só a do
│ MODELO DO CAT.  │ └──────────────────────────┘ └───────────────────┘   │ separador
│  4 · Cinética   │                                                      │ escolhido)
│  5 · Calibração ├═══════════ divisor arrastável ═══════════════════════┤
│ CÁLCULO         │ [Resumo][Modos][Varrimento][Gráfico][Registo]        │
│  6 · Varrimento │ ┌──────────────┐┌────────┐┌────────┐┌──────┐┌──────┐ │ painel de
│  7 · Loop de α  │ │VOLUME CRÍTICO││ NOx    ││ slip   ││ X_NO ││ureia │ │ resultados
│  8 · Numérico   │ │ 1.540 m³     ││ + alvo ││ + alvo ││      ││      │ │
│ CENÁRIO         │ └──────────────┘└────────┘└────────┘└──────┘└──────┘ │
│  Carregar…      │                                                      │
│  Gravar…        │                                                      │
│  Repor omissões │                                                      │
│ AJUDA           │                                                      │
│  Documentação   │                                                      │
│ [▶ Correr dim.] │                                                      │
├─────────────────┴──────────────────────────────────────────────────────┤
│ Pronto                              F1 documentação · F5 correr · ...  │ estado
└────────────────────────────────────────────────────────────────────────┘
```

**Barra lateral (à esquerda).** Os oito separadores de inputs, agrupados em
três blocos — *Dados do projeto*, *Modelo do catalisador* e *Cálculo* — seguidos
das ações sobre o cenário, da entrada **Documentação** e, sempre visível ao
fundo, do botão **▶ Correr dimensionamento**. O separador ativo tem uma marca
vermelha à esquerda. Um ponto vermelho à direita de um separador assinala que
ele tem um campo com valor inválido.

**Página de inputs (em cima).** As oito secções são **páginas escondidas**: só
se vê a do separador escolhido, com o título e a descrição no topo. Os botões
**◀ Anterior** / **Seguinte ▶** percorrem as páginas pela ordem. Dentro de cada
página os campos estão agrupados em cartões, com o rótulo, o campo e a unidade
em colunas alinhadas.

**Painel de resultados (em baixo).** Cinco separadores: *Resumo*, *Modos*,
*Varrimento*, *Gráfico* e *Registo* (ver §7). O *Registo* é a consola de
sempre; os outros mostram os mesmos números de forma estruturada.

**Divisor.** A linha entre a página de inputs e os resultados arrasta-se com o
rato para dar mais altura a uma ou a outra. Um duplo clique no divisor repõe o
ajuste automático. **Rolar nos resultados não mexe no formulário** (e
vice-versa).

**Barra de estado (ao fundo).** Diz o que a aplicação está a fazer — durante o
cálculo, com uma barra de progresso e o tempo decorrido — e lembra os atalhos
de teclado:

| atalho | faz |
|---|---|
| `F1` | Abrir a documentação, na secção do separador em que se está |
| `F5` (ou `Ctrl+Enter`) | Correr dimensionamento |
| `Ctrl+O` | Carregar cenário |
| `Ctrl+S` | Gravar cenário |
| `Ctrl+PgDn` / `Ctrl+PgUp` | Separador seguinte / anterior |
| `Ctrl+F` | Procurar na documentação |
| `Esc` | Sair da documentação e voltar ao dimensionamento |

Não é preciso percorrer todos os separadores: todos os campos têm valor por
omissão, tirando os dados do motor. Na prática, para um primeiro cálculo basta
o separador **1 · Dados do motor**.

**O «i» num círculo ao lado de um parâmetro** indica que ele tem uma explicação
curta: passe o rato sobre o «i» (ou sobre o nome do parâmetro) para a ver.

Os números muito grandes ou muito pequenos aparecem em notação científica curta
(`2.5e10`, `1e-6`); pode escrevê-los assim ou por extenso, com ponto ou vírgula
decimal.

### Documentação dentro da aplicação

A entrada **Documentação** da barra lateral (grupo *Ajuda*) mostra este
documento no lugar do formulário e dos resultados. O que se lê é sempre o
ficheiro `INSTRUCOES.md` da pasta do projeto: se o editar, a aplicação mostra a
versão nova da próxima vez que abrir a documentação.

| elemento | faz |
|---|---|
| **Índice** (à esquerda) | Lista das secções; um clique leva à secção. A secção que está a ser lida fica realçada |
| **Procurar** (em cima, à direita) | Escreva e prima `Enter`: realça todas as ocorrências, no texto e nas tabelas. `Enter` ou **▼** vai para a seguinte; `Shift+Enter` ou **▲**, para a anterior |
| Ligações a azul | Uma ligação a uma secção leva a ela; uma ligação a outro ficheiro do projeto (o README, por exemplo) abre-o no mesmo leitor — o botão **Documentação principal** volta a este documento; uma ligação à Internet abre o navegador |
| **◀ Voltar ao dimensionamento** | Regressa ao formulário e aos resultados. Escolher um dos oito separadores ou premir `Esc` faz o mesmo |

Um cálculo que esteja a correr continua enquanto se lê a documentação; nada do
que está no formulário se perde.

---

## 5. Primeiro dimensionamento, passo a passo

No separador **1 · Dados do motor**, escolha a origem dos dados: **Ficheiro
CSV** ou **Introdução manual**.

### A partir de um ficheiro CSV

1. **Ficheiro (CSV)** — carregue em **Procurar…** e escolha o ficheiro de
   inputs (formato na §12). A lista «Motor» passa a ter os motores que ele traz.
2. **Motor** — escolha da lista. Logo por baixo aparece o que o ficheiro traz
   para esse motor: o número de modos, o limite MARPOL, a gama de caudais de
   escape e o NO à entrada (a mesma informação fica no *Registo*).
3. No separador **2 · Geometria**, indique o **Comprimento L** do monolito (fica
   fixo; é a área frontal que varia).
4. No separador **4 · Cinética**, confirme o **Envelhecimento KK0** e o
   **Fouling** — é este par que decide se o reator cumpre ao fim da vida ou só
   no primeiro dia.
5. No separador **6 · Varrimento**, indique o **Volume máximo** a considerar. Se
   nem esse volume cumprir, não há solução no intervalo e a aplicação diz-lho.
6. No separador **8 · Numérico e saída**, escolha a **pasta de resultados**. Se
   deixar em branco, nada é escrito em disco (a aplicação avisa).
7. Prima **▶ Correr dimensionamento** (barra lateral, ou `F5`).

Durante o cálculo o painel de resultados mostra o *Registo* a encher; no fim
passa sozinho ao *Resumo*, com o volume crítico em destaque.

Se algum campo tiver um valor inválido, a aplicação abre o separador onde ele
está, põe o cursor nesse campo (a vermelho claro) e diz qual é o problema.

Para correr todos os motores de uma vez, ligue **«Correr todos os motores do
ficheiro»**. Nesse caso o campo *Motor* fica inerte, o comprimento *L* e a malha
de volumes dos outros separadores aplicam-se a todos os motores, e é produzida
a tabela-resumo dos volumes críticos.

### Introduzindo os dados à mão

Escolha **Introdução manual**. O cartão do ficheiro dá lugar à identificação
do motor e, por baixo, a toda a largura da página, aparece a tabela dos modos
do ciclo de ensaio, com uma linha por modo:

| campo | obrigatório | nota |
|---|---|---|
| Nome do motor | sim | Etiqueta usada nos resultados e nos ficheiros |
| Rotação nominal [rpm] | sim | Define o limite MARPOL em g/kWh |
| Potência nominal [kW] | não | Só entra no relatório |
| Carga [%] | sim | Carga de travão do modo |
| Peso [%] | sim | Peso no ciclo; só a razão entre pesos conta |
| Potência [kW] | sim | Potência de travão do modo |
| T entrada [°C] | sim | Temperatura à entrada do SCR |
| NO entrada [ppm] | sim | Engine-out. **O NO à saída não se introduz: é o que o modelo calcula.** |
| SFOC [g/kWh] + λ | ver nota | Dão o caudal de escape |
| Caudal esc. [kg/s] | ver nota | Alternativa ao par SFOC + λ |

**Caudal de escape**: cada modo precisa de *SFOC e λ*, **ou** do *Caudal esc.*
O caudal só é usado diretamente se estiver preenchido em **todos** os modos;
caso contrário, é calculado do combustível e do excesso de ar. Se faltarem os
dois, a aplicação diz em que modo.

Botões abaixo da tabela:

| botão | faz |
|---|---|
| **+ Adicionar modo** / **− Remover último** | Ajustam o número de linhas |
| **Limpar tabela** | Esvazia tudo |
| **Calcular caudal de escape** | Preenche a coluna «Caudal esc.» a partir do SFOC, do λ e do combustível — e mostra no *Registo* o caudal de combustível, o de ar e o de escape de cada modo (ver §6, «Caudal de escape») |
| **Copiar do ficheiro CSV** | Traz os dados do motor escolhido no modo CSV, para os editar à mão |

Linhas completamente em branco são ignoradas, portanto pode deixar linhas a mais.

Em introdução manual, o **comprimento L é obrigatório** no separador
**2 · Geometria** (não há ficheiro de onde o ler).

O cálculo demora tipicamente **4 a 5 segundos por motor**. A janela não
bloqueia: o botão fica desativado, a barra de estado mostra o tempo decorrido e
o *Registo* vai enchendo.

---

## 6. Os campos, um a um

Em cada tabela, a coluna «omissão» é o valor com que a aplicação abre e a
coluna «aceita» é o intervalo que o formulário valida. Um valor fora do
intervalo, ou não numérico, é recusado com uma mensagem que identifica o campo.

### 1 · Dados do motor

| campo | o que é | omissão | aceita |
|---|---|---|---|
| Origem dos dados | Ficheiro CSV ou introdução manual | Ficheiro CSV | — |
| Ficheiro (CSV) | Uma linha por modo do ciclo e por motor (§12) | — | Ficheiro existente |
| Motor | Etiqueta na coluna `Engine` do ficheiro | O primeiro do ficheiro | Da lista |
| Correr todos os motores do ficheiro | Corre todos e produz a tabela-resumo | Desligado | — |
| Nome do motor | Etiqueta do motor introduzido à mão | `DG1` | Texto |
| Rotação nominal | Rotação nominal do motor; define o limite MARPOL | 513 rpm | ≥ 1 |
| Potência nominal | Só entra no relatório | Em branco | ≥ 0, ou em branco |
| Combustível | Define o AFR estequiométrico | HFO | HFO, MDO, MGO, LSFO |
| Pressão | Pressão de operação no reator | 101325 Pa | ≥ 1 |
| Limite MARPOL | Tier de referência | III | III, II, I |
| Lei de potência em toda a gama | Reproduz o `9·n^-0.2` do MATLAB, sem patamares | Desligado | — |

A tabela dos modos (introdução manual) está descrita na §5. O ficheiro CSV tem
de trazer, por modo: carga, peso do modo no ciclo, potência de travão,
temperatura à entrada, NO à entrada, SFOC e λ, além da rotação e da potência
nominais do motor. As colunas de geometria são **opcionais**: um ficheiro só
com condições de operação é válido, e o comprimento indica-se no separador da
Geometria. A especificação completa está na §12.

Combustível, pressão e limite MARPOL aplicam-se seja qual for a origem dos
dados.

#### Combustíveis

Composição elementar (frações mássicas) e AFR estequiométrico resultante:

| combustível | C | H | S | AFR estequiométrico [kg ar / kg comb.] |
|---|---|---|---|---|
| HFO | 0.8490 | 0.1050 | 0.0400 | 13.548 |
| MDO | 0.8550 | 0.1250 | 0.0150 | 14.195 |
| MGO | 0.8570 | 0.1300 | 0.0090 | 14.364 |
| LSFO | 0.8600 | 0.1150 | 0.0050 | 13.867 |

Um combustível com outra composição só se define pela biblioteca
(`FuelComposition`, §16).

#### Limite MARPOL

O limite de NOx [g/kWh] sai da rotação nominal `n` [rpm] (MARPOL Anexo VI,
Regra 13):

| Tier | n < 130 | 130 ≤ n < 2000 | n ≥ 2000 |
|---|---|---|---|
| I | 17.0 | `45·n^-0.20` | 9.8 |
| II | 14.4 | `44·n^-0.23` | 7.7 |
| III | 3.4 | `9·n^-0.20` | 2.0 |

A 513 rpm o limite Tier III é 2.5836 g/kWh. Com **«Lei de potência em toda a
gama»** ligado, a lei do meio aplica-se a qualquer rotação, como no MATLAB; as
duas formas coincidem entre 130 e 2000 rpm.

#### Caudal de escape

Não é um input direto (embora possa sê-lo): sai do consumo e do excesso de ar,
pelo mesmo cálculo do `get_mass_dot_v3.m`:

```
m_fuel = SFOC[g/kWh] · P[kW] / 3.6e6                      [kg/s]
m_exh  = m_fuel · (1 + AFR_estequiométrico · λ)           [kg/s]
```

O AFR estequiométrico vem do balanço elementar do combustível
(C + O₂, 4H + O₂, S + O₂), pelo que muda com o combustível escolhido — 13.548
kg ar/kg para HFO. A premissa por trás da segunda linha é que **todo o ar
admitido sai no escape**.

O botão **«Calcular caudal de escape»** (separador 1, introdução manual) mostra
os caudais no *Registo* e preenche a coluna, para os poder conferir em vez de os
aceitar às cegas.

> **Cuidado com colunas de consumo tabelado.** No dataset de exemplo, a coluna
> `Fuel_Consumption_[kgh]` é exatamente **1.1 ×** `SFOC · P` — traz uma margem
> de 10 %. A aplicação ignora-a e recalcula, como o MATLAB fazia: usá-la daria
> caudais 10 % altos e, com eles, um reator sobredimensionado.

### 2 · Geometria do monolito

| campo | o que é | omissão | aceita |
|---|---|---|---|
| Comparar vários pares CPSI / parede | Liga o varrimento de substratos (ver abaixo) | Desligado | — |
| Densidade celular | CPSI [cél/in²]. `passo = 1 in / √CPSI`. **Escolha de projeto**, não vem do ficheiro | 46 cél/in² | ≥ 0.1 |
| Espessura de parede | Espessura total [m]. A semi-espessura governa a difusão intraporo | 0.00043 m | ≥ 0 |
| Comprimento L | Fica **fixo** no varrimento; é a área que varia (`A = V/L`). Prefixado a partir do ficheiro, se este o trouxer | 1.2 m | > 0 |

O **fouling** está no separador da Cinética, junto do envelhecimento: é uma
condição do catalisador, não da geometria escolhida.

Da densidade celular e da parede saem o passo de célula, o diâmetro hidráulico
`dh = passo − parede` e a fração de área aberta `ε = (dh/passo)²` (§11). Se a
parede for grossa de mais para o CPSI escolhido, o canal fecha (`dh ≤ 0`) e a
aplicação recusa correr, dizendo-o.

#### Comparar vários pares CPSI / parede

Ligando **«Comparar vários pares CPSI / parede»**, os dois campos únicos dão
lugar a uma tabela: uma linha por par, o CPSI em cél/in² e a parede **em
milímetros**. A aplicação corre o varrimento em volume completo uma vez por
par e põe os volumes críticos lado a lado. A tabela abre com três pares:
46 / 0.43, 64 / 0.35 e 100 / 0.25.

O tempo de cálculo é multiplicado pelo número de pares — cinco pares são cinco
varrimentos, uns 20 a 25 segundos ao todo.

Canais mais estreitos mexem no reator em dois sentidos opostos: dão mais área
geométrica por unidade de volume e melhor transferência de massa, mas também
menos área aberta (logo maior velocidade e menor tempo de residência), e uma
parede mais fina significa menos massa catalítica por canal. É por isso que
vale a pena comparar em vez de arbitrar.

Um par impossível no meio dos outros — parede que consome todo o passo — **não
pára o cálculo**: fica registado com o motivo e os restantes seguem. Só é erro
se nenhum dos pares for possível.

### 3 · Alvos de emissão

Dois níveis. As frações são do limite MARPOL calculado para a rotação do motor.

| campo | o que é | omissão | aceita |
|---|---|---|---|
| NOx do ciclo (fração) | NOx do ciclo ponderado ≤ fração × limite | 0.60 | 0 a 1 |
| NOx por modo (fração) | NOx de cada modo ≤ fração × limite | 0.80 | 0 a 1 |
| Slip do ciclo | NH₃ slip do ciclo ponderado ≤ valor | 10 ppm | ≥ 0 |
| Slip por modo | NH₃ slip de cada modo ≤ valor | 20 ppm | ≥ 0 |

Com os valores por omissão:

| | por modo | ciclo ponderado |
|---|---|---|
| NOx | ≤ 80 % do limite | ≤ 60 % do limite |
| NH₃ slip | ≤ 20 ppm | ≤ 10 ppm |

Um volume só é admissível se cumprir os **quatro** alvos ao mesmo tempo.

### 4 · Cinética e transporte

Os valores por omissão são os da Tabela 2 de Tronconi et al. (1998),
catalisador 1, e não precisam de ser mexidos para o caso de referência.
**Energias de ativação em cal/mol.** Os pré-exponenciais estão nas unidades
dessa tabela.

| campo | o que é | omissão | aceita |
|---|---|---|---|
| k0 adsorção NH₃ | Pré-exponencial de adsorção de NH₃ | 8.5e6 | ≥ 0 |
| E adsorção NH₃ | Energia de ativação de adsorção | 9000 cal/mol | Qualquer |
| k0 redução NO | Pré-exponencial de redução de NO | 2.5e10 | ≥ 0 |
| E redução NO | Energia de ativação de redução de NO | 18600 cal/mol | Qualquer |
| k0 dessorção NH₃ | Pré-exponencial de dessorção de NH₃ | 8e8 | ≥ 0 |
| E dessorção (θ=0) | Energia de ativação de dessorção a cobertura nula | 26000 cal/mol | Qualquer |
| β (Temkin) | Dependência da energia de dessorção com a cobertura | 0.32 | Qualquer |
| Envelhecimento KK0 | Atividade relativa do catalisador; entra ao quadrado na redução de NO | 0.80 | > 0 |
| Fouling | Fração da área frontal perdida por obstrução dos canais | 0.15 | 0 a 0.99 |
| Difusividade efetiva | Difusividade intraporo, na parede | 1e-6 m²/s | ≥ 0 |
| Difusividade molecular | Difusividade no gás; entra na transferência de massa | 8e-5 m²/s | ≥ 0 |
| Massa molar do gás | Massa molar média do escape; dá a densidade e a velocidade | 0.02896 kg/mol | > 0 |
| f (fronteira ativa) | Critério **numérico** da fronteira `x*` da zona ativa da parede; não é um parâmetro cinético | 0.01 | ≥ 0 |

Os dois campos com mais impacto prático estão em **Transporte e estado do
catalisador**:

- **Envelhecimento KK0** — entra ao quadrado no pré-exponencial de redução de
  NO (`k0NO_efetivo = k0NO · KK0²`). `1` é catalisador novo, `0.8` um fim de
  vida típico.
- **Fouling** — fração da área frontal perdida por obstrução dos canais: a
  área efetiva passa a `A·(1−fouling)`.

São eles que separam um reator que cumpre no primeiro dia de um que cumpre ao
fim da vida. Dimensionar com `KK0 = 1` e `fouling = 0` dá o menor reator
possível — e um que deixa de cumprir mal o catalisador envelhece ou suja.

> A temperatura fixa, a conversão só «vê» as constantes agrupadas. Mexer em
> `k0` ou em `E` isoladamente para o mesmo ponto é redundante — use os
> multiplicadores de calibração para isso.

### 5 · Calibração (multiplicadores)

Multiplicam a cinética já calculada. Tudo a `1` reproduz exatamente a cinética
de referência. Servem para ajustar o modelo a um catalisador concreto sem tocar
nos parâmetros físicos.

| campo | multiplica | omissão | aceita |
|---|---|---|---|
| × kNO | A constante de redução de NO | 1 | ≥ 0 |
| × kads | A constante de adsorção de NH₃ | 1 | ≥ 0 |
| × Deff | A difusividade efetiva intraporo | 1 | ≥ 0 |
| × k0d | O pré-exponencial de dessorção de NH₃ | 1 | ≥ 0 |

### 6 · Varrimento em volume

| campo | efeito | omissão | aceita |
|---|---|---|---|
| Volume máximo | Maior volume a considerar; o varrimento começa aqui e desce | 3.50 m³ | > 0 |
| Decremento de volume | Passo descendente | 0.20 m³ | > 0 |
| Volume mínimo | Piso do varrimento; tem de ser menor que o máximo | 0.20 m³ | > 0 |
| Refinar por bisseção em V | Afina o volume crítico para além da resolução do passo | Ligado | — |
| Tolerância do refinamento | Quando parar de bissetar | 0.02 m³ | > 0 |

Com o refinamento desligado, o volume crítico fica com a resolução do
decremento: é o último volume da malha que cumpre.

### 7 · Loop de α

| campo | efeito | omissão | aceita |
|---|---|---|---|
| α de arranque | Valor inicial em todos os modos | 0.80 | ≥ 0 |
| Passo de α | Ajuste multiplicativo (0.02 = 2 %) | 0.02 | > 0 |
| α mínimo | Limite inferior do doseamento; tem de ser menor que o máximo | 0.30 | ≥ 0 |
| α máximo | Limite superior do doseamento | 1.20 | ≥ 0 |
| Máximo de iterações | Guarda contra não-convergência | 200 | Inteiro ≥ 1 |
| Tolerância de bracketing | Quando o intervalo `[lo, hi]` conta como colapsado | 0.0001 | ≥ 0 |
| Minimizar α após cumprir os alvos | Ver a nota abaixo | Desligado | — |

**Sobre «Minimizar α»**: enquanto o reator tem folga, o α de arranque já cumpre
tudo e o loop fecha à primeira iteração — o caudal de ureia fica igual ao de
arranque e é pouco informativo. Com esta opção ligada, o α desce por modo até
ao **mínimo admissível**, dando o consumo real de ureia. **Não altera o volume
crítico**, só o ponto de operação reportado. Ligue-a se o objetivo for reportar
consumo de ureia; deixe-a desligada para reproduzir o comportamento do MATLAB.

### 8 · Numérico e saída

| campo | efeito | omissão | aceita |
|---|---|---|---|
| Nós axiais | Malha do solver. 120 é o valor validado; alterar muda o resultado ao nível da discretização | 120 | Inteiro ≥ 10 |
| Pasta de resultados | Onde gravar. Em branco = não grava | Em branco | Pasta |
| Gravar CSV | Escreve as tabelas em disco (§13) | Ligado | — |
| Gravar figuras (PNG) | Escreve as figuras em disco (§13); precisa do `matplotlib` | Ligado | — |

### Parâmetros que não estão no formulário

Estes valores existem na biblioteca e no ficheiro de cenário (§14), mas a
interface **usa sempre os valores por omissão**: para os alterar é preciso usar
a biblioteca (§16).

| parâmetro | valor | onde entra |
|---|---|---|
| Fração mássica de ureia na solução | 0.40 | Consumo de ureia [L/h] |
| Densidade da solução de ureia | 1109 kg/m³ | Consumo de ureia |
| Massa molar da ureia | 0.06006 kg/mol | Consumo de ureia |
| Massa molar do escape (doseamento) | 0.02896 kg/mol | Consumo de ureia |
| NH₃ por mole de ureia | 2 | Consumo de ureia |
| Massa molar do escape (NOx específico) | 29.0 g/mol | Conversão de ppm em g/kWh |
| Massa molar do NOx (como NO₂) | 46.01 g/mol | Conversão de ppm em g/kWh |
| Constante dos gases | 1.987 cal/(mol·K) e 8.314 J/(mol·K) | Arrhenius e densidade do gás |
| Tolerâncias do Newton por nó | Ver `SolverOptions` | Solver |
| Nomes das colunas e formato do CSV | Ver §12 | Leitura do ficheiro |

---

## 7. Ler os resultados

### No painel de resultados

| separador | mostra |
|---|---|
| **Resumo** | O **volume crítico** em destaque, com a área frontal e o comprimento; ao lado, o NOx e o slip do ciclo com o respetivo alvo, a conversão e o consumo de ureia — tudo avaliado nesse volume. Por baixo, o α de cada modo. |
| **Modos** | Uma linha por modo do ciclo, no volume crítico: α, X_NO, NO [g/kWh], slip, ureia, τ e a situação do modo. Os alvos por modo estão na legenda da tabela. |
| **Varrimento** | Uma linha por volume avaliado, do maior para o menor. O volume crítico está realçado; os volumes inadmissíveis estão a vermelho. |
| **Gráfico** | NOx do ciclo, slip do ciclo (escala logarítmica), α por modo e ureia, contra o volume, com os alvos e o volume crítico marcados. Redesenha-se à medida do painel. Precisa do `matplotlib`. |
| **Registo** | A consola: o texto integral do cálculo (ver abaixo), com os botões **Gravar registo…** e **Limpar**. |

Com **vários resultados** — «todos os motores», ou vários pares CPSI / parede —
o *Resumo* ganha uma tabela que os põe lado a lado. **Escolher uma linha dessa
tabela** muda o resultado mostrado nos mosaicos e nos separadores *Modos*,
*Varrimento* e *Gráfico*. Na comparação de substratos, o par com o menor volume
crítico de cada motor fica assinalado com ★ e é o que aparece escolhido à
partida; os pares impossíveis ficam a vermelho, com o motivo na coluna
«Observação».

Se **não houver volume admissível**, o mosaico do volume crítico fica a
vermelho com «Sem solução» e o que fazer (ver §9), e o separador *Modos* mostra
o maior volume avaliado — é aí que se vê qual o modo em situação 4.

Quando chega texto novo ao *Registo* e este não está à vista, o separador fica
marcado com um ponto («Registo •»).

### No registo (consola)

Uma linha por volume avaliado:

```
   V[m3]    A[m2]    sit NOx_c[g/kWh] slip_c[ppm]   XNO_c[%]  urea[L/h]   n_it
   1.640    1.367      1       1.5331       6.176      79.49      35.32      1
   1.440    1.200      4       1.6801       9.852      77.57      34.15      5
```

A coluna **`sit`** é a situação em que o loop de α fechou:

| sit | significado |
|---|---|
| **1** | Alvos cumpridos → volume **admissível** |
| **4** | Janela de α vazia → volume **inadmissível**; foi aqui que o varrimento parou |
| 0 | Não convergiu dentro do máximo de iterações (aumente o máximo) |

As situações 2 (falta conversão → subir α) e 3 (slip excessivo → descer α) são
intermédias: existem dentro do loop mas nunca são o estado final.

No fim, o resumo — tudo avaliado **no volume crítico**, que é o reator a
instalar:

```
  DG1: VOLUME CRÍTICO = 1.540 m³ (A = 1.283 m², L = 1.20 m)
      nesse volume: NOx = 1.5417 g/kWh · slip = 7.753 ppm · X_NO = 79.42 % · ureia = 34.91 L/h
      α por modo: 11%=0.816  24%=0.816  50%=0.816  73%=0.758
```

Repare que, no volume crítico, o NOx e o slip ficam **encostados aos alvos** —
é essa a definição de crítico. Se quiser margem, instale um volume maior: o
varrimento mostra, linha a linha, quanto é que cada metro cúbico extra compra.

### Nos ficheiros

Com pasta de resultados indicada, a aplicação escreve os CSV e as figuras
descritos, coluna a coluna, na §13.

---

## 8. Guardar e repetir um estudo

Na barra lateral, por baixo dos separadores (grupo **Cenário**):

- **Gravar cenário…** (`Ctrl+S`) escreve um `.json` com **todos** os inputs do
  formulário. Em introdução manual, os dados do motor vão **dentro** do
  ficheiro, que passa a correr sozinho, sem CSV nenhum.
- **Carregar cenário…** (`Ctrl+O`) repõe o formulário a partir desse `.json`.
- **Repor omissões** volta aos valores por omissão sem perder o ficheiro nem o
  motor escolhidos. O «Volume máximo» e o «Comprimento L» mantêm o valor que
  tiverem.

No separador *Registo* do painel de resultados:

- **Gravar registo…** guarda o conteúdo da consola num `.txt`.
- **Limpar** esvazia a consola.

A estrutura do `.json` está na §14. O mesmo ficheiro corre sem interface:

```python
import json
from tvscr import RunScenario

scn = RunScenario.from_dict(json.load(open("cenario.json", encoding="utf-8")))
batch = scn.run()
print(batch.summary)
```

---

## 9. Quando não há volume admissível

Se o *Resumo* mostrar **«Sem solução»** (e o *Registo* disser *«nenhum volume
admissível no intervalo varrido»*), a primeira geometria avaliada já falhou.
Motivos habituais, por ordem de probabilidade:

1. **Volume máximo pequeno de mais** — aumente o «Volume máximo» no separador
   do Varrimento. É o motivo mais comum.
2. **Cenário demasiado severo** — fouling e KK0 acumulados. Experimente
   fouling `0` e KK0 `1` para ver se cumpre com catalisador novo e limpo.
3. **Alvos apertados de mais** — os 60 %/10 ppm do ciclo são mais exigentes que
   o limite regulamentar cheio. Suba as frações para ver a margem real.
4. **Janela de α estreita** — alargue `α mínimo`/`α máximo`, ou reduza o passo
   de α.

O separador *Modos* (e o ficheiro `_modos.csv`) diz qual o modo em situação 4 e
porquê (NOx acima do alvo *e* slip acima do alvo ao mesmo α).

---

## 10. Erros comuns

| mensagem | causa | o que fazer |
|---|---|---|
| «Escolha o ficheiro de inputs (CSV)» | Campo vazio | Carregue em «Procurar…» |
| «Não consegui ler o ficheiro» | Separador ou decimal diferentes | O leitor espera `;` e vírgula decimal (§12). Para outro formato, use a biblioteca com `DatasetFormat` |
| «Coluna "..." não existe no ficheiro» | Cabeçalhos com outros nomes, ou coluna obrigatória em falta | Renomeie as colunas conforme a §12, ou use `ColumnMap` na biblioteca |
| «Geometria da célula inválida» | Parede grossa de mais para o CPSI | Baixe a espessura ou o CPSI |
| «"α mínimo" tem de ser menor que "α máximo"» | Limites trocados | Corrija |
| «"Volume mínimo" tem de ser menor que o "Volume máximo"» | Limites trocados | Corrija |
| «Modo N: falta o caudal de escape» | Na tabela manual, o modo não tem SFOC + λ nem caudal | Preencha um dos dois |
| Campo a **vermelho claro** | Valor não numérico ou fora dos limites | A aplicação abre o separador desse campo e põe lá o cursor; o texto do erro diz qual é o campo e o limite |
| «Nenhuma linha do motor "X"» | Etiqueta não existe no ficheiro | Escolha da lista |
| «Sem pasta de resultados» | CSV ou figuras ligados, sem pasta | Continue (nada é gravado) ou indique a pasta no separador 8 |
| «matplotlib não disponível: figuras ignoradas» | Falta a biblioteca | `pip install matplotlib`; o cálculo não é afetado |
| «Cenário inválido … campos desconhecidos» | O `.json` foi gravado por uma versão antiga, ou editado com um nome errado | Retire o campo indicado na mensagem, ou grave o cenário de novo |
| «Documentação não encontrada» | O `INSTRUCOES.md` não está na pasta do projeto | Reponha o ficheiro ao lado do `app.py` |

---

## 11. Modelo e método de cálculo

Esta secção resume o que o programa calcula e como. A dedução e a validação do
modelo estão na dissertação (§20).

### 11.1 Cadeia de cálculo

1. **Condições de operação** de cada modo do ciclo: carga, peso, potência,
   temperatura e NO à entrada, e caudal de escape (dado, ou calculado de SFOC,
   λ e combustível).
2. **Limite de NOx** em g/kWh, da rotação nominal e do Tier (§6).
3. Para uma geometria (volume `V`, comprimento `L`, substrato) e um α por
   modo, o **solver 1-D** dá o NO e o NH₃ à saída de cada modo.
4. O **ciclo** converte o NO à saída em NOx específico e pondera os modos.
5. O **loop de α** procura, para essa geometria, o α por modo que cumpre os
   quatro alvos — ou conclui que não existe.
6. O **varrimento em volume** repete os passos 3 a 5 do maior volume para o
   menor, até ao primeiro inadmissível, e refina o **volume crítico** por
   bisseção.

### 11.2 Geometria e escoamento

Monolito de canais quadrados, definido pelo CPSI e pela espessura de parede `w`:

```
passo = 25.4 mm / √CPSI                 passo de célula
dh    = passo − w                       diâmetro hidráulico do canal
ε     = (dh / passo)²                   fração de área frontal aberta
s     = w / 2                           semi-espessura da parede
A_ef  = A · (1 − fouling)               área frontal efetiva
```

Para o caso de referência (46 cél/in², 0.43 mm): passo = 3.745 mm,
dh = 3.315 mm, ε = 0.784.

Em cada modo, com o gás tratado como ideal à temperatura `T` e à pressão `P`:

```
ρ   = P · M / (R · T)                   densidade do gás         [kg/m³]
Q   = m_exh / ρ                         caudal volúmico          [m³/s]
v   = Q / (A_ef · ε)                    velocidade nos canais    [m/s]
τ   = L / v                             tempo de residência      [s]
AV  = v · dh / (4 · L)                  velocidade de área       [m/s]
```

### 11.3 Cinética

Mecanismo de Eley-Rideal: o NH₃ adsorve na superfície do catalisador e reage
com o NO da fase gasosa. Três constantes, todas de Arrhenius, com
`R = 1.987 cal/(mol·K)`:

```
kads = k0ads · exp(−Eads / (R·T))                    adsorção de NH₃
kNO  = k0NO · KK0² · exp(−ENO / (R·T))               redução de NO
kd   = k0d · exp(−E0d · (1 − β·θ) / (R·T))           dessorção de NH₃ (Temkin)
```

`θ` é a cobertura de NH₃ na superfície. O envelhecimento `KK0` entra ao
quadrado em `kNO`. Os multiplicadores de calibração (§6, separador 5) aplicam-se
a `kNO`, `kads`, `Deff` e `k0d`.

### 11.4 Solver 1-D

Modelo heterogéneo unidimensional de Tronconi, Cavanna e Forzatti (1998), na
variante **estacionária** orientada a dimensionamento (geometria → conversão).
Marcha espacial ao longo do canal sobre `N` nós (120 por omissão). Em cada nó
resolve-se um sistema 2×2 nas incógnitas `C_NO` e `θ`:

- **Balanço de NO na fase gasosa**: convecção ao longo do canal igual à
  transferência de massa do gás para a parede.
- **Balanço da cobertura de NH₃**: a taxa efetiva de NH₃ iguala a taxa efetiva
  de NO.

A transferência de massa gás-parede usa a correlação de Sherwood local para
canal quadrado em desenvolvimento, e o perfil de concentração **dentro da
parede** é analítico (módulo de Thiele), com a fronteira `x*` da zona ativa:

```
Sh(z*) = 2.977 + 8.827 · (1000·z*)^−0.545 · exp(−48.2·z*)
z*     = z · Dmol / (v · dh²)
kmat   = Sh · Dmol / dh
```

O doseamento entra pelo **α**, a razão molar NH₃/NO à entrada do reator. A
estequiometria 1:1 da reação torna `C_NH3 − C_NO = (α − 1) · C_NO,entrada`
constante ao longo do canal, o que reduz o problema a duas incógnitas.

O sistema é resolvido por Newton amortecido com projeção nos limites físicos.
Cada ponto traz um diagnóstico de validade numérica (resíduo e restrições
ativas), propagado até ao resultado do ciclo.

### 11.5 Grandezas de saída

Por modo:

```
X_NO  = 100 · (C_NO,entrada − C_NO,saída) / C_NO,entrada         conversão  [%]
slip  = C_NH3,saída                                              [ppm]
NO    = NO_saída[ppm] · 3600 · m_exh · M_NOx / (P · M_esc · 1000) [g/kWh]
```

com `m_exh` em kg/s, `P` a potência de travão em kW, `M_NOx = 46.01 g/mol` e
`M_esc = 29.0 g/mol`. A massa molar é a do **NO₂**: o NOx específico exprime-se
como NO₂ equivalente, pela convenção do Código Técnico NOx da MARPOL, embora a
espécie que o modelo resolve seja o NO.

No ciclo, cada grandeza é a média ponderada pelos pesos `w` dos modos:

```
G_ciclo = Σ (w_i · G_i) / Σ w_i        G = NO [g/kWh], slip, X_NO, ureia
```

Só a razão entre pesos conta; não têm de somar 100.

O **consumo de solução de ureia** de cada modo sai de α, admitindo que cada
mole de ureia liberta duas de NH₃:

```
n_esc   = m_exh / M_esc                 caudal molar de escape   [mol/s]
n_NH3   = α · NO_entrada · 1e-6 · n_esc                          [mol/s]
n_ureia = n_NH3 / 2                                              [mol/s]
m_sol   = n_ureia · M_ureia / w_ureia   caudal de solução        [kg/s]
V_sol   = m_sol / ρ_sol                 convertido para L/h
```

com solução a 40 % em massa e densidade de 1109 kg/m³ (§6).

### 11.6 Loop de α

Com α congelado, a pergunta seria *«o que acontece a este reator se o encolher
sem mexer no doseamento»*. Com α adaptativo é *«qual é o menor reator viável»*
— porque um reator menor seria, na prática, operado com outro doseamento.

Em cada volume, o loop procura o vetor de α (um por modo) que cumpre
simultaneamente o NOx e o slip, nos dois níveis (por modo e no ciclo).
Classifica cada avaliação por dois pares de eventos — A: NOx abaixo do alvo ·
B: acima · C: slip abaixo do alvo · D: acima:

| situação | eventos | ação |
|---|---|---|
| 1 | A + C | Alvos cumpridos → fecha o loop |
| 2 | B + C | Falta conversão → aumentar α |
| 3 | A + D | Slip excessivo → reduzir α |
| 4 | B + D | Janela de α vazia → **volume inadmissível** |

Duas decisões de método:

- **A situação 4 é avaliada por modo.** Cada modo tem o seu α; ter um modo em
  situação 2 e outro em situação 3 não é inviabilidade — cada um ajusta o seu.
- **Bracketing e bisseção geométrica.** O α sobe ou desce pelo «Passo de α»
  (multiplicativo) até haver um limite de cada lado; a partir daí bisseta. Um
  passo puro podia oscilar entre as situações 2 e 3 sem nunca fechar se a
  janela viável fosse mais estreita que o passo.

O loop fecha também se o intervalo colapsar («Tolerância de bracketing»), se α
saturar em «α mínimo» ou «α máximo», ou se atingir o «Máximo de iterações»
(situação 0).

### 11.7 Varrimento em volume

O comprimento `L` fica fixo e a área frontal sai do volume: `A = V / L`. O
varrimento começa no «Volume máximo» e desce pelo «Decremento de volume» até
ao primeiro volume inadmissível ou ao «Volume mínimo». Com o refinamento
ligado, bisseta depois em `V` entre o último volume admissível e o primeiro
que falhou, até a diferença ser menor que a «Tolerância do refinamento».

O **volume crítico** é o menor volume admissível encontrado. Se o maior volume
já for inadmissível, não há solução no intervalo (§9).

---

## 12. Ficheiro de inputs (CSV)

Texto separado por **ponto e vírgula**, com **vírgula decimal** e codificação
UTF-8 (com ou sem BOM) — o formato que o Excel em português grava em «CSV
(separado por ponto e vírgula)». A primeira linha são os cabeçalhos. Cada linha
seguinte é **um modo de um motor**; os motores distinguem-se pela coluna
`Engine`, e o ficheiro pode ter qualquer número de motores e de modos.

| coluna | unidade | obrigatória | conteúdo |
|---|---|---|---|
| `Engine` | — | sim | Etiqueta do motor (`DG1`, …) |
| `Engine_Speed_[rpm]` | rpm | sim | Rotação nominal; igual em todas as linhas do motor |
| `Rated_Power_[kW]` | kW | sim | Potência nominal; igual em todas as linhas do motor |
| `LoadTest` | fração | sim | Carga do modo, **de 0 a 1** (0.75 = 75 %) |
| `Weight` | % | sim | Peso do modo no ciclo |
| `Engine_Power_[kW]` | kW | sim | Potência de travão no modo |
| `Lamda` | — | sim | Excesso de ar λ no modo |
| `SFOC_[g/kWh]` | g/kWh | sim | Consumo específico no modo |
| `T_in_[C]` | °C | sim | Temperatura dos gases à entrada do SCR |
| `NO_in_[ppm]` | ppm | sim | NO à entrada do SCR |
| `NO_out_[ppm]` | ppm | a coluna, sim | NO medido à saída. **Não entra no dimensionamento**; só serve à calibração de α pela biblioteca. Pode ficar vazia, mas o cabeçalho tem de existir |
| `Implemented_Lenght_[m]` | m | não | Comprimento do monolito instalado; se existir, prefixa o «Comprimento L» |
| `Implemented_Volume_[m3]` | m³ | não | Volume instalado; só para conferir com área × comprimento |
| `Implemented_Area_[m2]` | m² | não | Área frontal instalada; só para conferir |
| `Fuel_Consumption_[kgh]` | kg/h | não | Ignorada: o consumo é recalculado de SFOC × potência (§6) |

Os nomes das colunas têm de coincidir com os da tabela (maiúsculas e espaços
nas pontas são tolerados), incluindo as grafias `Lamda` e `Lenght` do ficheiro
original. Outras colunas que o ficheiro traga são ignoradas.

Exemplo, com um motor de quatro modos (valores ilustrativos):

```
Engine;Engine_Speed_[rpm];Rated_Power_[kW];LoadTest;Weight;Engine_Power_[kW];Lamda;SFOC_[g/kWh];T_in_[C];NO_in_[ppm];NO_out_[ppm]
DG1;513;5760;0,11;10,5;637;3,42;229,5;341,6;530;
DG1;513;5760;0,24;31,6;1382;2,90;215,0;380,0;900;
DG1;513;5760;0,50;31,6;2895;2,37;208,0;410,4;1160;
DG1;513;5760;0,73;26,3;4213;2,18;197,0;421,5;1228;
```

Um ficheiro com outro separador, ponto decimal, temperatura em kelvin, carga
em percentagem ou outros nomes de coluna lê-se pela biblioteca, com
`DatasetFormat` e `ColumnMap` (§16); a interface usa sempre o formato acima.

---

## 13. Ficheiros de saída

Só são escritos se houver «Pasta de resultados» (separador 8). Os nomes de
ficheiro e de coluna são os dos scripts MATLAB, para comparação direta. Os CSV
de saída usam vírgula como separador e ponto decimal.

### Um motor, ou todos os motores

Em `<pasta>/<motor>/`:

**`volume_sweep_<motor>.csv`** — uma linha por volume avaliado. É aqui que se
lê a margem que cada volume acima do crítico compra.

| coluna | unidade | conteúdo |
|---|---|---|
| `V_m3` | m³ | Volume avaliado |
| `A_m2` | m² | Área frontal, `V / L` |
| `situacao` | — | Situação em que o loop de α fechou (§7) |
| `admissivel` | 0 / 1 | 1 se o volume cumpre os alvos |
| `NOx_ciclo_gkWh` | g/kWh | NOx específico do ciclo ponderado |
| `slip_ciclo_ppm` | ppm | NH₃ slip do ciclo ponderado |
| `XNO_ciclo_perc` | % | Conversão de NO do ciclo ponderado |
| `urea_ciclo_Lh` | L/h | Consumo de solução de ureia do ciclo ponderado |
| `n_iter` | — | Iterações do loop de α |
| `fase` | — | 1 = varrimento, 2 = refinamento por bisseção |

**`volume_sweep_<motor>_modos.csv`** — uma linha por (volume, modo). É aqui que
se vê **qual o modo que fecha o varrimento** — tipicamente o de carga mais
alta, onde o slip cresce primeiro.

| coluna | unidade | conteúdo |
|---|---|---|
| `V_m3` | m³ | Volume avaliado |
| `Load_perc` | % | Carga do modo |
| `Weight_perc` | % | Peso do modo no ciclo |
| `alpha` | — | α do modo nesse volume |
| `XNO_perc` | % | Conversão de NO |
| `NO_gkWh` | g/kWh | NOx específico à saída |
| `slip_ppm` | ppm | NH₃ slip |
| `urea_Lh` | L/h | Consumo de solução de ureia |
| `tau_s` | s | Tempo de residência |
| `AV_Nmh` | ver nota | Velocidade de área |
| `eta` | — | Eficácia média do NO na parede (Thiele) |
| `situacao_modo` | — | Situação final do modo |

**`volume_sweep_<motor>.png`** — painel 2×2: NOx do ciclo, slip (escala
logarítmica), α por modo e consumo de ureia, todos contra o volume.

Com «todos os motores», junta-se na raiz da pasta
**`resumo_volumes_criticos.csv`** (e `.png`, um gráfico de barras):

| coluna | unidade | conteúdo |
|---|---|---|
| `Engine` | — | Motor |
| `L_m` | m | Comprimento |
| `V_crit_m3` | m³ | Volume crítico |
| `A_crit_m2` | m² | Área frontal no volume crítico |
| `NOx_ciclo_gkWh`, `slip_ciclo_ppm`, `XNO_ciclo_perc`, `urea_ciclo_Lh` | — | Valores do ciclo no volume crítico |

### Comparação de substratos

Cada par tem a sua subpasta `<motor>_CPSI<n>_w<parede>mm/`, com os mesmos três
ficheiros. Na raiz fica **`resumo_substratos.csv`**, uma linha por (motor, par):

| coluna | unidade | conteúdo |
|---|---|---|
| `Engine` | — | Motor |
| `CPSI` | cél/in² | Densidade celular do par |
| `parede_mm` | mm | Espessura de parede do par |
| `dh_mm` | mm | Diâmetro hidráulico resultante |
| `eps_void` | — | Fração de área aberta resultante |
| `V_crit_m3`, `A_crit_m2` | m³, m² | Volume e área críticos |
| `NOx_ciclo_gkWh`, `slip_ciclo_ppm`, `XNO_ciclo_perc`, `urea_ciclo_Lh` | — | Valores do ciclo no volume crítico |
| `observacao` | — | Motivo, quando o par é impossível ou não tem volume admissível |

> **Nota sobre a coluna `AV_Nmh`**: é calculada como `AV · 3600 · 273.15`, tal
> como no MATLAB, o que não corresponde a uma normalização a 0 °C. Leia-a como
> indicador relativo entre pontos, não como um caudal em Nm³/h/m².

O *Registo* termina com a lista dos ficheiros gravados. Se um
`volume_sweep_*.csv` estiver aberto noutro programa quando a aplicação o tenta
gravar, fica por escrever e não aparece nessa lista: feche-o e volte a correr.

---

## 14. Ficheiro de cenário (.json)

O `.json` gravado por **Gravar cenário…** é o `RunScenario` da biblioteca,
escrito por extenso. Os campos de topo:

| campo | conteúdo |
|---|---|
| `dataset_path` | Caminho do CSV de inputs; `null` em introdução manual |
| `engines` | Lista de motores a correr; `null` = todos os do ficheiro |
| `inline_engines` | Motores introduzidos à mão, com os modos dentro (ver abaixo); `null` com CSV |
| `fuel`, `pressure_Pa`, `tier`, `tier_power_law_only` | Separador 1 |
| `substrate` | `cpsi` e `wall_thickness_m` — separador 2 |
| `substrates` | Lista de pares a comparar; `null` sem comparação |
| `length_m`, `frontal_area_m2` | Comprimento e área de referência (`Volume máximo / L`) |
| `targets` | Os quatro alvos — separador 3 |
| `kinetics` | Cinética, transporte e `aging_KK0` — separador 4 |
| `tuning` | Multiplicadores — separador 5 |
| `sweep` | Malha de volumes, refinamento e `fouling` — separadores 6 e 4 |
| `alpha_loop` | Loop de α — separador 7 |
| `solver` | `n_nodes` e tolerâncias do Newton — separador 8 |
| `urea`, `columns`, `dataset_format` | Solução de ureia e formato do CSV (§6, «Parâmetros que não estão no formulário») |
| `output_dir` | Pasta de resultados |

Cada motor de `inline_engines` tem `name`, `engine_speed_rpm`,
`rated_power_kW`, `length_m`, `frontal_area_m2` e a lista `modes`; cada modo
tem `load_pct`, `weight`, `power_kW`, `T_in_K` (em **kelvin**), `NO_in_ppm`,
`sfoc_g_per_kWh`, `lambda_` e `exhaust_mass_flow_kgs`.

Ao **carregar** um cenário, a interface lê os campos que têm lugar no
formulário. Os de `urea`, `columns`, `dataset_format` e as tolerâncias de
`solver` não têm: são ignorados ao carregar e voltam aos valores por omissão
quando se corre ou grava pela interface. Um `.json` editado à mão nesses campos
só produz efeito se for corrido pela biblioteca (§8).

Um `.json` com um campo que a biblioteca não conhece é recusado com uma
mensagem que diz qual é o campo — acontece com cenários gravados por versões
antigas do programa.

---

## 15. Reproduzir os resultados do MATLAB

Para obter exatamente os números dos scripts originais:

| campo | valor |
|---|---|
| Densidade celular | `46` |
| Espessura de parede | `0.00043` |
| Fouling | `0.15` |
| Envelhecimento KK0 | `0.80` |
| Lei de potência em toda a gama | **ligado** |
| Minimizar α | desligado |
| Alvos | 0.60 / 0.80 / 10 / 20 |
| α de arranque / passo | `0.80` / `0.02` |
| Volume máximo | `3.24` m³ (era 150 % do volume instalado do DG1) |
| Comprimento L | `1.2` m |
| Nós axiais | `120` |

Com estes valores, DG1 dá `V_crítico = 1.540 m³`, igual ao MATLAB até ao
arredondamento de máquina. A tabela de paridade dos cinco motores está no
[README](README.md).

---

## 16. Usar sem interface

A interface não calcula nada — só recolhe inputs e chama a biblioteca `tvscr`.
Tudo o que ela faz está disponível em Python:

```python
from tvscr import (EngineDataset, SubstrateGeometry, EmissionTargets,
                   VolumeSweepOptions, AlphaLoopOptions, volume_sweep)

ds   = EngineDataset.from_csv("Tabela_Inputs_Final.csv")
case = ds.build_case("DG1", substrate=SubstrateGeometry(cpsi=46,
                                                        wall_thickness_m=0.43e-3))
s = volume_sweep(case, EmissionTargets(),
                 VolumeSweepOptions(fouling=0.15, aging_KK0=0.80),
                 AlphaLoopOptions())
print(s.critical_volume_m3)
s.to_dataframe()        # uma linha por volume
s.modes_dataframe()     # uma linha por (volume, modo)
```

O que só a biblioteca permite:

| necessidade | objeto |
|---|---|
| CSV com outro separador, decimal, unidades ou nomes de coluna | `DatasetFormat`, `ColumnMap` |
| Combustível com outra composição | `FuelComposition` |
| Solução de ureia com outra concentração ou densidade | `UreaSolution` |
| Malha de volumes não uniforme | `VolumeSweepOptions(volumes_m3=[...])` |
| Um único ponto de operação, com perfis axiais | `solve_point` |
| Calibrar α contra NO medido à saída | `calibrate_alpha` |
| Tolerâncias do solver | `SolverOptions` |

Há exemplos completos em `examples/`:

| ficheiro | mostra |
|---|---|
| `01_ponto_unico.py` | Solver 1-D num ponto, todos os inputs explícitos |
| `02_varrimento_volume.py` | Varrimento de um motor, com CSV e figura |
| `03_todos_os_motores.py` | Todos os motores do ficheiro, resumo e cenário |
| `04_motor_novo_sem_ficheiro.py` | Motor novo com 5 modos, sem CSV; calibração de α |
| `05_varrimento_substratos.py` | Comparação de pares CPSI / espessura de parede |

---

## 17. Pressupostos e limitações

O resultado é tão bom quanto estes pressupostos forem verdadeiros para o caso
em estudo.

**Do modelo**

- **Regime estacionário.** Cada modo do ciclo é um ponto de carga constante.
  Transitórios de carga, arranques e a dinâmica de armazenamento de NH₃ não são
  simulados.
- **Escoamento isotérmico.** Não há balanço de energia: a temperatura do gás é
  a da entrada ao longo de todo o reator.
- **Decomposição completa da ureia.** Admite-se que a solução evapora e que a
  ureia se converte integralmente em NH₃ antes do catalisador.
- **Sem reações secundárias.** A oxidação do NH₃ é desprezada, e o NOx é
  tratado como NO na reação (a conversão para g/kWh usa a massa molar do NO₂,
  §11.5).
- **Canal único representativo.** Todos os canais veem o mesmo caudal e o mesmo
  α. Com má distribuição de caudal ou de NH₃ à entrada, o modelo **sobrestima a
  conversão e subestima o slip**: canais com excesso de NH₃ não compensam os
  que têm falta.
- **Canais quadrados e retos**, descritos só pelo CPSI e pela espessura de
  parede; gás ideal; pressão constante ao longo do reator.

**Do método**

- **A perda de carga não é calculada.** O volume crítico não garante uma perda
  de carga aceitável para o motor; essa verificação é feita à parte.
- **O comprimento é um input.** O programa encontra o volume (logo a área
  frontal) para o `L` indicado; não otimiza a relação entre `L` e `A`.
- **O envelhecimento e o fouling são dois números** (`KK0` e `fouling`),
  escolhidos pelo utilizador para representar o fim de vida. Não há modelo de
  desativação ao longo do tempo.
- **A cinética por omissão é a de um catalisador da literatura** (Tronconi et
  al., 1998). Para outro catalisador, os parâmetros ou os multiplicadores de
  calibração têm de ser ajustados a dados desse catalisador.
- **O volume crítico não tem margem.** No volume crítico o NOx ou o slip ficam
  encostados ao alvo. A margem de projeto é dada pelos alvos (frações abaixo do
  limite regulamentar), pelo `KK0` e pelo `fouling` — ou instalando mais volume.
- **O volume é contínuo.** O resultado não é arredondado a um número inteiro
  de módulos de catalisador comerciais.

**Do programa**

- A interface corre um motor, todos os motores de um ficheiro, ou os motores
  escolhidos com vários substratos. Em introdução manual trata um motor de cada
  vez.
- A coluna `AV_Nmh` não é uma velocidade de área normalizada (§13).
- Os resultados não foram validados experimentalmente por este programa (§1).

---

## 18. Nomenclatura

| símbolo | unidade | significado |
|---|---|---|
| A | m² | Área frontal geométrica do monolito |
| A_ef | m² | Área frontal efetiva, `A·(1 − fouling)` |
| AFR | kg/kg | Razão ar/combustível estequiométrica |
| AV | m/s | Velocidade de área, `v·dh/(4·L)` |
| α | — | Razão molar NH₃/NO à entrada do reator |
| β | — | Parâmetro de Temkin da dessorção de NH₃ |
| CPSI | cél/in² | Densidade celular do monolito |
| Deff | m²/s | Difusividade efetiva intraporo |
| Dmol | m²/s | Difusividade molecular no gás |
| dh | m | Diâmetro hidráulico do canal |
| E | cal/mol | Energia de ativação |
| ε | — | Fração de área frontal aberta |
| η | — | Eficácia média do NO na parede |
| f | — | Critério numérico da fronteira da zona ativa |
| k0 | — | Pré-exponencial de Arrhenius |
| KK0 | — | Atividade relativa do catalisador (1 = novo) |
| kmat | m/s | Coeficiente de transferência de massa gás-parede |
| L | m | Comprimento do monolito |
| λ | — | Excesso de ar |
| M | kg/mol | Massa molar |
| m_exh | kg/s | Caudal mássico de escape |
| n | rpm | Rotação nominal do motor |
| P | Pa ou kW | Pressão de operação; potência de travão |
| SFOC | g/kWh | Consumo específico de combustível |
| Sh | — | Número de Sherwood |
| s | m | Semi-espessura da parede |
| T | K | Temperatura do gás |
| τ | s | Tempo de residência |
| θ | — | Cobertura de NH₃ na superfície do catalisador |
| V | m³ | Volume de catalisador, `A·L` |
| v | m/s | Velocidade do gás nos canais |
| w | m ou % | Espessura de parede; peso do modo no ciclo |
| X_NO | % | Conversão de NO |
| x* | — | Fronteira da zona ativa da parede |

| termo | significado |
|---|---|
| Ciclo de ensaio | Conjunto de modos de carga, com pesos, usado na certificação (MARPOL Anexo VI) |
| Fouling | Obstrução dos canais do monolito por depósitos |
| Modo | Um ponto de carga do ciclo de ensaio |
| NH₃ slip | Amoníaco não reagido à saída do reator |
| SCR | Redução catalítica seletiva (*Selective Catalytic Reduction*) |
| Situação | Classificação do estado do loop de α (§11.6) |
| Substrato | A célula do monolito: densidade celular e espessura de parede |
| Volume crítico | O menor volume de catalisador que cumpre todos os alvos |

---

## 19. Estrutura do projeto e testes

| pasta ou ficheiro | conteúdo |
|---|---|
| `app.py`, `TV_SCR.bat` | Arranque da aplicação |
| `tvscr/` | Biblioteca de cálculo: solver, ciclo, loop de α, varrimento, leitura do CSV |
| `tvscr_ui/` | Interface gráfica; não calcula nada |
| `examples/` | Exemplos de uso da biblioteca |
| `tests/` | Testes automáticos |
| `INSTRUCOES.md` | Esta documentação |
| `README.md` | Correspondência com o MATLAB e paridade numérica |
| `ALTERACOES_LAYOUT.md` | Registo das alterações à interface |
| `Thesis.pdf` | Dissertação em que o programa se baseia |

Para correr os testes, a partir da pasta do projeto:

```bash
python -m pytest tests -q
```

Os testes de paridade com o MATLAB são ignorados se os ficheiros de referência
não estiverem presentes; os da interface, se não houver `tkinter` ou ecrã.

Tempos de cálculo típicos: cerca de 0.2 s por ponto de operação, 4 a 5 s por
varrimento completo de um motor e 25 s pelos cinco motores do dataset de
referência.

---

## 20. Referências

1. M. C. Reis, *Development of a Methodology for the Design and Dimensioning of
   SCR Systems for the reduction of NOx Emissions in Marine Propulsion
   Systems*. Dissertação de Mestrado em Engenharia Mecânica, 2026
   (`Thesis.pdf`, na pasta do projeto).
2. E. Tronconi, A. Cavanna e P. Forzatti, «Unsteady analysis of NO reduction
   over selective catalytic reduction — de-NOx monolith catalysts», *Industrial
   & Engineering Chemistry Research*, 37(6), 2341–2349, 1998.
   [doi:10.1021/ie970729p](https://doi.org/10.1021/ie970729p)
3. E. Tronconi e A. Beretta, «The role of inter- and intra-phase mass transfer
   in the SCR-deNOx reaction over catalysts of different shapes», *Catalysis
   Today*, 52(2), 249–258, 1999.
4. E. Tronconi, L. Lietti, P. Forzatti e S. Malloggi, «Experimental and
   theoretical investigation of the dynamics of the SCR-deNOx reaction»,
   *Chemical Engineering Science*, 51(11), 2965–2970, 1996.
5. Organização Marítima Internacional, *MARPOL, Anexo VI, Regra 13 — Óxidos de
   azoto (NOx)*, e *Código Técnico NOx 2008*.

---

## 21. Ficha técnica

| | |
|---|---|
| Programa | TECNOVERITAS SCR DIMENSIONING TOOL |
| Versão | 0.1.0 |
| Autor | Miguel Carrusca Reis |
| Enquadramento | Dissertação de Mestrado em Engenharia Mecânica, com dados e caso de estudo da TecnoVeritas |
| Orientação | Prof. Miguel Mendes, Dr. Jorge Antunes |
| Linguagem | Python ≥ 3.9 (`numpy`, `scipy`, `pandas`; `matplotlib` opcional) |
| Origem | Porte dos scripts MATLAB do modelo 1-D, com paridade numérica verificada (ver README) |
