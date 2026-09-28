# mappick

Ranking de mapas de CS2 (Premier) para o time que está no lobby: qual mapa pickar,
do melhor para o pior, em % de vitória esperada.

A página fica publicada no Claude: https://claude.ai/artifact/69WBB37W3yZXccF4HXxum5

## Arquivos

| arquivo | o que é |
|---|---|
| `artifact/template.html` | a página (HTML + cálculo em JS), com `__RAW__`, `__MAPS__` e `__PLAYERS__` no lugar dos dados |
| `artifact/build.py` | junta o template com os dados e gera `artifact/mappick.html` |
| `artifact/mappick.html` | a página pronta, é ela que é publicada |
| `data/artifact_v4.csv` | as partidas dos 13 (2.934, 2.391 de Premier, até 27/09/2026) |
| `data/artifact_v5.csv` | as mesmas partidas com K/D, ADR, rating e HS% separados por jogador |
| `modelo.py` | o mesmo cálculo da página, em Python |
| `backtest.py` | teste: prevê cada partida só com as anteriores e mede o acerto |

## Como a conta funciona

- Entram só partidas de **Premier** de quem está marcado no lobby, juntos ou separados;
  o placar é virado para o lado do lobby.
- **Peso por idade linear**: a partida mais antiga do recorte vale 0%, a mais recente
  100%, as do meio em partes iguais. Com filtro de season, refeito dentro do recorte.
- **Peso de lineup**: `0,05 + 0,95 · Jaccard(time da partida, lobby)^1,5`.
- **Metade vitória, metade K/D.** Vitória = `0,65 · resultado + 0,35 · saldo de rounds`,
  encolhida para a média do time conforme a amostra. K/D = índice 0–99 de cada jogador
  (K/D 37,5%, ADR 37,5%, rating 25%) comparado com o nível dele nas 50 partidas
  anteriores; a conversão de pontos de K/D para % sai do histórico do próprio lobby.

## Formato de `artifact_v4.csv`

`minutos desde 1690000000, mapa, rounds time 1, rounds time 2, times, premier, desempenho`

- `mapa`: índice na lista `MAPS` de `artifact/build.py`.
- `times`: 13 caracteres na ordem de `PLAYERS` em `artifact/build.py`
  (`1`/`2` = time em que o jogador estava, `-` = não jogou).
- `desempenho`: 2 dígitos (00–99) por jogador presente, na mesma ordem; `xx` = sem stats.

`artifact_v5.csv` é igual, mas com 8 dígitos por jogador: `K/D×33`, `ADR÷2`,
`rating×50`, `HS%`.

## Atualizar com partidas novas

1. No `csstats.gg`, baixar `/player/{steam64}/stats` de cada um dos 13 (o JSON fica
   em `window.MATCH_DATA`) e cruzar as partidas pelo `id`, que é global: mesmo placar
   = mesmo time. Tirar abandonos e partidas interrompidas.
2. Gravar em `data/artifact_v4.csv` no formato acima.
3. `python artifact/build.py` e publicar `artifact/mappick.html` no mesmo link.
4. Season nova do Premier: somar a data de início na lista `SEASONS` do template.

## Testar

```bash
python backtest.py
```

Roda o teste fora da amostra (933 partidas) e imprime erro (Brier), diferença de
vitória entre o terço de cima e o de baixo do ranking, e o espalhamento médio entre
mapas.
