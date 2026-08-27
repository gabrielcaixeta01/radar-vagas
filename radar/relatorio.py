"""Renderiza o relatorio de segunda-feira.

Duas secoes: novidades e prazos fechando. A segunda existe porque o jeito mais
comum de perder uma vaga nao e nao ficar sabendo — e ficar sabendo e esquecer.
"""

from __future__ import annotations

import html
from datetime import date

from .models import Oportunidade

MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _linha(o: Oportunidade) -> str:
    titulo = html.escape(o.titulo[:110])
    org = html.escape(o.organizacao[:60])
    partes = [f'• <a href="{html.escape(o.url, quote=True)}">{titulo}</a>',
              f"  <b>{org}</b>"]

    meta = []
    if o.local:
        meta.append(html.escape(o.local))
    if o.remoto:
        meta.append("remoto")
    if o.nota is not None:
        meta.append(f"nota {o.nota}")
    if meta:
        partes[1] += " — " + " · ".join(meta)

    if o.alertas:
        partes.append("  ⚠ " + " · ".join(html.escape(a) for a in o.alertas))
    if o.motivo:
        partes.append(f"  <i>{html.escape(o.motivo[:140])}</i>")

    return "\n".join(partes)


def _secao(titulo: str, itens: list[Oportunidade], limite: int) -> list[str]:
    if not itens:
        return []
    bloco = [f"\n<b>{titulo}</b> ({len(itens)})\n"]
    bloco += [_linha(o) for o in itens[:limite]]
    if len(itens) > limite:
        bloco.append(f"\n<i>… e mais {len(itens) - limite}</i>")
    return bloco


def montar(novos: list[Oportunidade], fechando: list[Oportunidade],
           cfg: dict) -> str:
    hoje = date.today()
    limite = cfg["ranking"]["max_itens_por_secao"]

    partes = [f"<b>📡 Radar — {hoje.day} de {MESES[hoje.month]}</b>"]

    estagios = [o for o in novos if o.tipo == "estagio"]
    concursos = [o for o in novos if o.tipo == "concurso"]

    partes += _secao("🎯 Estágios", estagios, limite)
    partes += _secao("📋 Concursos", concursos, limite)
    partes += _secao("⏰ Prazo fechando", fechando, limite)

    if not (estagios or concursos or fechando):
        partes.append("\nNada novo esta semana.")

    return "\n".join(partes)
