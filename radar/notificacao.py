from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

LIMITE_TELEGRAM = 4096  # limite duro da API


def enviar_telegram(texto: str) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        log.error("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID ausente")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = True
    for pedaco in _fatiar(texto):
        try:
            r = httpx.post(url, json={
                "chat_id": chat_id,
                "text": pedaco,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=30)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            log.error("telegram falhou: %s", e)
            ok = False
    return ok


def _fatiar(texto: str) -> list[str]:
    """Quebra em blocos respeitando linhas, para nao cortar tag HTML no meio."""
    if len(texto) <= LIMITE_TELEGRAM:
        return [texto]

    pedacos, atual = [], ""
    for linha in texto.split("\n"):
        if len(atual) + len(linha) + 1 > LIMITE_TELEGRAM:
            pedacos.append(atual)
            atual = linha
        else:
            atual = f"{atual}\n{linha}" if atual else linha
    if atual:
        pedacos.append(atual)
    return pedacos
