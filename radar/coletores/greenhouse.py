"""Vagas direto do ATS das empresas, via API pública do Greenhouse.

    GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true

Sem token, sem scraping: é a API que o próprio site de carreiras da empresa
consome. Validado em 04/11/2026 — boards ativos: stone, c6bank, inter,
btgpactual, xpinc, quintoandar, ebanx, vtex, wildlifestudios. Devolveram 404
(não usam Greenhouse): ifood, mercadolivre, picpay, pagbank, creditas, neon.
`nubank` responde 200 mas com 0 vagas — o board existe e está vazio.

A API devolve TODAS as vagas abertas (BTG tem ~250), não só as de entrada. O
corte por nível e geografia é do filtro de regras, como para as outras fontes.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import date

from ..models import Oportunidade
from .base import Coletor

log = logging.getLogger(__name__)

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
_TAG = re.compile(r"<[^>]+>")


class GreenhouseColetor(Coletor):
    nome = "greenhouse"
    tipo = "estagio"

    def buscar(self) -> list[Oportunidade]:
        from ..filtros import normalizar, tem_palavra

        gh = self.cfg.get("greenhouse", {})
        boards, entrada = gh.get("boards", []), gh.get("titulos_entrada", [])
        itens: list[Oportunidade] = []
        for b in boards:
            board, empresa = b["board"], b.get("empresa", b["board"])
            try:
                r = self.get(API.format(board=board), params={"content": "true"})
                vagas = r.json().get("jobs", [])
            except Exception as e:  # noqa: BLE001 — um board fora nao derruba os outros
                log.warning("greenhouse:%s falhou (%s)", board, e)
                continue
            if entrada:
                vagas = [v for v in vagas
                         if tem_palavra(normalizar(v.get("title", "")), entrada)]
            log.debug("greenhouse:%s: %d vagas de entrada", board, len(vagas))
            itens += [self._para_oportunidade(v, board, empresa) for v in vagas]
        return itens

    def _para_oportunidade(self, v: dict, board: str, empresa: str) -> Oportunidade:
        local = (v.get("location") or {}).get("name", "")
        modelo = " ".join(str(m.get("value", "")) for m in v.get("metadata") or []
                          if "work" in str(m.get("name", "")).lower())
        remoto = bool(re.search(r"remot", f"{local} {modelo}", re.I))
        return Oportunidade(
            tipo="estagio",
            titulo=v.get("title", "").strip(),
            organizacao=empresa,
            url=v.get("absolute_url", ""),
            fonte=f"greenhouse:{board}",
            local=local,
            remoto=remoto,
            descricao=_texto(v.get("content", ""))[:4000],
            publicado_em=_data(v.get("updated_at")),
        )


def _texto(conteudo: str) -> str:
    # O campo vem com HTML escapado duas vezes: &lt;p&gt; -> <p> -> texto.
    t = _TAG.sub(" ", html.unescape(html.unescape(conteudo or "")))
    return re.sub(r"\s+", " ", t).strip()


def _data(v: str | None) -> date | None:
    try:
        return date.fromisoformat((v or "")[:10])
    except ValueError:
        return None
