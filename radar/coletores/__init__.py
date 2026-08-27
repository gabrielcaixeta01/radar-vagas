from .base import Coletor, coletar_todos
from .dou import DOUColetor
from .gupy import GupyColetor
from .querido_diario import QueridoDiarioColetor

REGISTRO: dict[str, type[Coletor]] = {
    "gupy": GupyColetor,
    "dou": DOUColetor,
    "querido-diario": QueridoDiarioColetor,
}


def montar(cfg: dict, apenas: str | None = None) -> list[Coletor]:
    nomes = [apenas] if apenas else list(REGISTRO)
    faltando = [n for n in nomes if n not in REGISTRO]
    if faltando:
        raise SystemExit(f"Fonte desconhecida: {faltando[0]}. "
                         f"Disponiveis: {', '.join(REGISTRO)}")
    return [REGISTRO[n](cfg) for n in nomes]


__all__ = ["Coletor", "coletar_todos", "montar", "REGISTRO"]
