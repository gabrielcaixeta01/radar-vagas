"""Vagas de estagio via python-jobspy.

Conferido contra o servico real em 27/08/2026, rodando scrape_jobs de verdade:

- INDEED FUNCIONA com country_indeed="Brazil". Devolve DataFrame populado e
  todas as colunas que o parser assume existem de fato: title, company,
  job_url, site, location, is_remote, description, date_posted.
  `location` vem como "Brasília, DF, BR"; `date_posted` ja e datetime.date.

- GLASSDOOR NAO FUNCIONA. Devolve HTTP 400 "Glassdoor: location not parsed".
  Testado com location "Brasília, DF", "Brasilia", "Brazil", "Brasilia, Brazil"
  e "São Paulo, Brazil" — os cinco deram 0 linhas. Nao e bloqueio de IP, e a
  resolucao de localidade do Brasil que a lib nao faz para esse portal.

- GOOGLE NAO FUNCIONA. 0 linhas com search_term sozinho e tambem com
  google_search_term em linguagem natural.

Por isso SITES tem so "indeed". Nao adianta reintroduzir os outros dois sem
antes rodar scrape_jobs e ver linha voltando — foi exatamente assim que a
versao anterior nasceu quebrada.

LinkedIn fica FORA por decisao de projeto: o ToS proibe scraping e o bloqueio
por IP e agressivo (o Actions roda em IP compartilhado da Azure).
"""

from __future__ import annotations

import logging
from datetime import date

from ..models import Oportunidade
from .base import Coletor

log = logging.getLogger(__name__)

SITES = ["indeed"]
HORAS = 24 * 8          # janela de 8 dias, roda semanal com margem
POR_TERMO = 25

# (location, is_remote). O filtro geografico real esta em filtros.py; aqui so
# garantimos que as duas buscas que interessam sejam feitas.
BUSCAS = (("Brasília, DF", False), ("Brazil", True))

# Colunas que _para_oportunidade le. Se o jobspy mudar o schema, o log avisa
# em vez de estourar KeyError no meio da execucao.
COLUNAS_ESPERADAS = ["title", "company", "job_url", "site", "location",
                     "is_remote", "description", "date_posted"]


class VagasColetor(Coletor):
    nome = "vagas"
    tipo = "estagio"

    def buscar(self) -> list[Oportunidade]:
        try:
            from jobspy import scrape_jobs
        except ImportError:
            log.error("jobspy nao instalado — rode: pip install python-jobspy")
            return []

        import pandas as pd  # vem junto com jobspy

        est = self.cfg["estagio"]
        quadros = []

        for termo in est["termos_busca"]:
            for local, remoto in BUSCAS:
                try:
                    df = scrape_jobs(
                        site_name=SITES,
                        search_term=termo,
                        location=local,
                        country_indeed="Brazil",
                        is_remote=remoto,
                        results_wanted=POR_TERMO,
                        hours_old=HORAS,
                        description_format="markdown",
                        verbose=0,
                    )
                except Exception as e:  # noqa: BLE001
                    log.warning("vagas: %r em %s falhou (%s)", termo, local, e)
                    continue

                if df is None or df.empty:
                    log.debug("vagas: %r em %s -> 0 linhas", termo, local)
                    continue

                log.debug("vagas: %r em %s -> %d linhas", termo, local, len(df))
                quadros.append(df)

        if not quadros:
            log.warning("vagas: nenhuma busca devolveu linha")
            return []

        df = pd.concat(quadros, ignore_index=True)

        if "job_url" in df.columns:
            df = df.drop_duplicates(subset=["job_url"])
        log.info("vagas: %d linhas apos dedup", len(df))

        faltando = [c for c in COLUNAS_ESPERADAS if c not in df.columns]
        if faltando:
            log.warning("vagas: jobspy mudou o schema, colunas ausentes: %s",
                        ", ".join(faltando))

        return [self._para_oportunidade(linha) for _, linha in df.iterrows()]

    def _para_oportunidade(self, r) -> Oportunidade:
        site = _txt(r.get("site"))
        return Oportunidade(
            tipo="estagio",
            titulo=_txt(r.get("title")),
            organizacao=_txt(r.get("company")),
            url=_txt(r.get("job_url")),
            fonte=f"{self.nome}:{site}" if site else self.nome,
            local=_txt(r.get("location")),
            remoto=_bool(r.get("is_remote")),
            descricao=_txt(r.get("description"))[:4000],
            publicado_em=_data(r.get("date_posted")),
        )


def _txt(v) -> str:
    import pandas as pd
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):  # arrays/listas nao respondem a isna
        pass
    return str(v)


def _bool(v) -> bool:
    import pandas as pd
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    return bool(v)


def _data(v) -> date | None:
    if v is None:
        return None
    try:
        import pandas as pd
        if pd.isna(v):
            return None
        return pd.to_datetime(v).date()
    except Exception:  # noqa: BLE001
        return None
