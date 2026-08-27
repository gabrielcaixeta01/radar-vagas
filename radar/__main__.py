"""Ponto de entrada.

    python -m radar --dry-run             # imprime no terminal, nao envia, nao salva
    python -m radar --fonte gupy --dry-run  # testa um coletor isolado
    python -m radar --sem-llm --dry-run     # sem gastar API
    python -m radar                         # execucao real
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import config, dedup, filtros, ranking, relatorio
from .coletores import coletar_todos, montar
from .notificacao import enviar_telegram


def main() -> int:
    p = argparse.ArgumentParser(prog="radar")
    p.add_argument("--dry-run", action="store_true",
                   help="imprime no terminal sem enviar nem gravar estado")
    p.add_argument("--fonte", help="roda so um coletor (gupy, dou, querido-diario)")
    p.add_argument("--sem-llm", action="store_true", help="pula o ranking")
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

    # 6. relatorio
    texto = relatorio.montar(aprovados, fechando, cfg)

    if args.dry_run:
        print("\n--- RELATORIO (dry-run) ---\n")
        print(texto)
        print(f"\n--- {len(aprovados)} aprovados, {len(fechando)} fechando ---")
        return 0

    if not enviar_telegram(texto):
        return 1

    dedup.salvar(config.CAMINHO_ESTADO, vistos, itens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
