import time
from config import TEMPO_LIMITE_CHAT, INTERVALO_ENTRE_CHATS

def calcular_liberado_em(simulacao_iniciada_em: float, id_publico: int) -> float:
    return simulacao_iniciada_em + (id_publico * INTERVALO_ENTRE_CHATS)

def calcular_inicio_turno(at: dict, simulacao_iniciada_em: float) -> float:
    if at["ultimo_tempo_backend"] is not None:
        return at["ultimo_tempo_backend"]
    return calcular_liberado_em(simulacao_iniciada_em, at["id"])

def atendimento_liberado(at: dict, simulacao_iniciada_em: float) -> bool:
    return time.time() >= calcular_liberado_em(simulacao_iniciada_em, at["id"])

def atendimento_expirado(at: dict, simulacao_iniciada_em: float) -> bool:
    if at["finalizado"]:
        return False
    if not atendimento_liberado(at, simulacao_iniciada_em):
        return False

    inicio_turno = calcular_inicio_turno(at, simulacao_iniciada_em)
    return (time.time() - inicio_turno) >= TEMPO_LIMITE_CHAT