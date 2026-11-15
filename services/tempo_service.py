import time
from config import TEMPO_LIMITE_CHAT, INTERVALO_ENTRE_CHATS

MODO_TREINO = "treino"
MODO_AVALIACAO = "avaliacao"
MODOS = (MODO_TREINO, MODO_AVALIACAO)


def intervalo_entre_chats(modo: str) -> int:
    """No treino todos os atendimentos já começam liberados."""
    return 0 if modo == MODO_TREINO else INTERVALO_ENTRE_CHATS


def calcular_liberado_em(simulacao_iniciada_em: float, id_publico: int, modo: str = MODO_AVALIACAO) -> float:
    return simulacao_iniciada_em + (id_publico * intervalo_entre_chats(modo))


def calcular_inicio_turno(at: dict, simulacao_iniciada_em: float) -> float:
    if at["ultimo_tempo_backend"] is not None:
        return at["ultimo_tempo_backend"]
    return calcular_liberado_em(simulacao_iniciada_em, at["id"], at.get("modo", MODO_AVALIACAO))


def atendimento_liberado(at: dict, simulacao_iniciada_em: float) -> bool:
    liberado_em = calcular_liberado_em(simulacao_iniciada_em, at["id"], at.get("modo", MODO_AVALIACAO))
    return time.time() >= liberado_em


def atendimento_expirado(at: dict, simulacao_iniciada_em: float) -> bool:
    if at.get("modo") == MODO_TREINO:
        return False  # treino não tem limite de tempo
    if at["finalizado"]:
        return False
    if not atendimento_liberado(at, simulacao_iniciada_em):
        return False

    inicio_turno = calcular_inicio_turno(at, simulacao_iniciada_em)
    return (time.time() - inicio_turno) >= TEMPO_LIMITE_CHAT
