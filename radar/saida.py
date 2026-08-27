"""Destinos do relatorio.

Padrao e arquivo: grava relatorios/AAAA-MM-DD.md no repo e, quando roda no
GitHub Actions, tambem escreve no resumo da execucao (aquela pagina que abre
ao clicar no workflow). Nenhum dos dois precisa de token ou configuracao.

Telegram continua disponivel via --destino telegram, mas e opcional.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)


def salvar_arquivo(texto: str, pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{date.today().isoformat()}.md"
    caminho.write_text(texto, encoding="utf-8")
    log.info("relatorio salvo em %s", caminho)

    # ultimo.md sempre aponta para o mais recente — link fixo para favoritar
    (pasta / "ultimo.md").write_text(texto, encoding="utf-8")
    return caminho


def escrever_resumo_actions(texto: str) -> bool:
    """GITHUB_STEP_SUMMARY aceita markdown e renderiza na pagina do workflow."""
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if not destino:
        return False
    with open(destino, "a", encoding="utf-8") as f:
        f.write(texto + "\n")
    log.info("resumo escrito no GitHub Actions")
    return True
