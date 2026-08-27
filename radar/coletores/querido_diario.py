"""Querido Diario — API publica e aberta (Open Knowledge Brasil).

Cobre diarios oficiais do executivo municipal/distrital. Serve para pegar
concursos do DF (CLDF, Metro-DF, BRB e demais orgaos distritais) que nao
saem no DOU.

Vantagem sobre raspar o DODF direto: e API estavel, documentada e com licenca
aberta — nao quebra com mudanca de layout nem esbarra em termos de uso.
Docs: https://docs.queridodiario.ok.org.br/pt-br/latest/utilizando/api-publica.html
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from ..models import Oportunidade
from .base import Coletor

log = logging.getLogger(__name__)

ENDPOINT = "https://queridodiario.ok.org.br/api/gazettes"
BRASILIA_IBGE = "5300108"
DIAS_JANELA = 10


class QueridoDiarioColetor(Coletor):
    nome = "querido-diario"
    tipo = "concurso"

    def buscar(self) -> list[Oportunidade]:
        conc = self.cfg["concursos"]
        fim = date.today()
        inicio = fim - timedelta(days=DIAS_JANELA)
        vistos: set[str] = set()
        out: list[Oportunidade] = []

        for termo in conc["termos_busca"]:
            try:
                r = self.get(ENDPOINT, params={
                    "territory_ids": BRASILIA_IBGE,
                    "querystring": termo,
                    "published_since": inicio.isoformat(),
                    "published_until": fim.isoformat(),
                    "excerpt_size": 800,
                    "number_of_excerpts": 2,
                    "size": 20,
                })
                itens = r.json().get("gazettes", [])
            except Exception as e:  # noqa: BLE001
                log.warning("querido-diario: termo %r falhou (%s)", termo, e)
                continue

            for g in itens:
                url = g.get("txt_url") or g.get("url") or ""
                if not url or url in vistos:
                    continue
                vistos.add(url)

                trechos = " […] ".join(g.get("excerpts", []) or [])
                out.append(Oportunidade(
                    tipo="concurso",
                    titulo=f"Diario Oficial DF — edicao {g.get('edition') or 's/n'}",
                    organizacao=g.get("territory_name", "Distrito Federal"),
                    url=url,
                    fonte=self.nome,
                    local="Brasilia, DF",
                    descricao=trechos,
                    publicado_em=_data(g.get("date")),
                ))

        return out


def _data(valor) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None
