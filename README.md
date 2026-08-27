# radar-vagas

Agente que busca estágios e concursos toda segunda de manhã e manda um
relatório no Telegram.

```
coletores → filtro de regras → dedup → ranking LLM → relatório → Telegram
                                 ↑
                          state/seen.json
```

## O que já está pronto

| Arquivo | Papel |
|---|---|
| `config.yaml` | **a especificação** — é aqui que você ajusta o agente |
| `radar/models.py` | `Oportunidade`, o formato normalizado de todo coletor |
| `radar/coletores/gupy.py` | estágios (fonte principal) |
| `radar/coletores/dou.py` | editais federais no Diário Oficial da União |
| `radar/coletores/querido_diario.py` | editais do DF via API aberta |
| `radar/filtros.py` | corte por palavra-chave e geografia (barato) |
| `radar/ranking.py` | nota 0–10 pelo LLM (caro, só no que sobrou) |
| `radar/dedup.py` | estado do que já foi reportado |
| `radar/relatorio.py` | render HTML do Telegram |
| `.github/workflows/radar.yml` | cron de segunda, 08:00 BRT |

## Passo a passo

### 1. Repositório

Crie `radar-vagas` no GitHub, **privado** — o repo guarda suas preferências e
o histórico do que você já viu.

```bash
git init && git add . && git commit -m "esqueleto do radar"
git remote add origin git@github.com:gabrielcaixeta01/radar-vagas.git
git push -u origin main
```

### 2. Rodar local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m radar --dry-run --sem-llm
```

Imprime no terminal, não envia nada, não grava estado. Rode isso várias vezes
enquanto ajusta o `config.yaml`.

Para testar um coletor de cada vez:

```bash
python -m radar --fonte gupy --dry-run --sem-llm -v
```

### 3. Calibrar o filtro

A primeira execução quase certamente vai vir errada em algum extremo: ou
passa lixo demais, ou corta vaga boa. O log mostra `filtro de regras: N -> M`.

- Muita coisa passando → adicione termo em `keywords_negativas`
- Vaga boa sumindo → rode com `-v`, veja se ela chegou a ser coletada. Se não
  chegou, o problema é o coletor, não o filtro.

### 4. Bot do Telegram

1. Fale com [@BotFather](https://t.me/BotFather) → `/newbot` → guarde o token
2. Mande qualquer mensagem para o seu bot
3. Pegue o chat ID:

```bash
curl "https://api.telegram.org/bot<SEU_TOKEN>/getUpdates"
```

Procure `"chat":{"id":123456789`.

```bash
export TELEGRAM_TOKEN=...
export TELEGRAM_CHAT_ID=...
python -m radar --sem-llm   # execução real, sem LLM
```

### 5. Ligar o LLM

```bash
export ANTHROPIC_API_KEY=...
python -m radar --dry-run
```

Custo é baixo porque só o que passou pelo filtro vai para o modelo. Se
`ANTHROPIC_API_KEY` faltar, o agente roda mesmo assim, com nota neutra.

### 6. Secrets no GitHub

`Settings → Secrets and variables → Actions → New repository secret`:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY`

### 7. Testar no CI antes do cron

Aba `Actions` → workflow `radar` → `Run workflow`. Rode manual até o relatório
sair do jeito que você quer. O `workflow_dispatch` fica no arquivo para sempre.

### 8. Deixar rodando

O cron já está ativo: `0 11 * * 1` = 11:00 UTC = 08:00 em Brasília.

## O que vai quebrar

Isso não é pessimismo, é o ciclo de vida normal de um agregador:

1. **Gupy** — endpoint não documentado. Se voltar zero itens, abra
   `portal.gupy.io`, aba Network, faça uma busca e confira o endpoint e os
   nomes dos campos. Ajuste `ENDPOINT` e `_para_oportunidade`.
2. **DOU** — o parser depende de `<script id="params">`. Se o log disser que
   não encontrou, o layout do in.gov.br mudou.
3. **Extração de prazo** — heurística de regex sobre texto de edital. Acerta a
   maioria, erra em redação incomum. Por isso o relatório sempre linka o
   original.

Cada coletor roda isolado: um quebrado não derruba os outros, só some do
relatório com um `ERROR` no log do Actions.

## Pegadinhas do GitHub Actions

- Workflow agendado é **desativado após 60 dias sem commit** no repo. O passo
  que commita o `seen.json` resolve isso sozinho enquanto houver novidade —
  mas se passarem semanas sem nada novo, o repo fica parado. Se acontecer,
  o GitHub manda email antes de desativar.
- O cron atrasa 5–20 min em horário de pico. Não é bug.

## Próximos passos naturais

- Coletor do Cebraspe/IADES (poucas páginas, HTML estável — bom exercício)
- Adicionar `superior` em `escolaridade` perto da formatura, o que abre
  Técnico e Analista Judiciário
- Trocar `seen.json` por SQLite se o arquivo passar de alguns milhares de linhas
