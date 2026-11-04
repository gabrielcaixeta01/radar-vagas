from .base import Coletor, coletar_todos
from .dou import DOUColetor
from .greenhouse import GreenhouseColetor
from .vagas import VagasColetor

# querido-diario foi REMOVIDO: a API tem o DF na base (territory 5300108,
# 1455 diarios), mas a coleta parou em 2025-03-28 — published_since=2025-04-01
# devolve 0. Para um radar semanal de editais abertos a fonte esta morta.
# Ver README (secao "Fontes descartadas") antes de tentar reativar.
REGISTRO: dict[str, type[Coletor]] = {
    "vagas": VagasColetor,
    "greenhouse": GreenhouseColetor,
    "dou": DOUColetor,
}


def montar(cfg: dict, apenas: str | None = None) -> list[Coletor]:
    nomes = [apenas] if apenas else list(REGISTRO)
    faltando = [n for n in nomes if n not in REGISTRO]
    if faltando:
        raise SystemExit(f"Fonte desconhecida: {faltando[0]}. "
                         f"Disponiveis: {', '.join(REGISTRO)}")
    return [REGISTRO[n](cfg) for n in nomes]


__all__ = ["Coletor", "coletar_todos", "montar", "REGISTRO"]
