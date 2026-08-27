"""Modelo normalizado. Todo coletor devolve Oportunidade, nada mais."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

Tipo = Literal["estagio", "concurso"]


@dataclass
class Oportunidade:
    tipo: Tipo
    titulo: str
    organizacao: str          # empresa ou orgao
    url: str
    fonte: str                # "gupy", "dou", ...
    local: str = ""
    remoto: bool = False
    descricao: str = ""
    publicado_em: Optional[date] = None
    prazo: Optional[date] = None          # fim das inscricoes
    salario: Optional[float] = None

    # preenchidos depois, pelo pipeline
    nota: Optional[int] = None
    motivo: str = ""
    alertas: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Chave de deduplicacao.

        Usa URL quando ela e estavel; senao cai para titulo+organizacao.
        Alguns portais mudam querystring a cada request, entao a URL crua
        nao serve — normalize antes no coletor se for o caso.
        """
        base = self.url or f"{self.titulo}|{self.organizacao}"
        return hashlib.sha256(f"{self.fonte}|{base}".encode()).hexdigest()[:16]

    @property
    def dias_ate_prazo(self) -> Optional[int]:
        if not self.prazo:
            return None
        return (self.prazo - date.today()).days

    def texto_para_analise(self, limite: int = 2500) -> str:
        partes = [self.titulo, self.organizacao, self.local, self.descricao]
        return "\n".join(p for p in partes if p)[:limite]
