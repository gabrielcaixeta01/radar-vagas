"""Diario Oficial da Uniao (in.gov.br).

Tudo aqui foi conferido contra o servico real em 27/08/2026. As tres correcoes
que fizeram a versao anterior devolver zero:

1. SECAO ERRADA. O codigo antigo lia `secao=do1`. A Secao 1 e so ato normativo
   (Despacho, Portaria, Decisao, Resolucao): no indice de 26/08/2026, 377 itens
   e ZERO ocorrencias da palavra "concurso". Edital de concurso sai na Secao 3
   — no mesmo dia, 2242 itens, 82 do artType "Edital" e 31 batendo
   concurso/processo seletivo.

2. CONTENT TRUNCADO. O `content` do indice e capado em 403 caracteres e 96% dos
   itens terminam em "...". Nao da para achar prazo de inscricao ali. O texto
   completo so existe na materia individual (/web/dou/-/{urlTitle}), que
   devolve ~1000-6500 chars dentro de <div class="texto-dou">.

3. USER-AGENT. O UA do projeto leva 403 do in.gov.br. Com UA de navegador
   passa. Por isso o header e sobrescrito nas duas chamadas.

Sobre volume: buscar a materia de todos os candidatos seria caro, entao o
indice e pre-filtrado localmente (barato) e so o que sobra vira requisicao.
O gate de orgao alvo e de nivel medio NAO e feito aqui de proposito — quem faz
isso e filtros.py, a partir do config.yaml. Duplicar o filtro no coletor foi
parte do que fazia o pipeline zerar.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from datetime import date, timedelta

from ..models import Oportunidade
from .base import Coletor

log = logging.getLogger(__name__)

LEITURA = "https://www.in.gov.br/leiturajornal"
BASE_MATERIA = "https://www.in.gov.br/web/dou/-/"

# Secao 3 = editais, avisos e contratos. Validado: e onde estao os concursos.
SECAO = "do3"
DIAS_JANELA = 8

# UA de navegador: com o UA do projeto o in.gov.br devolve 403.
UA_NAVEGADOR = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36")
CABECALHOS = {
    "User-Agent": UA_NAVEGADOR,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Passo 1: o item fala de concurso?
GATILHOS = re.compile(r"concurso p[uú]blico|processo seletivo", re.I)

# Passo 2: e abertura, ou so movimentacao de concurso antigo? O indice de um dia
# tipico tem ~31 itens de concurso, dos quais ~24 sao ruido de ciclo de vida.
RUIDO = re.compile(
    r"retifica|homologa|resultado|prorroga[cç]|convoca|classifica|"
    r"anula|revoga|exame m[eé]dico|pr[eé]-admissional|"
    r"nomea[cç]|posse|desist[eê]ncia", re.I)

# Teto de materias buscadas por execucao. A 1 req/s, 60 = ~1 min de rede.
MAX_MATERIAS = 60


def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in txt if not unicodedata.combining(c)).lower()


class DOUColetor(Coletor):
    nome = "dou"
    tipo = "concurso"

    def buscar(self) -> list[Oportunidade]:
        candidatos = self._candidatos()
        log.info("dou: %d candidatos no indice apos pre-filtro", len(candidatos))

        if len(candidatos) > MAX_MATERIAS:
            log.warning("dou: %d candidatos, buscando so os %d mais recentes",
                        len(candidatos), MAX_MATERIAS)
            candidatos = candidatos[:MAX_MATERIAS]

        out: list[Oportunidade] = []
        for dia, item in candidatos:
            slug = (item.get("urlTitle") or "").lstrip("/")
            titulo = _limpar(item.get("title") or "")
            hierarquia = _limpar(item.get("hierarchyStr") or "")

            # O content do indice e truncado; o texto util esta na materia.
            corpo = self._materia(slug) or _limpar(item.get("content") or "")

            out.append(Oportunidade(
                tipo="concurso",
                titulo=titulo or "Publicacao DOU",
                organizacao=_orgao(hierarquia),
                url=BASE_MATERIA + slug,
                fonte=self.nome,
                descricao=corpo or hierarquia,
                publicado_em=dia,
                prazo=_prazo(corpo),
            ))

        return out

    def _candidatos(self) -> list[tuple[date, dict]]:
        """Varre a janela de dias e devolve (dia, item) que parecem abertura."""
        vistos: set[str] = set()
        candidatos: list[tuple[date, dict]] = []

        for dia in self._dias_uteis():
            for item in self._indice(dia):
                slug = item.get("urlTitle") or ""
                if not slug or slug in vistos:
                    continue

                # O gatilho olha titulo + content + hierarquia. O content vem
                # truncado, mas os 403 chars iniciais bastam para classificar.
                texto = " ".join([
                    item.get("title") or "",
                    item.get("content") or "",
                    item.get("hierarchyStr") or "",
                ])
                if not GATILHOS.search(texto) or RUIDO.search(texto):
                    continue

                vistos.add(slug)
                candidatos.append((dia, item))

        return candidatos

    def _dias_uteis(self) -> list[date]:
        hoje = date.today()
        dias = [hoje - timedelta(days=i) for i in range(DIAS_JANELA)]
        return [d for d in dias if d.weekday() < 5]  # DOU nao sai fim de semana

    def _indice(self, dia: date) -> list[dict]:
        try:
            r = self.get(LEITURA,
                         params={"data": dia.strftime("%d-%m-%Y"), "secao": SECAO},
                         headers=CABECALHOS)
        except Exception as e:  # noqa: BLE001
            log.warning("dou: indice %s falhou (%s)", dia, e)
            return []

        itens = _extrair_params(r.text)
        if itens is None:
            log.warning("dou: %s sem <script id=params> utilizavel", dia)
            return []

        log.debug("dou: %s -> %d itens no indice", dia, len(itens))
        return itens

    def _materia(self, slug: str) -> str:
        """Texto completo da publicacao. Sem isso nao ha prazo para extrair."""
        if not slug:
            return ""
        try:
            r = self.get(BASE_MATERIA + slug, headers=CABECALHOS, tentativas=2)
        except Exception as e:  # noqa: BLE001
            log.debug("dou: materia %s falhou (%s)", slug, e)
            return ""
        finally:
            time.sleep(1)  # teto de 1 req/s no in.gov.br

        return _texto_materia(r.text)


def _extrair_params(html: str) -> list[dict] | None:
    m = re.search(r'<script[^>]*id="params"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("jsonArray", [])
    except json.JSONDecodeError as e:
        log.warning("dou: JSON do params invalido (%s)", e)
        return None


def _texto_materia(html: str) -> str:
    """Extrai <div class="texto-dou">. Se o layout mudar, cai para a pagina toda
    em vez de devolver vazio — melhor um texto sujo que nenhum."""
    m = re.search(r'<div[^>]*class="[^"]*texto-dou[^"]*"[^>]*>(.*?)</div>\s*</div>',
                  html, re.S)
    return _limpar(m.group(1) if m else html)


def _limpar(txt: str) -> str:
    txt = re.sub(r"<(script|style)\b.*?</\1>", " ", txt or "", flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", txt).strip()


def _orgao(hierarquia: str) -> str:
    """hierarchyStr vem como "Ministerio X/Autarquia Y/Setor Z". O nivel mais
    especifico costuma ser setor interno, entao o orgao util e o do meio."""
    partes = [p.strip() for p in hierarquia.split("/") if p.strip()]
    if not partes:
        return "—"
    return partes[1] if len(partes) > 1 else partes[0]


MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5,
         "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
         "novembro": 11, "dezembro": 12}

# "inscricoes ... ate 15/09/2026" e "inscricoes ... ate 15 de setembro de 2026".
PADRAO_PRAZO = re.compile(
    r"inscri\w+.{0,200}?at[ée]\s+(?:as\s+\d{1,2}\S*\s+(?:horas?\s+)?d[eo]\s+)?"
    r"(?:dia\s+)?(\d{1,2})\s*(?:/|\s+de\s+)\s*"
    r"(\d{1,2}|janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\s*(?:/|\s+de\s+)\s*(\d{4})",
    re.I | re.S)


def _prazo(corpo: str) -> date | None:
    m = PADRAO_PRAZO.search(corpo or "")
    if not m:
        return None
    dia, mes_raw, ano = m.groups()
    mes = int(mes_raw) if mes_raw.isdigit() else MESES.get(_norm(mes_raw))
    if not mes:
        return None
    try:
        return date(int(ano), mes, int(dia))
    except ValueError:
        return None
