"""Estagio 2 do funil: quanto cada vaga combina com o curriculo.

So roda no que sobreviveu a filtros.py. Dois modos:

LLM (padrao, precisa de ANTHROPIC_API_KEY)
    O curriculo (perfil/curriculo.md) vai no system prompt; cada vaga vai numa
    chamada. A resposta e JSON validado por pydantic (`messages.parse` com
    `output_format`). Se vier fora do schema ou com nota fora de 0-10, tenta de
    novo; se falhar de novo, a vaga cai para o modo sem LLM em vez de sumir.

Sem LLM (fallback gratis)
    Nota por sobreposicao: quantas competencias do curriculo e termos das
    trilhas prioritarias aparecem no texto da vaga. Pior que o modelo, mas
    ordena e corta lixo — antes todo mundo recebia a nota de corte.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from .config import RAIZ
from .filtros import normalizar
from .models import Oportunidade

log = logging.getLogger(__name__)

TENTATIVAS = 2

# US$ por milhao de tokens (entrada, saida). Usado so para logar o custo.
PRECOS = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
}


# --- schema da resposta ---------------------------------------------------

class AvaliacaoVaga(BaseModel):
    nota: int = Field(description="0 a 10: quanto a vaga combina com o curriculo e as restricoes")
    aderente: bool = Field(description="true se vale a pena ele se candidatar")
    justificativa: str = Field(description="uma frase curta em portugues citando o que do curriculo bate ou o que impede")
    efetivacao: Optional[bool] = Field(description="a vaga sinaliza efetivacao/CLT ao final? null se nao da para saber")


class AvaliacaoConcurso(BaseModel):
    nota: int = Field(description="0 a 10")
    aderente: bool = Field(description="true se vale a pena ele se inscrever")
    justificativa: str = Field(description="uma frase curta em portugues")
    nivel_medio: Optional[bool] = Field(description="o cargo de interesse e de nivel medio? null se nao se aplica")


# --- prompts --------------------------------------------------------------

SISTEMA_ESTAGIO = """Voce faz a triagem semanal de vagas para o candidato cujo \
curriculo esta abaixo. Para cada vaga, diga quanto ela combina com ele.

<curriculo>
{curriculo}
</curriculo>

Restricoes dele (eliminatorias):
- Quer vaga de entrada: estagio, trainee ou junior. Pleno/senior nao serve.
- So SOFTWARE e DADOS. Hardware, eletronica, firmware, embarcados, redes \
fisicas, suporte tecnico/help desk, vendas e marketing estao fora.
- Mora em Brasilia e nao se muda. Presencial ou hibrido fora do DF nao serve; \
remoto no Brasil serve. Vaga no exterior so se for remota e contratar quem \
mora no Brasil.
- Estagio precisa ser compativel com quem se forma em {formatura}; vaga que \
exige diploma ja concluido nao serve.

Trilhas, por ordem de interesse: {prioridades}.
Empresas que ele prioriza: {empresas}.

Como dar a nota:
- 9-10: trilha prioritaria, usa o que ele ja sabe (Python, SQL, ML, dados, \
TypeScript/React), local compativel e chance real de efetivacao ou CLT.
- 7-8: software ou dados em geral, local compativel, encaixe razoavel com o \
curriculo.
- 4-6: tecnologia, mas encaixe fraco (stack que ele nao tem, funcao \
generalista, remoto duvidoso).
- 0-3: qualquer restricao eliminatoria violada.
Na justificativa, cite o ponto concreto do curriculo que bate (ex.: "Power \
BI no TJDFT", "competicao de risco de credito") ou a restricao violada."""

SISTEMA_CONCURSO = """Voce faz a triagem de publicacoes de diario oficial para \
o candidato cujo curriculo esta abaixo. Ele cursa Engenharia de Computacao na \
UnB com formatura prevista em {formatura}. Salario inicial de interesse: \
acima de R$ {minimo}.

<curriculo>
{curriculo}
</curriculo>

O que interessa, nesta ordem:
1. NIVEL SUPERIOR em carreira de TI (sistemas, desenvolvimento, dados, \
seguranca) ou do setor financeiro (Banco Central, CVM, BNDES), desde que a \
posse tenda a ocorrer a partir de {formatura} — edital recem-aberto, prazo \
longo ou cadastro de reserva.
2. NIVEL MEDIO apenas em banco publico (Caixa, Banco do Brasil, BRB): tecnico \
bancario, escriturario, agente comercial — pode fazer ja, sem diploma.

Notas: 0-2 se nao e edital de abertura ou nenhum cargo se encaixa; 4-6 se \
encaixa mas salario baixo ou posse claramente antes de {formatura}; 7-10 se \
edital de abertura compativel e salario acima do minimo."""


# --- entrada publica ------------------------------------------------------

def carregar_curriculo(cfg: dict) -> str:
    caminho = RAIZ / cfg.get("perfil", {}).get("curriculo", "perfil/curriculo.md")
    try:
        return Path(caminho).read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("curriculo nao encontrado em %s — ranking sem CV", caminho)
        return ""


def rankear(itens: list[Oportunidade], cfg: dict) -> list[Oportunidade]:
    rk = cfg["ranking"]
    cliente = _cliente() if rk["usar_llm"] else None

    if cliente is None:
        for o in itens:
            _nota_sem_llm(o, cfg)
        return itens

    curriculo = carregar_curriculo(cfg)
    sistemas = {
        "estagio": SISTEMA_ESTAGIO.format(
            curriculo=curriculo,
            formatura=cfg["estagio"]["formatura_prevista"],
            prioridades="; ".join(cfg["estagio"]["prioridades"]),
            empresas=", ".join(cfg["estagio"]["empresas_alvo"])),
        "concurso": SISTEMA_CONCURSO.format(
            curriculo=curriculo,
            formatura=cfg["estagio"]["formatura_prevista"],
            minimo=cfg["concursos"]["salario_minimo"]),
    }
    uso = Uso(rk["modelo"])

    for o in itens:
        schema = AvaliacaoVaga if o.tipo == "estagio" else AvaliacaoConcurso
        av = _avaliar(cliente, rk["modelo"], sistemas[o.tipo], o, schema, uso)
        if av is None:
            # Perder oportunidade e pior do que mostrar ruido: cai para a
            # nota por palavras em vez de sumir do relatorio.
            _nota_sem_llm(o, cfg)
            o.motivo = "[sem LLM] " + o.motivo
            continue
        o.nota = av.nota
        o.motivo = av.justificativa[:200]
        if getattr(av, "efetivacao", None) is True:
            o.alertas.append("efetivacao provavel")

    log.info("ranking LLM: %d chamadas, %d tokens entrada, %d saida, ~US$ %.4f",
             uso.chamadas, uso.entrada, uso.saida, uso.custo)
    return itens


def selecionar(itens: list[Oportunidade], cfg: dict) -> list[Oportunidade]:
    rk = cfg["ranking"]
    aprovados = [o for o in itens if (o.nota or 0) >= rk["nota_minima"]]
    aprovados.sort(key=lambda o: (-(o.nota or 0), o.organizacao))
    return aprovados


# --- LLM ------------------------------------------------------------------

@dataclass
class Uso:
    modelo: str
    chamadas: int = 0
    entrada: int = 0
    saida: int = 0

    def somar(self, resp) -> None:
        self.chamadas += 1
        self.entrada += getattr(resp.usage, "input_tokens", 0) or 0
        self.saida += getattr(resp.usage, "output_tokens", 0) or 0

    @property
    def custo(self) -> float:
        p_in, p_out = PRECOS.get(self.modelo, (0.0, 0.0))
        return (self.entrada * p_in + self.saida * p_out) / 1_000_000


def _cliente():
    try:
        import anthropic
    except ImportError:
        log.warning("pacote anthropic nao instalado — ranking sem LLM")
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY ausente — ranking sem LLM (nota por palavras)")
        return None
    return anthropic.Anthropic()


def _avaliar(cliente, modelo: str, sistema: str, o: Oportunidade,
             schema: type[BaseModel], uso: Uso):
    """Uma vaga -> avaliacao validada, ou None depois de TENTATIVAS falhas."""
    import anthropic

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = cliente.messages.parse(
                model=modelo,
                max_tokens=2000,
                system=sistema,
                output_config={"effort": "low"},  # classificacao: nao precisa pensar muito
                output_format=schema,
                messages=[{"role": "user", "content": o.texto_para_analise()}],
            )
            uso.somar(resp)
            if resp.stop_reason in ("refusal", "max_tokens"):
                raise ValueError(f"stop_reason={resp.stop_reason}")
            av = resp.parsed_output
            if av is None:
                raise ValueError("resposta sem JSON")
            # O schema garante o tipo; o intervalo a gente confere aqui.
            if not 0 <= av.nota <= 10:
                raise ValueError(f"nota fora de 0-10: {av.nota}")
            return av
        except (ValidationError, ValueError) as e:
            log.warning("ranking: resposta invalida para %r (tentativa %d): %s",
                        o.titulo[:60], tentativa, e)
        except anthropic.APIError as e:
            # O SDK ja fez retry de 429/5xx; aqui e erro que nao vai sumir.
            log.warning("ranking: API falhou para %r: %s", o.titulo[:60], e)
            return None
    return None


# --- sem LLM --------------------------------------------------------------

def _nota_sem_llm(o: Oportunidade, cfg: dict) -> None:
    if o.tipo != "estagio":
        # Concurso ja passou por filtro de orgao alvo; sem modelo nao ha
        # como julgar cargo/escolaridade, entao entra com a nota de corte.
        o.nota = cfg["ranking"]["nota_minima"]
        o.motivo = ""
        return

    perfil = cfg.get("perfil", {})
    texto = f" {normalizar(o.texto_para_analise(limite=4000))} "
    comp = [t for t in perfil.get("competencias", []) if _casa(t, texto)]
    trilha = [t for t in perfil.get("termos_trilha", []) if _casa(t, texto)]
    alvo = any(normalizar(e) in normalizar(o.organizacao)
               for e in cfg["estagio"]["empresas_alvo"])

    o.nota = min(10, 2 + min(len(comp), 4) + min(len(trilha), 2) + (2 if alvo else 0))
    achados = comp[:4] + [t for t in trilha if t not in comp][:2]
    o.motivo = ("bate com o CV: " + ", ".join(achados)) if achados else "pouco em comum com o CV"


def _casa(termo: str, texto: str) -> bool:
    # Exige borda de palavra: sem isso "sql" casa em "mysql" e "ml" em "html".
    return re.search(rf"(?<![a-z0-9]){re.escape(normalizar(termo))}(?![a-z0-9])",
                     texto) is not None
