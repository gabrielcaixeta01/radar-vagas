"""Envio do relatorio por e-mail (SMTP).

Padrao pensado para Gmail com senha de app:
    SMTP_USER      seu.email@gmail.com
    SMTP_PASSWORD  senha de app de 16 letras (myaccount.google.com/apppasswords)
    EMAIL_TO       destinatario (opcional; padrao = SMTP_USER)
    SMTP_HOST / SMTP_PORT  opcionais; padrao smtp.gmail.com:465 (SSL)

Manda multipart: texto (o markdown) + HTML (o mesmo HTML do Telegram, com as
quebras de linha convertidas). Cliente de e-mail que nao renderiza HTML mostra
o markdown, que ja e legivel.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger(__name__)


def enviar_email(assunto: str, texto_md: str, texto_html: str) -> bool:
    usuario = os.environ.get("SMTP_USER")
    senha = os.environ.get("SMTP_PASSWORD")
    if not (usuario and senha):
        log.error("SMTP_USER ou SMTP_PASSWORD ausente — e-mail nao enviado")
        return False

    destino = os.environ.get("EMAIL_TO") or usuario
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    porta = int(os.environ.get("SMTP_PORT", "465"))

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = usuario
    msg["To"] = destino
    msg.set_content(texto_md)
    corpo = texto_html.replace("\n", "<br>\n")
    msg.add_alternative(
        f'<div style="font-family:-apple-system,Segoe UI,sans-serif;'
        f'font-size:14px;line-height:1.5">{corpo}</div>', subtype="html")

    try:
        if porta == 465:
            with smtplib.SMTP_SSL(host, porta, context=ssl.create_default_context(),
                                  timeout=30) as s:
                s.login(usuario, senha)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, porta, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(usuario, senha)
                s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        log.error("e-mail falhou: %s", e)
        return False

    log.info("e-mail enviado para %s", destino)
    return True
