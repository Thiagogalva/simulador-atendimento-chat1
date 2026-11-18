"""Dicas progressivas do modo treino (sem IA, derivadas da resposta esperada do passo)."""
import re

from services.semantica_service import conceitos, palavras_chave
from services.texto_service import normalizar_texto
from services.tom_service import ACAO, ACOLHIMENTO, CORTESIA, PROXIMO_PASSO, componentes_de_acolhimento

NIVEL_MAXIMO = 2
MAXIMO_PALAVRAS = 4

_DICAS_DE_TOM = {
    "acolhimento": "reconheça a situação ou o sentimento do cliente",
    "acao": "diga o que você vai fazer",
    "cortesia": "seja cortês",
    "proximo_passo": "informe o prazo ou o próximo passo",
}

# Palavras que não ajudam como pista de conteúdo.
_GENERICAS = {normalizar_texto(p) for p in (
    "forma", "clara", "claro", "possível", "momento", "melhor", "disso", "nesse", "neste", "agora",
    "assim", "nosso", "nossa", "dessa", "desse", "outra", "outro", "cada", "sempre", "ainda",
    "estar", "estou", "dentro", "mesmo", "quando", "algumas", "alguns", "existe", "existem",
    "acontecendo", "identifiquei", "peço", "poderá", "porque", "também", "apenas", "somente",
)}
_PADROES_DE_TOM = (ACOLHIMENTO, ACAO, CORTESIA, PROXIMO_PASSO)


def e_de_tom_ou_generica(palavra: str) -> bool:
    normal = normalizar_texto(palavra)
    return normal in _GENERICAS or any(p.search(normal) for p in _PADROES_DE_TOM)


def _pistas_de_conteudo(resposta_esperada: str, palavras_criticas) -> list:
    """Palavras críticas do cenário presentes na resposta esperada vêm primeiro; depois as mais raras."""
    escolhidas = []

    criticas = set()
    for palavra in palavras_criticas or []:
        criticas |= conceitos(palavra)

    palavras_da_resposta = re.findall(r"[^\W\d_]+", resposta_esperada, re.UNICODE)
    for palavra in palavras_da_resposta:
        if criticas & conceitos(palavra) and palavra.lower() not in escolhidas:
            escolhidas.append(palavra.lower())

    for palavra in palavras_chave(resposta_esperada, limite=8):
        if len(escolhidas) >= MAXIMO_PALAVRAS:
            break
        if palavra not in escolhidas and len(palavra) >= 5 and not e_de_tom_ou_generica(palavra):
            escolhidas.append(palavra)

    ordem = {p.lower(): i for i, p in enumerate(palavras_da_resposta)}
    return sorted(escolhidas[:MAXIMO_PALAVRAS], key=lambda p: ordem.get(p, 0))


def gerar_dica(resposta_esperada: str, nivel: int, palavras_criticas=None) -> str:
    """
    Nível 1: pontos que a resposta deve cobrir (palavras-chave e tom).
    Nível 2: a resposta sugerida completa.
    """
    if nivel >= NIVEL_MAXIMO:
        return "Resposta sugerida: " + resposta_esperada

    partes = []
    pistas = _pistas_de_conteudo(resposta_esperada, palavras_criticas)
    if pistas:
        partes.append("Fale sobre: " + ", ".join(pistas) + ".")

    tom = [_DICAS_DE_TOM[c] for c in componentes_de_acolhimento(resposta_esperada)]
    if tom:
        partes.append("No tom: " + "; ".join(tom) + ".")

    return " ".join(partes) or "Responda diretamente ao que o cliente perguntou."
