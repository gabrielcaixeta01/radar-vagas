"""Renderiza o relatorio de segunda-feira.

Duas secoes: novidades e prazos fechando. A segunda existe porque o jeito mais
comum de perder uma vaga nao e nao ficar sabendo — e ficar sabendo e esquecer.

Dois formatos a partir da mesma estrutura:
    markdown -> arquivo no repo e resumo do GitHub Actions
    html     -> Telegram (opcional)
"""

from __future__ import annotations

import html as _html
from datetime import date

from .models import Oportunidade

MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


# --- markdown -------------------------------------------------------------

def _esc_md(txt: str) -> str:
    for c in ("[", "]", "*", "_"):
        txt = txt.replace(c, "\\" + c)
    return txt


def _linha_md(o: Oportunidade) -> str:
    partes = [f"- **[{_esc_md(o.titulo[:110])}]({o.url})**"]

    meta = [f"`{o.organizacao[:60]}`"]
    if o.local:
        meta.append(o.local)
    if o.remoto:
        meta.append("remoto")
    if o.nota is not None:
        meta.append(f"nota {o.nota}")
    partes.append("  " + " · ".join(meta))

    if o.alertas:
        partes.append("  ⚠️ " + " · ".join(o.alertas))
    if o.motivo:
        partes.append(f"  _{_esc_md(o.motivo[:140])}_")

    return "  \n".join(partes)


def _secao_md(titulo: str, itens: list[Oportunidade], limite: int) -> list[str]:
    if not itens:
        return []
    bloco = [f"\n## {titulo} ({len(itens)})\n"]
    bloco += [_linha_md(o) for o in itens[:limite]]
    if len(itens) > limite:
        bloco.append(f"\n_… e mais {len(itens) - limite}_")
    return bloco


# --- html (telegram) ------------------------------------------------------

def _linha_html(o: Oportunidade) -> str:
    titulo = _html.escape(o.titulo[:110])
    org = _html.escape(o.organizacao[:60])
    partes = [f'• <a href="{_html.escape(o.url, quote=True)}">{titulo}</a>',
              f"  <b>{org}</b>"]

    meta = []
    if o.local:
        meta.append(_html.escape(o.local))
    if o.remoto:
        meta.append("remoto")
    if o.nota is not None:
        meta.append(f"nota {o.nota}")
    if meta:
        partes[1] += " — " + " · ".join(meta)

    if o.alertas:
        partes.append("  ⚠ " + " · ".join(_html.escape(a) for a in o.alertas))
    if o.motivo:
        partes.append(f"  <i>{_html.escape(o.motivo[:140])}</i>")

    return "\n".join(partes)


def _secao_html(titulo: str, itens: list[Oportunidade], limite: int) -> list[str]:
    if not itens:
        return []
    bloco = [f"\n<b>{titulo}</b> ({len(itens)})\n"]
    bloco += [_linha_html(o) for o in itens[:limite]]
    if len(itens) > limite:
        bloco.append(f"\n<i>… e mais {len(itens) - limite}</i>")
    return bloco


# --- entrada publica ------------------------------------------------------

def montar(novos: list[Oportunidade], fechando: list[Oportunidade],
           cfg: dict, formato: str = "markdown") -> str:
    hoje = date.today()
    limite = cfg["ranking"]["max_itens_por_secao"]

    estagios = [o for o in novos if o.tipo == "estagio"]
    concursos = [o for o in novos if o.tipo == "concurso"]

    if formato == "html":
        partes = [f"<b>📡 Radar — {hoje.day} de {MESES[hoje.month]}</b>"]
        partes += _secao_html("🎯 Estágios, trainee e júnior", estagios, limite)
        partes += _secao_html("📋 Concursos", concursos, limite)
        partes += _secao_html("⏰ Prazo fechando", fechando, limite)
    else:
        partes = [f"# 📡 Radar — {hoje.day} de {MESES[hoje.month]} de {hoje.year}"]
        partes += _secao_md("🎯 Estágios, trainee e júnior", estagios, limite)
        partes += _secao_md("📋 Concursos", concursos, limite)
        partes += _secao_md("⏰ Prazo fechando", fechando, limite)

    if not (estagios or concursos or fechando):
        partes.append("\nNada novo esta semana.")

    return "\n".join(partes)
