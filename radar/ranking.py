"""Estagio 2 do funil: nota do LLM.

So roda no que sobreviveu a filtros.py. Julga o que regra nao julga:
se o programa tem trilha de efetivacao, se a duracao encaixa com a formatura,
e se o cargo do edital e mesmo acessivel com o nivel de escolaridade atual.

Se ANTHROPIC_API_KEY nao estiver definida, cai para nota neutra e segue —
o relatorio sai sem ranking em vez de nao sair.
"""

from __future__ import annotations

import json
import logging
import os
import re

from .models import Oportunidade

log = logging.getLogger(__name__)

PROMPT_ESTAGIO = """Voce avalia vagas de entrada (estagio, trainee ou junior) \
para um estudante de Engenharia de Computacao na UnB, 7o semestre, formatura \
prevista em {formatura}.

Perfil dele:
- So SOFTWARE. Hardware, eletronica, firmware, embarcados, redes fisicas e \
suporte tecnico sao descarte imediato.
- Trilhas por ordem de interesse: {prioridades}.
- Mora em Brasilia e NAO se muda para Sao Paulo. Vaga presencial fora do DF \
nao serve, por melhor que seja; remota serve.
- Vaga internacional so serve se for remota e contratar de fato quem mora no \
Brasil (se exige visto, autorizacao de trabalho no exterior ou presenca no \
pais, nota baixa).
- Prioriza chance real de efetivacao.

Responda APENAS com JSON, sem markdown e sem texto em volta:
{{"nota": <0-10>, "motivo": "<uma frase curta em portugues>", \
"efetivacao": <true|false|null>}}

Criterios de nota:
- 9-10: trilha prioritaria (dados/ML ou quant/financeiro), empresa alvo, \
local compativel (DF ou remoto), efetivacao ou vaga CLT de entrada
- 7-8: software em geral ou tecnologia em instituicao financeira, local \
compativel, duracao >= 12 meses
- 4-6: tecnologia mas encaixe fraco (TI generalista, suporte disfarcado de \
dev), ou remoto duvidoso
- 0-3: hardware/eletronica/embarcados/infra fisica, presencial fora do DF, \
exige visto ou residencia no exterior, ou exige formatura anterior a {formatura}

VAGA:
{texto}"""

PROMPT_CONCURSO = """Voce avalia publicacoes de diario oficial para um \
estudante de Engenharia de Computacao na UnB, 7o semestre, formatura \
prevista em {formatura}. Salario inicial de interesse: acima de R$ {minimo}.

O que interessa a ele, nesta ordem:
1. NIVEL SUPERIOR em carreira de TECNOLOGIA DA INFORMACAO (analista de \
sistemas, desenvolvimento, dados, seguranca) ou do setor FINANCEIRO \
(Banco Central, CVM, BNDES, area economico-financeira), desde que a posse \
tenda a ocorrer a partir de {formatura} — edital recem-aberto, prazo longo \
ou cadastro de reserva.
2. NIVEL MEDIO apenas em banco publico (Caixa, Banco do Brasil, BRB): \
tecnico bancario, escriturario, agente comercial. Esses ele pode fazer ja, \
sem diploma.

Cargo de nivel medio fora de banco, ou cargo de nivel superior em area que \
nao e TI nem financeira, nao interessa.

Responda APENAS com JSON, sem markdown e sem texto em volta:
{{"nota": <0-10>, "motivo": "<uma frase curta em portugues>", \
"nivel_medio": <true|false|null>}}

Criterios de nota:
- 0-2: nao e edital de abertura, ou nenhum cargo se encaixa nos dois casos acima
- 4-6: encaixa, mas salario baixo, orgao fora do interesse, ou nivel superior \
com posse claramente antes de {formatura}
- 7-10: edital de abertura de TI/financeiro de nivel superior compativel com \
o prazo dele, ou de nivel medio em banco publico, com salario acima do minimo

PUBLICACAO:
{texto}"""


def _cliente():
    try:
        import anthropic
    except ImportError:
        log.warning("pacote anthropic nao instalado — pulando ranking")
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY ausente — pulando ranking")
        return None
    return anthropic.Anthropic()


def rankear(itens: list[Oportunidade], cfg: dict) -> list[Oportunidade]:
    rk = cfg["ranking"]

    cliente = _cliente() if rk["usar_llm"] else None
    if cliente is None:
        # Sem LLM todo mundo recebe a nota de corte: o relatorio sai sem
        # ordenacao, mas sai. Nota None faria selecionar() descartar tudo.
        for o in itens:
            o.nota = rk["nota_minima"]
            o.motivo = "" if not rk["usar_llm"] else "nao avaliado (LLM indisponivel)"
        return itens

    for o in itens:
        if o.tipo == "estagio":
            prompt = PROMPT_ESTAGIO.format(
                formatura=cfg["estagio"]["formatura_prevista"],
                prioridades="; ".join(cfg["estagio"]["prioridades"]),
                texto=o.texto_para_analise())
        else:
            prompt = PROMPT_CONCURSO.format(
                minimo=cfg["concursos"]["salario_minimo"],
                formatura=cfg["estagio"]["formatura_prevista"],
                texto=o.texto_para_analise())

        try:
            resp = cliente.messages.create(
                model=rk["modelo"],
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            dados = _json_seguro("".join(
                b.text for b in resp.content if b.type == "text"))
            o.nota = int(dados.get("nota", 0))
            o.motivo = str(dados.get("motivo", ""))[:200]
            if dados.get("efetivacao") is True:
                o.alertas.append("efetivacao provavel")
        except Exception as e:  # noqa: BLE001
            # Item que falha vai para o relatorio com nota neutra em vez de
            # sumir: perder oportunidade e pior do que mostrar ruido.
            log.warning("ranking falhou para %r (%s)", o.titulo[:60], e)
            o.nota = rk["nota_minima"]
            o.motivo = "nao avaliado"

    return itens


def _json_seguro(texto: str) -> dict:
    texto = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.M).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def selecionar(itens: list[Oportunidade], cfg: dict) -> list[Oportunidade]:
    rk = cfg["ranking"]
    aprovados = [o for o in itens if (o.nota or 0) >= rk["nota_minima"]]
    aprovados.sort(key=lambda o: (-(o.nota or 0), o.organizacao))
    return aprovados
