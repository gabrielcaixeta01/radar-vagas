"""Diario Oficial da Uniao (in.gov.br) — fonte primaria de editais.

O edital aparece aqui antes de chegar nos agregadores. A pagina de busca do
in.gov.br embute o resultado num <script id="params"> com JSON dentro, o que e
mais estavel do que raspar a lista renderizada.

Cobre orgaos federais (Caixa, BB, Correios, Camara, Senado). NAO cobre
distrital/estadual — para CLDF, BRB e Metro-DF veja o coletor `dodf`.

Teste isolado:
    python -m radar --fonte dou --dry-run
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

from ..models import Oportunidade
from .base import Coletor

log = logging.getLogger(__name__)

BUSCA = "https://www.in.gov.br/consulta/-/buscar/dou"
DIAS_JANELA = 10  # roda semanal; margem cobre feriado e atraso do workflow


class DOUColetor(Coletor):
    nome = "dou"
    tipo = "concurso"

    def buscar(self) -> list[Oportunidade]:
        conc = self.cfg["concursos"]
        fim = date.today()
        inicio = fim - timedelta(days=DIAS_JANELA)
        vistos: set[str] = set()
        out: list[Oportunidade] = []

        for termo in conc["termos_busca"]:
            for item in self._buscar_termo(termo, inicio, fim):
                url = item.get("urlTitulo") or ""
                if url and not url.startswith("http"):
                    url = f"https://www.in.gov.br/web/dou/-/{url.lstrip('/')}"
                if not url or url in vistos:
                    continue
                vistos.add(url)

                titulo = _limpar(item.get("title", ""))
                corpo = _limpar(item.get("content", "") or item.get("abstract", ""))

                out.append(Oportunidade(
                    tipo="concurso",
                    titulo=titulo,
                    organizacao=_orgao(item, titulo, corpo, conc["orgaos"]),
                    url=url,
                    fonte=self.nome,
                    descricao=corpo,
                    publicado_em=_data(item.get("pubDate")),
                    prazo=_prazo(corpo),
                ))

        return out

    def _buscar_termo(self, termo: str, inicio: date, fim: date) -> list[dict]:
        params = {
            "q": termo,
            "s": "do1,do2,do3",
            "exactDate": "personalizado",
            "publishFrom": inicio.strftime("%d-%m-%Y"),
            "publishTo": fim.strftime("%d-%m-%Y"),
            "sortType": "0",
        }
        try:
            r = self.get(BUSCA, params=params,
                         headers={"Accept": "text/html"})
        except Exception as e:  # noqa: BLE001
            log.warning("dou: termo %r falhou (%s)", termo, e)
            return []

        m = re.search(
            r'<script[^>]*id="params"[^>]*>(.*?)</script>', r.text, re.S)
        if not m:
            log.warning("dou: <script id=params> nao encontrado — "
                        "o layout do in.gov.br provavelmente mudou")
            return []

        try:
            return json.loads(m.group(1)).get("jsonArray", [])
        except json.JSONDecodeError as e:
            log.warning("dou: JSON invalido (%s)", e)
            return []


def _limpar(txt: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt or "")).strip()


def _orgao(item: dict, titulo: str, corpo: str, alvos: list[str]) -> str:
    texto = f"{titulo} {corpo} {item.get('hierarchyStr', '')}".lower()
    for alvo in alvos:
        if alvo.lower() in texto:
            return alvo
    return item.get("hierarchyStr", "").split("/")[-1].strip() or "—"


def _data(valor) -> date | None:
    if not valor:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(valor)[:10], fmt).date()
        except ValueError:
            continue
    return None


PADRAO_PRAZO = re.compile(
    r"(?:inscri\w+|per[ií]odo).{0,120}?at[ée]\s+(?:o dia\s+)?(\d{1,2})[/\s.de]+"
    r"(\d{1,2}|janeiro|fevereiro|mar\wo|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)[/\s.de]+(\d{4})",
    re.I | re.S)

MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
         "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
         "outubro": 10, "novembro": 11, "dezembro": 12}


def _prazo(corpo: str) -> date | None:
    """Extrai a data-limite de inscricao. Heuristica: acerta a maioria,
    erra em edital com redacao incomum. O relatorio sempre linka o original."""
    m = PADRAO_PRAZO.search(corpo or "")
    if not m:
        return None
    dia, mes_raw, ano = m.groups()
    mes = MESES.get(mes_raw.lower()) if not mes_raw.isdigit() else int(mes_raw)
    if not mes:
        return None
    try:
        return date(int(ano), mes, int(dia))
    except ValueError:
        return None
