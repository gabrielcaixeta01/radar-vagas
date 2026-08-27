"""Estado de itens ja vistos.

JSON simples versionado no repo: auditavel, sem banco, e o proprio git guarda
o historico. Se um dia passar de uns milhares de linhas, migre para SQLite.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from .models import Oportunidade

log = logging.getLogger(__name__)

RETENCAO_DIAS = 180  # depois disso a vaga ja fechou; esquecer evita o arquivo crescer


def carregar(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("seen.json corrompido — recomecando do zero")
        return {}


def novos(itens: list[Oportunidade], vistos: dict[str, str]) -> list[Oportunidade]:
    return [o for o in itens if o.id not in vistos]


def salvar(caminho: Path, vistos: dict[str, str],
           itens: list[Oportunidade]) -> None:
    hoje = date.today()
    atualizado = dict(vistos)
    for o in itens:
        atualizado[o.id] = hoje.isoformat()

    corte = (hoje - timedelta(days=RETENCAO_DIAS)).isoformat()
    atualizado = {k: v for k, v in atualizado.items() if v >= corte}

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(atualizado, indent=1, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    log.info("estado: %d ids", len(atualizado))
