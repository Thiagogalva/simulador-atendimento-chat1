from services.texto_service import (
    FRASES_CHAVE,
    PALAVRAS_CRITICAS,
    PALAVRAS_EMPATICAS,
    normalizar_texto,
    expandir_com_sinonimos
)

def pontuar_frases_chave(resposta_normalizada: str) -> int:
    pontos = 0

    for grupo in FRASES_CHAVE:
        grupo_normalizado = [normalizar_texto(frase) for frase in grupo]
        if any(frase in resposta_normalizada for frase in grupo_normalizado):
            pontos += 8

    return min(pontos, 24)

def pontuar_palavras_criticas(resposta_palavras: set, titulo_atendimento: str) -> int:
    criticas = PALAVRAS_CRITICAS.get(titulo_atendimento.lower(), [])
    if not criticas:
        return 0

    criticas_normalizadas = {normalizar_texto(p) for p in criticas}
    presentes = sum(1 for palavra in criticas_normalizadas if palavra in resposta_palavras)

    if len(criticas_normalizadas) == 0:
        return 0

    proporcao = presentes / len(criticas_normalizadas)
    return int(proporcao * 20)

def calcular_coerencia(resposta: str, atendimento: dict) -> int:
    resposta_normalizada = normalizar_texto(resposta)
    esperada_normalizada = normalizar_texto(atendimento["resposta_esperada"])

    palavras_resposta = set(resposta_normalizada.split())
    palavras_esperadas = set(esperada_normalizada.split())

    if len(palavras_esperadas) == 0:
        return 0

    palavras_resposta_expandidas = expandir_com_sinonimos(palavras_resposta)
    palavras_esperadas_expandidas = expandir_com_sinonimos(palavras_esperadas)

    intersecao = palavras_resposta_expandidas.intersection(palavras_esperadas_expandidas)

    similaridade = len(intersecao) / len(palavras_esperadas_expandidas)
    nota_base = similaridade * 60

    bonus_frases = pontuar_frases_chave(resposta_normalizada)
    bonus_criticas = pontuar_palavras_criticas(
        palavras_resposta_expandidas,
        atendimento.get("titulo", "").lower()
    )

    penalidade_curta = 0
    if len(resposta_normalizada.split()) < 4:
        penalidade_curta = 20
    elif len(resposta_normalizada.split()) < 7:
        penalidade_curta = 8

    nota = nota_base + bonus_frases + bonus_criticas - penalidade_curta

    return max(0, min(100, int(nota)))

def avaliar_empatia(resposta: str) -> int:
    resposta_lower = resposta.lower()
    pontos = sum(1 for p in PALAVRAS_EMPATICAS if p in resposta_lower)
    return min(20, pontos * 5)

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

    nota = base + bonus_empatia + bonus_tempo - penalidade_erros
    return max(0, min(100, round(nota)))