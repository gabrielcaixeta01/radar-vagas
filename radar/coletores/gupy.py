"""Gupy — maior concentrador de vagas de tech no Brasil.

A busca publica do portal (portal.gupy.io) e alimentada por uma API JSON.
Ela nao e documentada, entao PODE MUDAR sem aviso. Se este coletor comecar a
voltar zero itens, abra portal.gupy.io no navegador, aba Network, faca uma
busca e confira o endpoint e os nomes dos campos.

Teste isolado:
    python -m radar --fonte gupy --dry-run
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..models import Oportunidade
from .base import Coletor

log = logging.getLogger(__name__)

ENDPOINT = "https://portal.api.gupy.io/api/job"


class GupyColetor(Coletor):
    nome = "gupy"
    tipo = "estagio"

    def buscar(self) -> list[Oportunidade]:
        est = self.cfg["estagio"]
        vistos: set[str] = set()
        out: list[Oportunidade] = []

        for termo in est["termos_busca"]:
            try:
                r = self.get(ENDPOINT, params={
                    "name": termo,
                    "offset": 0,
                    "limit": 100,
                })
                dados = r.json().get("data", [])
            except Exception as e:  # noqa: BLE001
                log.warning("gupy: termo %r falhou (%s)", termo, e)
                continue

            for j in dados:
                url = j.get("jobUrl") or j.get("url") or ""
                if not url or url in vistos:
                    continue
                vistos.add(url)
                out.append(self._para_oportunidade(j, url))

        return out

    def _para_oportunidade(self, j: dict, url: str) -> Oportunidade:
        cidade = j.get("city") or ""
        uf = j.get("state") or ""
        local = ", ".join(p for p in (cidade, uf) if p)

        workplace = (j.get("workplaceType") or "").lower()
        remoto = workplace == "remote" or bool(j.get("isRemoteWork"))

        return Oportunidade(
            tipo="estagio",
            titulo=j.get("name", ""),
            organizacao=j.get("careerPageName") or j.get("companyName") or "",
            url=url,
            fonte=self.nome,
            local=local,
            remoto=remoto,
            descricao=_limpar_html(j.get("description", "")),
            publicado_em=_data(j.get("publishedDate")),
        )


def _limpar_html(txt: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", txt or "").replace("&nbsp;", " ").strip()


def _data(valor) -> "datetime.date | None":
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).date()
    except ValueError:
        return None
