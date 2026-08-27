from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..models import Oportunidade

log = logging.getLogger(__name__)

UA = "radar-vagas/0.1 (projeto pessoal de estudo; contato via GitHub)"


class Coletor:
    """Interface unica. Todo coletor implementa buscar()."""

    nome: str = "base"
    tipo: str = "estagio"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def buscar(self) -> list[Oportunidade]:
        raise NotImplementedError

    # --- utilitarios compartilhados ---

    def get(self, url: str, *, params: dict | None = None,
            headers: dict | None = None, tentativas: int = 3) -> httpx.Response:
        """GET com retry e backoff. Rate limit basico entre chamadas."""
        h = {"User-Agent": UA, "Accept": "application/json, text/html;q=0.9"}
        if headers:
            h.update(headers)

        ultimo_erro: Exception | None = None
        for i in range(tentativas):
            try:
                r = httpx.get(url, params=params, headers=h,
                              timeout=30, follow_redirects=True)
                if r.status_code == 429:
                    espera = 2 ** (i + 2)
                    log.warning("%s: 429, esperando %ss", self.nome, espera)
                    time.sleep(espera)
                    continue
                r.raise_for_status()
                time.sleep(1)  # educado com o servidor
                return r
            except Exception as e:  # noqa: BLE001
                ultimo_erro = e
                log.warning("%s: tentativa %d falhou (%s)", self.nome, i + 1, e)
                time.sleep(2 ** i)

        raise RuntimeError(f"{self.nome}: falhou apos {tentativas} tentativas") from ultimo_erro


def coletar_todos(coletores: list[Coletor]) -> list[Oportunidade]:
    """Roda todos os coletores. Um quebrado nao derruba a execucao inteira —
    isso importa porque scraper de HTML quebra sozinho quando o site muda."""
    resultados: list[Oportunidade] = []
    for c in coletores:
        try:
            itens = c.buscar()
            log.info("%s: %d itens", c.nome, len(itens))
            resultados.extend(itens)
        except Exception as e:  # noqa: BLE001
            log.error("%s: FALHOU — %s", c.nome, e)
    return resultados
