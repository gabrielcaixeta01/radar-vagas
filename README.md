# radar-vagas

Agente que busca estágios e concursos toda segunda de manhã, compara cada vaga
com o meu currículo e me manda por e-mail um relatório ordenado por aderência
(também salvo em `relatorios/AAAA-MM-DD.md`).

```
coletores ──→ filtro de regras ──→ dedup ──→ ranking (CV × vaga) ──→ relatório ──→ e-mail + .md
(Indeed,       (nível, área,         ↑        LLM com JSON validado,
 Greenhouse,    geografia)     state/seen.json  ou palavras do CV
 DOU)                                           se não houver chave
```

## O que já está pronto

| Arquivo | Papel |
|---|---|
| `config.yaml` | **a especificação** — é aqui que você ajusta o agente |
| `perfil/curriculo.md` | o currículo que o ranking compara com cada vaga |
| `radar/models.py` | `Oportunidade`, o formato normalizado de todo coletor |
| `radar/coletores/vagas.py` | estágios via jobspy (Indeed) |
| `radar/coletores/greenhouse.py` | vagas direto do ATS de BTG, XP, Inter, C6, Stone... |
| `radar/coletores/dou.py` | editais federais no Diário Oficial da União |
| `radar/filtros.py` | corte por palavra-chave e geografia (barato) |
| `radar/ranking.py` | nota 0–10 CV × vaga: LLM com saída validada (pydantic), ou palavras do CV |
| `radar/dedup.py` | estado do que já foi reportado |
| `radar/relatorio.py` | render markdown e HTML |
| `radar/correio.py` | envio por e-mail (SMTP / Gmail) |
| `radar/saida.py` | grava o .md e escreve no resumo do Actions |
| `.github/workflows/radar.yml` | cron de segunda, 08:00 BRT |

## Ranking: como a nota sai

Com `ANTHROPIC_API_KEY`, cada vaga que passou pelo filtro vai numa chamada ao
`claude-haiku-5-5` com o currículo inteiro no system prompt. A resposta é
forçada a um schema (`messages.parse` + `output_format=AvaliacaoVaga`):

```json
{"nota": 8, "aderente": true, "justificativa": "Python e SQL; remoto", "efetivacao": null}
```

O schema garante o tipo, mas não o intervalo — `nota` fora de 0–10 é tratada
como resposta inválida e gera nova tentativa. Duas falhas seguidas e a vaga cai
para a nota por palavras em vez de sumir do relatório (`[sem LLM]` no motivo).
O log do Actions mostra tokens e custo estimado de cada execução; para ~40
vagas/semana dá cerca de US$ 0,02.

Sem a chave, a nota é `2 + competências do CV encontradas (máx. 4) + termos de
trilha (máx. 2) + 2 se empresa alvo`. As listas estão em `perfil:` no
`config.yaml`. É pior que o modelo, mas já corta vaga que não tem nada a ver.

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
`ANTHROPIC_API_KEY` faltar, o agente roda mesmo assim, com a nota por palavras do CV.

### 6. Secrets no GitHub

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Obrigatório? | O que é |
|---|---|---|
| `SMTP_USER` | sim | o Gmail que envia, ex. `gabrielcaixetaromero@gmail.com` |
| `SMTP_PASSWORD` | sim | **senha de app**, não a senha da conta: ative a verificação em 2 etapas e gere em <https://myaccount.google.com/apppasswords> |
| `EMAIL_TO` | não | destinatário; padrão = `SMTP_USER` |
| `ANTHROPIC_API_KEY` | não | sem ele o ranking é por palavras do CV |

Sem `SMTP_USER`/`SMTP_PASSWORD` o job fica vermelho (o GitHub te avisa por
e-mail) e o `seen.json` não é atualizado — as vagas voltam na semana seguinte
em vez de se perderem. O relatório `.md` é commitado mesmo assim.

Testar o e-mail local:

```bash
export SMTP_USER=... SMTP_PASSWORD=...
python -m radar --destino email     # envia de verdade e grava o estado
```

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

## Roadmap

| # | Etapa | Status |
|---|---|---|
| 1 | Vaga → Claude API → avaliação | ✅ `ranking.py` |
| 2 | JSON validado com pydantic + retry | ✅ `AvaliacaoVaga`, `TENTATIVAS = 2` |
| 3 | Coleta real (Greenhouse) | ✅ `coletores/greenhouse.py` — iFood não usa Greenhouse (404) |
| 4 | SQLite para dedup | ⏳ hoje é `state/seen.json` |
| 5 | Avaliação: 20–30 vagas com nota manual vs. nota do modelo | ⏳ |
| 6 | Ajuste de prompt guiado pela métrica da etapa 5 | ⏳ depende da 5 |
| 7 | Agente com tools (`buscar_detalhes_da_vaga`, `consultar_historico`) | ⏳ |
| 8 | RAG: embeddings dos trechos do CV | ⏳ hoje o CV inteiro vai no prompt (~1k tokens) |
| 9 | GitHub Actions toda segunda + e-mail | ✅ falta só cadastrar os secrets |
| 10 | README com arquitetura, decisões, métricas e limitações | 🟡 parcial — métricas dependem da 5 |

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
| **Greenhouse: ifood, mercadolivre, picpay, pagbank, creditas, neon** | 404 em `boards-api.greenhouse.io` (04/11/2026) — essas empresas usam outro ATS. |
| **LinkedIn** | ToS proíbe scraping e o bloqueio por IP é agressivo. Decisão de projeto, não limitação técnica. |

Alternativa pendente para editais distritais (DODF/BRB/CLDF): raspar o portal
oficial do DODF. Não foi implementado — precisa de validação de acesso antes.
