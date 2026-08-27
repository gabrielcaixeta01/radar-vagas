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

PROMPT_ESTAGIO = """Voce avalia vagas de estagio para um estudante de \
Engenharia de Computacao na UnB, formatura prevista em {formatura}. Ele \
prioriza vagas com chance real de efetivacao.

Responda APENAS com JSON, sem markdown e sem texto em volta:
{{"nota": <0-10>, "motivo": "<uma frase curta em portugues>", \
"efetivacao": <true|false|null>}}

Criterios de nota:
- 9-10: empresa alvo, stack compativel, programa com efetivacao declarada
- 7-8: stack compativel e duracao >= 12 meses
- 4-6: relacionada a tecnologia mas com encaixe fraco
- 0-3: fora da area, ou exige formatura anterior a {formatura}

VAGA:
{texto}"""

PROMPT_CONCURSO = """Voce avalia publicacoes de diario oficial para um \
estudante que hoje so pode concorrer a cargos de NIVEL MEDIO (esta no 7o \
semestre, ainda sem diploma). Ele busca salario inicial acima de R$ {minimo}.

Responda APENAS com JSON, sem markdown e sem texto em volta:
{{"nota": <0-10>, "motivo": "<uma frase curta em portugues>", \
"nivel_medio": <true|false|null>}}

Criterios de nota:
- 0-2: nao e edital de concurso, ou so tem cargos de nivel superior
- 4-6: edital de nivel medio, mas salario baixo ou orgao fora do interesse
- 7-10: edital com cargo de nivel medio, salario acima do minimo, orgao federal ou do DF

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
                texto=o.texto_para_analise())
        else:
            prompt = PROMPT_CONCURSO.format(
                minimo=cfg["concursos"]["salario_minimo"],
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
