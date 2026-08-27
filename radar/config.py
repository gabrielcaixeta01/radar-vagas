from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_CONFIG = RAIZ / "config.yaml"
CAMINHO_ESTADO = RAIZ / "state" / "seen.json"


def carregar(caminho: Path = CAMINHO_CONFIG) -> dict[str, Any]:
    with open(caminho, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg.setdefault("escolaridade", ["medio"])
    cfg.setdefault("ranking", {})
    cfg["ranking"].setdefault("usar_llm", True)
    cfg["ranking"].setdefault("modelo", "claude-haiku-4-5")
    cfg["ranking"].setdefault("nota_minima", 6)
    cfg["ranking"].setdefault("max_itens_por_secao", 10)
    return cfg


def env(nome: str, obrigatorio: bool = False) -> str | None:
    valor = os.environ.get(nome)
    if obrigatorio and not valor:
        raise RuntimeError(f"Variavel de ambiente {nome} nao definida")
    return valor
