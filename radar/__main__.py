"""Ponto de entrada.

    python -m radar --dry-run --sem-llm      # imprime no terminal, nao grava
    python -m radar --fonte gupy --dry-run   # testa um coletor isolado
    python -m radar                          # gera relatorios/AAAA-MM-DD.md
    python -m radar --destino telegram       # envia no Telegram (opcional)
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import config, dedup, filtros, ranking, relatorio, saida
from .coletores import coletar_todos, montar


def main() -> int:
    p = argparse.ArgumentParser(prog="radar")
    p.add_argument("--dry-run", action="store_true",
                   help="imprime no terminal sem gravar arquivo nem estado")
    p.add_argument("--fonte", help="roda so um coletor (gupy, dou, querido-diario)")
    p.add_argument("--sem-llm", action="store_true", help="pula o ranking")
    p.add_argument("--destino", default="arquivo",
                   choices=["arquivo", "telegram", "ambos"],
                   help="onde entregar o relatorio (padrao: arquivo)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")

    cfg = config.carregar()
    if args.sem_llm:
        cfg["ranking"]["usar_llm"] = False

    # 1. coleta
    itens = coletar_todos(montar(cfg, args.fonte))
    logging.info("coletados: %d", len(itens))

    # 2. filtro barato
    itens = filtros.filtrar(itens, cfg)

    # 3. dedup — separa novidades do que ja foi reportado
    vistos = dedup.carregar(config.CAMINHO_ESTADO)
    novidades = dedup.novos(itens, vistos)
    logging.info("novos: %d", len(novidades))

    # 4. ranking (so nas novidades; reavaliar o antigo seria pagar duas vezes)
    novidades = ranking.rankear(novidades, cfg)
    filtros.marcar_alertas(novidades, cfg)
    aprovados = ranking.selecionar(novidades, cfg)

    # 5. prazos fechando: vale lembrar mesmo que ja tenha sido reportado antes
    limite = cfg["concursos"]["alerta_prazo_dias"]
    fechando = [o for o in itens
                if o.dias_ate_prazo is not None
                and 0 <= o.dias_ate_prazo <= limite
                and o.id not in {a.id for a in aprovados}]
    filtros.marcar_alertas(fechando, cfg)

    # 6. entrega
    texto_md = relatorio.montar(aprovados, fechando, cfg, formato="markdown")

    if args.dry_run:
        print("\n" + texto_md)
        print(f"\n--- dry-run: {len(aprovados)} aprovados, "
              f"{len(fechando)} fechando (nada foi gravado) ---")
        return 0

    ok = True
    if args.destino in ("arquivo", "ambos"):
        saida.salvar_arquivo(texto_md, config.PASTA_RELATORIOS)
        saida.escrever_resumo_actions(texto_md)

    if args.destino in ("telegram", "ambos"):
        from .notificacao import enviar_telegram
        texto_html = relatorio.montar(aprovados, fechando, cfg, formato="html")
        ok = enviar_telegram(texto_html)

    if not ok:
        return 1

    dedup.salvar(config.CAMINHO_ESTADO, vistos, itens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
