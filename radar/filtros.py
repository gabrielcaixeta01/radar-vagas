"""Estagio 1 do funil: regras baratas.

Roda antes do LLM e corta ~90% do volume. Cada item descartado aqui e um
item que voce nao paga para o modelo ler.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from .models import Oportunidade

log = logging.getLogger(__name__)


def normalizar(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "")
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return txt.lower()


def _tem(texto: str, termos: list[str]) -> bool:
    return any(normalizar(t) in texto for t in termos)


def tem_palavra(texto: str, termos: list[str]) -> bool:
    """Como _tem, mas com borda de palavra: "pl" nao casa em "planejamento"."""
    return any(re.search(rf"(?<![a-z0-9]){re.escape(normalizar(t).strip())}(?![a-z0-9])",
                         texto) for t in termos)


def filtrar(itens: list[Oportunidade], cfg: dict) -> list[Oportunidade]:
    mantidos = []
    for o in itens:
        if o.tipo == "estagio" and _passa_estagio(o, cfg):
            mantidos.append(o)
        elif o.tipo == "concurso" and _passa_concurso(o, cfg):
            mantidos.append(o)
    log.info("filtro de regras: %d -> %d", len(itens), len(mantidos))
    return mantidos


def _passa_estagio(o: Oportunidade, cfg: dict) -> bool:
    est = cfg["estagio"]
    texto = normalizar(o.texto_para_analise())

    # Nivel do cargo sai do titulo, nao do texto todo: a descricao cita
    # "senior"/"lead" o tempo todo sem que a vaga seja senior.
    if tem_palavra(normalizar(o.titulo), est.get("titulos_negativos", [])):
        return False
    if _tem(texto, est["keywords_negativas"]):
        return False
    if not _tem(texto, est["keywords_positivas"]):
        return False

    # Geografia: DF sempre; fora do DF so se for 100% remoto.
    local = normalizar(o.local)
    no_df = _tem(local, est["local"]["prioridade"])
    if not no_df and est["local"]["aceitar_fora_do_df_apenas_se_remoto"]:
        if not (o.remoto or "remoto" in texto):
            return False

    return True


def _passa_concurso(o: Oportunidade, cfg: dict) -> bool:
    conc = cfg["concursos"]
    texto = normalizar(o.texto_para_analise())

    if _tem(texto, conc["keywords_negativas"]):
        return False

    # Enquanto escolaridade for so [medio], exige sinal explicito de nivel medio.
    if "superior" not in cfg["escolaridade"]:
        if not _tem(texto, ["nivel medio", "ensino medio", "tecnico bancario",
                            "escriturario", "agente comercial"]):
            return False

    # Precisa mencionar algum orgao alvo.
    return _tem(texto, conc["orgaos"])


def marcar_alertas(itens: list[Oportunidade], cfg: dict) -> None:
    """Anota prazo apertado e empresa alvo. Nao filtra, so etiqueta."""
    limite = cfg["concursos"]["alerta_prazo_dias"]
    alvos = cfg["estagio"]["empresas_alvo"]

    for o in itens:
        d = o.dias_ate_prazo
        if d is not None and 0 <= d <= limite:
            o.alertas.append(f"fecha em {d} dia(s)")
        if o.tipo == "estagio" and _tem(normalizar(o.organizacao), alvos):
            o.alertas.append("empresa alvo")
