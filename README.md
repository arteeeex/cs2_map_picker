# mappick

Ranking objetivo de mapas de CS2 a partir do seu histórico real: qual mapa pickar,
do melhor para o pior, em % de vitória esperada — **para o time que está no lobby agora**.

Sem regra escrita à mão, sem peso chutado por mapa. Tudo sai da fórmula.
Zero dependências: só Python 3 da stdlib.

```bash
python mappick.py seed     # dados de exemplo, para ver funcionando já
python mappick.py web      # abre a página local
```

---

## Como usar

### 1. Diga quem é você

```bash
python mappick.py setme 76561198XXXXXXXXX
```

Esse é o seu **Steam64** (17 dígitos, começa com `7656`). Onde achar:
abra seu perfil no CSStats e ele está na URL — `csstats.gg/player/7656...`.
Se não usa CSStats, cole a URL do seu perfil Steam em `steamid.io`
e pegue o campo `steamID64`.

### 2. Puxe o histórico

```bash
python mappick.py sync
```

**Você não adiciona os amigos à mão.** Quem jogou no seu time é descoberto
sozinho a partir das partidas: o coletor lê o roster de cada uma e registra
todo mundo, com quantas partidas vocês têm juntos.

### 3. Separe o time dos randoms

Em Premier solo a maior parte dos "colegas" é random de uma partida só, então
a lista viria com centenas de nomes. Por isso a interface mostra por padrão só
quem tem **3+ partidas** com você, mais quem você fixou como time. Tem busca
para achar qualquer um, e um botão para revelar o resto.

Para fixar alguém como time fixo (aparece sempre, com ★):

```bash
python mappick.py friend joao        # fixa
python mappick.py friend joao off    # solta
```

Na página dá para fazer o mesmo com **botão direito** no nome.

### 4. Use na hora do pick

Abra `python mappick.py web`, marque quem está no lobby e leia a ordem.
Clicar num mapa abre de onde veio o número. No terminal, o mesmo:

```bash
python mappick.py rank joao pedro
python mappick.py players            # lista todo mundo que ele conhece
```

---

## O problema que ele resolve

Winrate bruto por mapa mente por três motivos:

1. **Amostra pequena.** 2 vitórias em 2 no Nuke não é 100% de Nuke.
2. **O time muda.** Seu Nuke com o joão não é o seu Nuke sozinho.
3. **Você muda.** Partida de 8 meses atrás não descreve você hoje.

O modelo trata os três de forma explícita e mensurável.

## A fórmula

### 1. Alvo contínuo, não vitória/derrota

Binário desperdiça informação. Cada partida vira uma nota:

```
q = 0.65 · resultado + 0.35 · (rounds_ganhos / rounds_totais)
```

13x11 perdido informa diferente de 13x3 perdido.

Como `q` é uma nota e não uma probabilidade, ela é **recalibrada com os próprios
dados** para voltar à escala de vitória, usando a média de `q` nas suas vitórias
(Q1) e nas suas derrotas (Q0): `q' = (q − Q0) / (Q1 − Q0)`. Sem isso a escala fica
deslocada — foi um bug real, pego na validação.

### 2. Peso de cada partida

```
w = w_tempo · w_roster

w_tempo  = 2 ^ (−idade_em_dias / meia_vida)          meia-vida padrão: 120 dias
w_roster = piso + (1 − piso) · Jaccard(time_da_partida, time_do_lobby) ^ γ
```

O peso de roster é **o coração do sistema**. Para o lobby atual `T`, toda partida do
histórico é repesada pela semelhança do time daquela partida com `T`:

| lobby pedido | partida histórica | Jaccard | peso |
|---|---|---|---|
| eu+joão | eu+joão | 1.00 | máximo |
| eu+joão | eu+joão+pedro | 0.50 | médio |
| eu+joão | eu+pedro | 0.00 | piso (0.15) |

É isso que responde "eu e X", "eu, X e Y", "só eu e Y" — cada combinação gera um
conjunto de pesos diferente, automaticamente. O piso > 0 faz partidas com outro
time ainda informarem a força bruta do mapa, em vez de virarem lixo.

### 3. Amostra efetiva (Kish)

```
n_eff = (Σw)² / Σw²
```

40 partidas velhas com o time errado podem valer `n_eff = 5`. Esse número é o que
impede o modelo de acreditar em qualquer coisa, e é o que aparece na interface.

### 4. Encolhimento hierárquico (empirical Bayes)

Quatro níveis, cada um encolhendo para o anterior:

```
prior 0.5  →  sua base geral  →  você nesse mapa  →  você nesse mapa com esse time

est = (n_eff · média + k · nível_pai) / (n_eff + k)
```

Com pouca amostra o resultado cola no nível mais geral; com muita, se solta.
2 vitórias em 2 viram ~62%, não 100%.

### 5. Forma individual (KD, ADR, KAST, rating)

Cada jogador do lobby tem um índice composto por partida, normalizado **contra a
própria média dele** (z-score) — assim fragger e suporte são comparáveis; o que
conta é render acima ou abaixo do próprio normal naquele mapa. O z é encolhido por
amostra e agregado ponderando pelo `n_eff` de cada um.

### 6. Combinação final

```
logit(P) = logit(nível_time) + β · Z_forma
P = sigmoide(...)
```

### 7. Confiança

`se = sqrt(P(1−P)/n_eff)`, intervalo de 90% na barra. O **modo conservador**
reordena pelo pior caso do intervalo — para quando você não quer apostar num mapa
"bom, mas com 4 partidas".

---

## Validação

`python validate.py` gera histórico sintético a partir de forças **conhecidas** e
mede se o modelo as reconstrói.

**Convergência** — a fórmula está certa?

| partidas | Spearman | erro médio |
|---|---|---|
| 500 | +0.43 | 8.8 pp |
| 2.000 | +0.81 | 4.6 pp |
| 8.000 | +0.92 | 3.3 pp |
| 25.000 | +0.92 | 2.7 pp |

**Utilidade** — o encolhimento vale a pena no volume real? (15 seeds × 5 cenários)

| partidas | modelo | winrate bruto |
|---|---|---|
| 150 | **10.5 pp** de erro | 27.3 pp |
| 300 | **9.0 pp** | 25.9 pp |
| 600 | **7.5 pp** | 19.6 pp |

No regime realista o modelo erra **12 a 17 pp menos** que olhar winrate por mapa,
e ranqueia cerca de duas vezes melhor.

---

## Como o CSStats realmente entrega os dados

Mapeado na marra, porque nada disso é documentado:

- `/player/{id}` está atrás do Cloudflare e as partidas **não** vêm no HTML:
  a página chama `getStatsWhenVisible()`, ou seja, só carrega com a aba em foco.
- `/player/{id}/matches` **não existe** — devolve sempre a mesma página 404.
- A rota boa é **`/player/{id}/stats`**, ~1 MB de HTML com um JSON embutido em
  `window.MATCH_DATA` contendo *todas* as partidas, com mapa, placar, K/D/A,
  ADR, HS%, rating e o rank Premier antes/depois.
- `/player/{id}/ajax/played-with` devolve JSON com o agregado de com quem você
  jogou (útil para achar o grupo, sem detalhe por partida).

**Como o roster de cada partida é reconstruído:** o `MATCH_DATA` não diz quem
jogou com você, mas o `id` da partida é global no CSStats. Então basta baixar o
`MATCH_DATA` de cada membro do grupo e cruzar: mesmo `id` = mesma partida;
mesmo placar = mesmo time; placar invertido = jogaram um contra o outro. O
roster de centenas de partidas sai de N requisições, uma por pessoa.

Como o Cloudflare recusa `urllib`/`curl`, a coleta roda **no navegador** e
entrega ao servidor local:

```bash
python mappick.py web          # num terminal, deixa rodando
python mappick.py csstats-js   # imprime o script
```

Abra `csstats.gg` logado, F12 → console, cole o script. Ele baixa os perfis do
grupo e manda para `127.0.0.1:8770/api/ingest`. Se o Chrome reclamar de acesso à
rede privada, aceite — o servidor já responde o `Access-Control-Allow-Private-Network`
que essa checagem exige.

## Fontes de dados

Nenhuma fonte tem 100% do histórico, então o sistema **soma as fontes e deduplica**
(`mapa | dia | placar`), ficando com a versão mais completa de cada partida.

- **CSStats.gg** — fonte principal para Premier/MM. Cobertura bem maior.
- **Leetify** — complementar: stats melhores (KAST, rating) nas partidas que tem.
  Cobertura curta por um motivo estrutural: a Valve entrega o histórico por
  *match sharing codes encadeados*, cada um apontando para o próximo, então o
  Leetify só anda **para frente** a partir de quando você conectou a conta —
  o que veio antes é inalcançável. E as demos expiram em ~30 dias.
- **CSV/JSON manual** — sempre funciona, não depende de site nenhum.

```bash
python mappick.py setme  76561198XXXXXXXXX
python mappick.py sync            # todas as fontes + dedupe
python mappick.py import x.csv
python mappick.py dedupe
python mappick.py csstats-dump ID # salva o HTML cru se o layout mudar
```

## Ajustes

Tudo em `config.json` → `model`:

| parâmetro | padrão | efeito |
|---|---|---|
| `half_life_days` | 120 | menor = só o passado recente conta |
| `roster_floor` | 0.15 | menor = mais rígido quanto ao time exato |
| `roster_sharpness` | 1.5 | maior = exige mais semelhança de time |
| `shrink_*` | 10/8/6 | maior = mais conservador com amostra pequena |
| `form_beta` | 0.12 | peso do KD/ADR/KAST no resultado |
| `map_resets` | `{}` | `{"de_train": "2026-01-15"}` descarta o que é anterior a um rework |
