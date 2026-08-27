# radar-vagas

Agente que busca estágios e concursos toda segunda de manhã e gera um
relatório em `relatorios/AAAA-MM-DD.md`.

```
coletores → filtro de regras → dedup → ranking LLM → relatório → arquivo .md 
                                 ↑
                          state/seen.json
```

## O que já está pronto

| Arquivo | Papel |
|---|---|
| `config.yaml` | **a especificação** — é aqui que você ajusta o agente |
| `radar/models.py` | `Oportunidade`, o formato normalizado de todo coletor |
| `radar/coletores/vagas.py` | estágios via jobspy (Indeed) |
| `radar/coletores/dou.py` | editais federais no Diário Oficial da União |
| `radar/filtros.py` | corte por palavra-chave e geografia (barato) |
| `radar/ranking.py` | nota 0–10 pelo LLM (caro, só no que sobrou) |
| `radar/dedup.py` | estado do que já foi reportado |
| `radar/relatorio.py` | render markdown (e HTML, se usar Telegram) |
| `radar/saida.py` | grava o .md e escreve no resumo do Actions |
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
python -m radar --fonte vagas --dry-run --sem-llm -v
```

### 3. Calibrar o filtro

A primeira execução quase certamente vai vir errada em algum extremo: ou
passa lixo demais, ou corta vaga boa. O log mostra `filtro de regras: N -> M`.

- Muita coisa passando → adicione termo em `keywords_negativas`
- Vaga boa sumindo → rode com `-v`, veja se ela chegou a ser coletada. Se não
  chegou, o problema é o coletor, não o filtro.

### 4. Gerar o relatório

```bash
python -m radar --sem-llm
```

Grava dois arquivos:

- `relatorios/2026-09-01.md` — o histórico, um por semana
- `relatorios/ultimo.md` — sempre o mais recente, bom para favoritar no GitHub

Quando roda no Actions, o mesmo texto aparece no resumo da execução: aba
`Actions` → clique no run → o relatório está renderizado na própria página.
Não precisa baixar nada.

### 5. Ligar o LLM

```bash
export ANTHROPIC_API_KEY=...
python -m radar --dry-run
```

Custo é baixo porque só o que passou pelo filtro vai para o modelo. Se
`ANTHROPIC_API_KEY` faltar, o agente roda mesmo assim, com nota neutra.

### 6. Secret no GitHub

Só um, e ele é opcional:

`Settings → Secrets and variables → Actions → New repository secret`

- `ANTHROPIC_API_KEY` — sem ele o radar funciona, só não ordena por relevância

### 7. Testar no CI antes do cron

Aba `Actions` → workflow `radar` → `Run workflow`. Rode manual até o relatório
sair do jeito que você quer. O `workflow_dispatch` fica no arquivo para sempre.

### 8. Deixar rodando

O cron já está ativo: `0 11 * * 1` = 11:00 UTC = 08:00 em Brasília.

## O que vai quebrar

Isso não é pessimismo, é o ciclo de vida normal de um agregador:

1. **vagas (jobspy)** — quando um portal muda, quem conserta é o mantenedor
   da lib. Rode `pip install -U python-jobspy` antes de investigar.
   Só o Indeed está ativo — ver "Fontes descartadas". O Indeed às vezes
   bloqueia IP de datacenter; se falhar no Actions mas funcionar local, é isso.
2. **DOU** — o parser depende de `<script id="params">` na página
   `/leiturajornal?...&secao=do3`. Se o log disser que não encontrou, o layout
   mudou. Atenção: a seção **do3** é a que tem edital; a do1 é só ato normativo.
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
- Notificação ativa, se um dia o arquivo no repo não bastar: `python -m radar
  --destino telegram` já funciona, só precisa de `TELEGRAM_TOKEN` e
  `TELEGRAM_CHAT_ID` (bot criado no @BotFather)

## Fontes descartadas

Validado contra os serviços reais em 27/08/2026. Não reintroduza nenhuma
destas sem antes rodar uma chamada e ver dado voltando.

| Fonte | Por quê |
|---|---|
| **Querido Diário** | O DF existe na base (`territory_ids=5300108`, 1455 diários), mas a coleta **parou em 2025-03-28**: `published_since=2025-04-01` devolve 0. Para um radar de editais abertos, tudo que há ali já venceu. |
| **Glassdoor** (jobspy) | HTTP 400 `Glassdoor: location not parsed`. Testado com `Brasília, DF`, `Brasilia`, `Brazil`, `Brasilia, Brazil` e `São Paulo, Brazil` — os cinco deram 0 linhas. |
| **Google Jobs** (jobspy) | 0 linhas, com `search_term` sozinho e com `google_search_term` em linguagem natural. |
| **Gupy** | `portal.api.gupy.io/api/job` devolve 404; a API documentada exige token Bearer de empregador. |
| **LinkedIn** | ToS proíbe scraping e o bloqueio por IP é agressivo. Decisão de projeto, não limitação técnica. |

Alternativa pendente para editais distritais (DODF/BRB/CLDF): raspar o portal
oficial do DODF. Não foi implementado — precisa de validação de acesso antes.
