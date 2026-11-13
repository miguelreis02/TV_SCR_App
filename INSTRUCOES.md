# TECNOVERITAS SCR DIMENSIONING TOOL — Instruções de utilização

Guia de utilização da aplicação. Para a documentação técnica do modelo e da
correspondência com o MATLAB, ver o [README](README.md).

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

---

## 2. Requisitos

- Python 3.9 ou mais recente, com `tkinter` (vem no instalador oficial de
  Windows e no Anaconda).
- Bibliotecas: `numpy`, `scipy`, `pandas`. `matplotlib` só é preciso para as
  figuras.

Se usa Anaconda, já tem tudo. Caso contrário, no Anaconda Prompt (ou no
terminal onde o Python certo esteja acessível), a partir da pasta do projeto:

```bash
pip install -r requirements.txt
```

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
│ [▶ Correr dim.] │                                                      │
├─────────────────┴──────────────────────────────────────────────────────┤
│ Pronto                         F5 correr · Ctrl+O · Ctrl+S · Ctrl+PgDn │ estado
└────────────────────────────────────────────────────────────────────────┘
```

**Barra lateral (à esquerda).** Os oito separadores de inputs, agrupados em
três blocos — *Dados do projeto*, *Modelo do catalisador* e *Cálculo* — seguidos
das ações sobre o cenário e, sempre visível ao fundo, do botão
**▶ Correr dimensionamento**. Um ponto vermelho ao lado de um separador
assinala que ele tem um campo com valor inválido.

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
| `F5` (ou `Ctrl+Enter`) | Correr dimensionamento |
| `Ctrl+O` | Carregar cenário |
| `Ctrl+S` | Gravar cenário |
| `Ctrl+PgDn` / `Ctrl+PgUp` | Separador seguinte / anterior |

Não é preciso percorrer todos os separadores: todos os campos têm valor por
omissão, tirando os dados do motor. Na prática, para um primeiro cálculo basta
o separador **1 · Dados do motor**.

**O «i» num círculo ao lado de um parâmetro** indica que ele tem uma explicação
curta: passe o rato sobre o «i» (ou sobre o nome do parâmetro) para a ver.

Os números muito grandes ou muito pequenos aparecem em notação científica curta
(`2.5e10`, `1e-6`); pode escrevê-los assim ou por extenso, com ponto ou vírgula
decimal.

---

## 5. Primeiro dimensionamento, passo a passo

No separador **1 · Dados do motor**, escolha a origem dos dados: **Ficheiro
CSV** ou **Introdução manual**.

### A partir de um ficheiro CSV

1. **Ficheiro (CSV)** — carregue em **Procurar…** e escolha o ficheiro de
   inputs. A lista «Motor» passa a ter os motores que ele traz.
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
ficheiro»**. Nesse caso os campos *Motor*, *L* e *A* ficam inertes — a
geometria de cada motor vem do ficheiro — e é produzida a tabela-resumo dos
volumes críticos.

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
O caudal só é usado directamente se estiver preenchido em **todos** os modos;
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

### 1 · Dados do motor

| campo | o que é | onde arranjar |
|---|---|---|
| Origem dos dados | Ficheiro CSV ou introdução manual | — |
| Ficheiro (CSV) | Uma linha por modo do ciclo e por motor | Ensaio / projeto |
| Motor | Etiqueta na coluna `Engine` | Do próprio ficheiro |
| Correr todos os motores | Corre todos e produz a tabela-resumo | — |
| Combustível | Define o AFR estequiométrico | Especificação do navio |
| Pressão [Pa] | Pressão de operação | 101325 (atmosférica) |
| Limite MARPOL | Tier I / II / III | Regulamento aplicável |
| Lei de potência em toda a gama | Reproduz o `9·n^-0.2` do MATLAB | Só para comparar com resultados antigos |

O ficheiro tem de trazer, por modo: carga, peso do modo no ciclo, potência de
travão, temperatura à entrada, NO à entrada e (para o caudal de escape) SFOC e
λ. As colunas de geometria são **opcionais**: um ficheiro só com condições de
operação é válido, e o comprimento indica-se no separador da Geometria.

Combustível, pressão e limite MARPOL aplicam-se seja qual for a origem dos
dados.

#### Caudal de escape

Não é um input directo (embora possa sê-lo): sai do consumo e do excesso de ar,
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
> `Fuel_Consumption_[kgh]` é exactamente **1.1 ×** `SFOC · P` — traz uma margem
> de 10 %. A aplicação ignora-a e recalcula, como o MATLAB fazia: usá-la daria
> caudais 10 % altos e, com eles, um reator sobredimensionado.

### 2 · Geometria do monolito

| campo | o que é | nota |
|---|---|---|
| Comparar vários pares CPSI / parede | Liga o varrimento de substratos | Ver abaixo |
| Densidade celular [cél/in²] | CPSI. `passo = 1 in / √CPSI` | **Escolha de projeto**, não vem do ficheiro |
| Espessura de parede [m] | Espessura total | Idem. A semi-espessura governa a difusão intraporo |
| Comprimento L [m] | Fica **fixo** no varrimento; é a área que varia (`A = V/L`) | Prefixado a partir do ficheiro, se este o trouxer |

O **fouling** passou para o separador da Cinética, junto do envelhecimento:
é uma condição do catalisador, não da geometria escolhida.

Se a parede for grossa de mais para o CPSI escolhido, o canal fecha
(`dh ≤ 0`) e a aplicação recusa correr, dizendo-o.

#### Comparar vários pares CPSI / parede

Ligando **«Comparar vários pares CPSI / parede»**, os dois campos únicos dão
lugar a uma tabela: uma linha por par, o CPSI em cél/in² e a parede **em
milímetros**. A aplicação corre o varrimento em volume completo uma vez por
par e põe os volumes críticos lado a lado.

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

| | por modo | ciclo ponderado |
|---|---|---|
| NOx | ≤ 80 % do limite | ≤ 60 % do limite |
| NH₃ slip | ≤ 20 ppm | ≤ 10 ppm |

### 4 · Cinética e transporte

Os valores por omissão são os da Tabela 2 de Tronconi 1998 (catalisador 1) e
não precisam de ser mexidos para o caso de referência. **Energias de ativação
em cal/mol.**

Os dois campos com mais impacto prático estão em **Transporte e estado do
catalisador**:

- **Envelhecimento KK0** — entra ao quadrado no pré-exponencial de redução de
  NO (`k0NO_efetivo = k0NO · KK0²`). `1` é catalisador novo, `0.8` um fim de
  vida típico.
- **Fouling** — fracção da área frontal perdida por obstrução dos canais: a
  área efetiva passa a `A·(1−fouling)`.

São eles que separam um reator que cumpre no primeiro dia de um que cumpre ao
fim da vida. Dimensionar com `KK0 = 1` e `fouling = 0` dá o menor reator
possível — e um que deixa de cumprir mal o catalisador envelhece ou suja.

> A temperatura fixa, a conversão só «vê» as constantes agrupadas. Mexer em
> `k0` ou em `E` isoladamente para o mesmo ponto é redundante — use os
> multiplicadores de calibração para isso.

### 5 · Calibração (multiplicadores)

Multiplicam a cinética já calculada (`× kNO`, `× kads`, `× Deff`, `× k0d`).
Tudo a `1` reproduz exatamente a cinética de referência. Servem para ajustar o
modelo a um catalisador concreto sem tocar nos parâmetros físicos.

### 6 · Varrimento em volume

| campo | efeito |
|---|---|
| Volume máximo [m³] | Maior volume a considerar; o varrimento começa aqui e desce |
| Decremento de volume [m³] | Passo descendente |
| Volume mínimo [m³] | Piso do varrimento |
| Refinar por bisseção em V | Afina o volume crítico para além da resolução do passo |
| Tolerância do refinamento [m³] | Quando parar de bissetar |

### 7 · Loop de α

| campo | efeito |
|---|---|
| α de arranque | Valor inicial em todos os modos |
| Passo de α | Ajuste multiplicativo (0.02 = 2 %) |
| α mínimo / máximo | Limites de segurança do doseamento |
| Máximo de iterações | Guarda contra não-convergência |
| Tolerância de bracketing | Quando o intervalo `[lo, hi]` conta como colapsado |
| Minimizar α após cumprir os alvos | Ver a nota abaixo |

**Sobre «Minimizar α»**: enquanto o reator tem folga, o α de arranque já cumpre
tudo e o loop fecha à primeira iteração — o caudal de ureia fica igual ao de
arranque e é pouco informativo. Com esta opção ligada, o α desce por modo até
ao **mínimo admissível**, dando o consumo real de ureia. **Não altera o volume
crítico**, só o ponto de operação reportado. Ligue-a se o objetivo for reportar
consumo de ureia; deixe-a desligada para reproduzir o comportamento do MATLAB.

### 8 · Numérico e saída

| campo | efeito |
|---|---|
| Nós axiais | Malha do solver. 120 é o valor validado; alterar muda o resultado ao nível da discretização |
| Pasta de resultados | Onde gravar. Em branco = não grava |
| Gravar CSV / figuras | O que escrever em disco |

---

## 7. Ler os resultados

### No painel de resultados

| separador | mostra |
|---|---|
| **Resumo** | O **volume crítico** em destaque, com a área frontal e o comprimento; ao lado, o NOx e o slip do ciclo com o respetivo alvo, a conversão e o consumo de ureia — tudo avaliado nesse volume. Por baixo, o α de cada modo. |
| **Modos** | Uma linha por modo do ciclo, no volume crítico: α, X_NO, NO [g/kWh], slip, ureia, τ e a situação do modo. Os alvos por modo estão na legenda da tabela. |
| **Varrimento** | Uma linha por volume avaliado, do maior para o menor. O volume crítico está realçado a amarelo; os volumes inadmissíveis estão a vermelho. |
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

Em `<pasta>/<motor>/`:

- **`volume_sweep_<motor>.csv`** — uma linha por volume: V, A, situação,
  admissível, NOx/slip/X_NO/ureia do ciclo, nº de iterações e fase
  (1 = varrimento, 2 = refinamento). É aqui que se lê a margem que cada volume
  acima do crítico compra.
- **`volume_sweep_<motor>_modos.csv`** — uma linha por (volume, modo): α, X_NO,
  NO [g/kWh], slip, ureia, τ, AV, η e a situação daquele modo. É aqui que se vê
  **qual o modo que fecha o varrimento** — tipicamente o de carga mais alta, é
  onde o slip cresce primeiro.
- **`volume_sweep_<motor>.png`** — painel 2×2: NOx do ciclo, slip (escala
  logarítmica), α por modo e consumo de ureia, todos contra o volume.

Com «todos os motores», junta-se `resumo_volumes_criticos.csv` e `.png` na raiz
da pasta.

No **varrimento de substratos**, a estrutura muda: cada par tem a sua subpasta
`<motor>_CPSI<n>_w<parede>mm/` com os mesmos ficheiros, e na raiz fica
`resumo_substratos.csv` — uma linha por (motor, par), com CPSI, parede, `dh`,
fração de área aberta, volume crítico, área crítica e os valores do ciclo
nesse volume. Pares impossíveis aparecem na tabela com o motivo na coluna
`observacao`.

> **Nota sobre a coluna `AV_Nmh`**: é calculada como `AV · 3600 · 273.15`, tal
> como no MATLAB, o que não corresponde a uma normalização a 0 °C. Leia-a como
> indicador relativo entre pontos, não como um caudal em Nm³/h/m².

---

## 8. Guardar e repetir um estudo

Na barra lateral, por baixo dos separadores (grupo **Cenário**):

- **Gravar cenário…** (`Ctrl+S`) escreve um `.json` com **todos** os inputs do
  formulário. Em introdução manual, os dados do motor vão **dentro** do
  ficheiro, que passa a correr sozinho, sem CSV nenhum.
- **Carregar cenário…** (`Ctrl+O`) repõe o formulário a partir desse `.json`.
- **Repor omissões** volta aos valores por omissão sem perder o ficheiro nem o
  motor escolhidos.

No separador *Registo* do painel de resultados:

- **Gravar registo…** guarda o conteúdo da consola num `.txt`.
- **Limpar** esvazia a consola.

O mesmo `.json` corre sem interface:

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
| «Não consegui ler o ficheiro» | Separador ou decimal diferentes | O leitor espera `;` e vírgula decimal. Para outro formato, use a biblioteca com `DatasetFormat` |
| «Coluna "..." não existe no ficheiro» | Cabeçalhos com outros nomes | Renomeie as colunas, ou use `ColumnMap` na biblioteca |
| «Geometria da célula inválida» | Parede grossa de mais para o CPSI | Baixe a espessura ou o CPSI |
| «"α mínimo" tem de ser menor que "α máximo"» | Limites trocados | Corrija |
| Campo a **vermelho claro** | Valor não numérico ou fora dos limites | A aplicação abre o separador desse campo e põe lá o cursor; o texto do erro diz qual é o campo e o limite |
| «Nenhuma linha do motor "X"» | Etiqueta não existe no ficheiro | Escolha da lista |

---

## 11. Reproduzir os resultados do MATLAB

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
arredondamento de máquina.

---

## 12. Usar sem interface

A interface não calcula nada — só recolhe inputs e chama a biblioteca. Tudo o
que ela faz está disponível em Python:

```python
from tvscr import (EngineDataset, SubstrateGeometry, EmissionTargets,
                   VolumeSweepOptions, AlphaLoopOptions, volume_sweep)

ds   = EngineDataset.from_csv("Tabela_Inputs_Final.csv")
case = ds.build_case("DG1", substrate=SubstrateGeometry(cpsi=46,
                                                        wall_thickness_m=0.43e-3))
s = volume_sweep(case, EmissionTargets(),
                 VolumeSweepOptions(fouling=0.15, aging_KK0=0.80),
                 AlphaLoopOptions())
print(s.critical_volume_m3, s.oversize)
```

Há exemplos completos em `examples/`, incluindo um motor definido de raiz sem
ficheiro CSV (`04_motor_novo_sem_ficheiro.py`).
