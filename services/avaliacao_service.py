from services.texto_service import (
    FRASES_CHAVE,
    PALAVRAS_CRITICAS,
    normalizar_texto
)
from services.semantica_service import conceitos, similaridade
from services.tom_service import avaliar_tom

def fracao_frases_chave(resposta_normalizada: str, esperada_normalizada: str):
    """
    Entre os grupos de frases-chave presentes na resposta esperada deste passo,
    retorna a fração que também aparece na resposta do operador.
    Retorna None quando o passo não exige nenhuma frase-chave.
    """
    exigidos = 0
    atendidos = 0

    for grupo in FRASES_CHAVE:
        grupo_normalizado = [normalizar_texto(frase) for frase in grupo]
        if any(frase in esperada_normalizada for frase in grupo_normalizado):
            exigidos += 1
            if any(frase in resposta_normalizada for frase in grupo_normalizado):
                atendidos += 1

    if exigidos == 0:
        return None
    return atendidos / exigidos

def fracao_palavras_criticas(conceitos_resposta: set, conceitos_esperados: set, titulo_atendimento: str):
    """
    Entre as palavras críticas do atendimento que aparecem na resposta esperada deste passo,
    retorna a fração presente na resposta do operador.
    Retorna None quando o passo não exige nenhuma palavra crítica.
    """
    criticas = set()
    for palavra in PALAVRAS_CRITICAS.get(titulo_atendimento.lower(), []):
        criticas |= conceitos(palavra)
    exigidas = criticas & conceitos_esperados

    if not exigidas:
        return None
    return sum(1 for c in exigidas if c in conceitos_resposta) / len(exigidas)

def calcular_coerencia(resposta: str, atendimento: dict) -> int:
    resposta_normalizada = normalizar_texto(resposta)
    esperada_normalizada = normalizar_texto(atendimento["resposta_esperada"])

    if not esperada_normalizada.split():
        return 0

    # Componentes (peso, fração 0-1). Frases-chave e palavras críticas só entram
    # quando o passo atual realmente as exige; assim a resposta sugerida vale 100.
    componentes = [(60, similaridade(resposta, atendimento["resposta_esperada"]))]

    frases = fracao_frases_chave(resposta_normalizada, esperada_normalizada)
    if frases is not None:
        componentes.append((20, frases))

    criticas = fracao_palavras_criticas(
        conceitos(resposta),
        conceitos(atendimento["resposta_esperada"]),
        atendimento.get("titulo", "")
    )
    if criticas is not None:
        componentes.append((20, criticas))

    peso_total = sum(peso for peso, _ in componentes)
    nota = sum(peso * fracao for peso, fracao in componentes) / peso_total * 100

    quantidade_palavras = len(resposta_normalizada.split())
    if quantidade_palavras < 4:
        nota -= 20
    elif quantidade_palavras < 7:
        nota -= 8

    return max(0, min(100, int(round(nota))))

def avaliar_empatia(resposta: str, respostas_anteriores=None):
    """Retorna (nota de empatia 0-20, avisos de tom)."""
    return avaliar_tom(resposta, respostas_anteriores)

def avaliar_tempo(segundos: float) -> int:
    if segundos <= 10:
        return 20
    if segundos <= 25:
        return 10
    return 0

def classificar_nivel(nota: float) -> str:
    if nota >= 90:
        return "Especialista"
    if nota >= 75:
        return "Bom"
    if nota >= 60:
        return "Intermediário"
    return "Iniciante"

def calcular_nota(at: dict) -> int:
    if at["total_respostas"] == 0:
        return 0

    base = at["media_coerencia"]
    bonus_empatia = at["media_empatia"]
    bonus_tempo = at["media_tempo"]
    penalidade_erros = at["total_erros"] * 5
    penalidade_cliente = 20 if at.get("encerrado_por_cliente") else 0

    nota = base + bonus_empatia + bonus_tempo - penalidade_erros - penalidade_cliente
    return max(0, min(100, round(nota)))