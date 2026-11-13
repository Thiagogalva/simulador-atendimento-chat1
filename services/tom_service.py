"""
Análise de tom da resposta do operador (regras locais, sem API).

Avalia o acolhimento de forma contextual em vez de apenas contar palavras:
  + acolhimento (reconhece o problema/sentimento do cliente)      até  8 pontos
  + ação        (diz o que vai fazer ou fez pelo cliente)         até  6 pontos
  + cortesia    (agradece, "por gentileza", disposição)           até  3 pontos
  + próximo passo (prazo, retorno, o que acontece agora)          até  3 pontos
  - tom inadequado (hostil, culpa o cliente, descaso, gritaria, gíria, resposta repetida)

Devolve a nota de empatia (0 a 20, mesma escala usada antes) e avisos para o operador.
"""
import re

from services.texto_service import normalizar_texto

ACOLHIMENTO = re.compile(
    r"\b(entend\w*|compreend\w*|lament\w*|sinto muito|imagino|desculp\w*|ciente|"
    r"compreensivel|preocupa\w*)\b"
)
# Ação do operador: "vou/irei/posso + verbo" ou verbo na 1ª pessoa (não conta o substantivo "análise").
_VERBOS = (r"verific|analis|consult|conferi|providenci|encaminh|direcion|orient|explic|ajud|auxili|"
           r"registr|resolv|solucion|transferi|esclarec|inform|acompanh")
ACAO = re.compile(
    r"\b(vou|irei|posso|vamos|estou|estarei|farei|ja)\s+(?:\w+\s+){0,2}?(?:" + _VERBOS + r")\w*"
    r"|\b(verifico|analiso|consulto|confiro|providencio|encaminho|direciono|oriento|explico|ajudo|"
    r"auxilio|registro|resolvo|informo|acompanho|registrei|encaminhei|providenciei|verifiquei)\b"
)
CORTESIA = re.compile(
    r"\b(por gentileza|por favor|obrigad\w*|agradec\w*|agradeco|de nada|"
    r"a disposicao|fico a disposicao|com prazer)\b"
)
PROXIMO_PASSO = re.compile(
    r"\b(prazo\w*|retorno|aguard\w*|proximos? passos?|em breve|assim que|acompanh\w*|"
    r"dias? uteis|\d+ (horas?|dias?)|ate \d+)\b"
)

# (padrão, penalidade, aviso)
TOM_INADEQUADO = [
    (re.compile(r"\b(nao e comigo|nao e problema meu|problema e seu|problema seu|se vira|"
                r"resolve ai|nao me interessa|nao ligo|sua culpa|voce errou|voce que errou)\b"),
     10, "Evite frases que passam descaso ou culpam o cliente. Reconheça a situação e ofereça um caminho."),
    (re.compile(r"\b(ja falei|ja disse|ja expliquei|como eu disse)\b"),
     6, "Evite cobrar o cliente por não ter entendido. Explique de novo com paciência."),
    (re.compile(r"\bcalma\b"),
     5, 'Evite pedir "calma" ao cliente; demonstre que entende a urgência.'),
    (re.compile(r"\b(nao sei|nao posso fazer nada|nao tem como|nao tem o que fazer|nao tenho como)\b"),
     5, 'Evite "não sei"/"não tem como" sem alternativa. Explique o motivo e o próximo passo.'),
    (re.compile(r"\b(kk+|rs+|mano|vlw|tmj|opa|eae|valeu)\b"),
     4, "Use linguagem profissional; evite gírias e risadas no atendimento."),
]


def _proporcao_maiusculas(texto: str) -> float:
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 8:
        return 0.0
    return sum(1 for c in letras if c.isupper()) / len(letras)


def avaliar_tom(resposta: str, respostas_anteriores=None):
    """
    Retorna (empatia, avisos). `respostas_anteriores` são as respostas já enviadas pelo operador
    neste atendimento (usadas para detectar repetição).
    """
    respostas_anteriores = respostas_anteriores or []
    normalizada = normalizar_texto(resposta)
    avisos = []

    pontos = 0
    if ACOLHIMENTO.search(normalizada):
        pontos += 8
    if ACAO.search(normalizada):
        pontos += 6
    if CORTESIA.search(normalizada):
        pontos += 3
    if PROXIMO_PASSO.search(normalizada):
        pontos += 3

    penalidade = 0
    for padrao, valor, aviso in TOM_INADEQUADO:
        if padrao.search(normalizada):
            penalidade += valor
            avisos.append(aviso)

    if _proporcao_maiusculas(resposta) >= 0.6:
        penalidade += 8
        avisos.append("Evite escrever em letras maiúsculas; pode soar como grito.")

    if resposta.count("!") >= 3:
        penalidade += 3
        avisos.append("Evite excesso de exclamações; mantenha um tom calmo e profissional.")

    if normalizada and normalizada in {normalizar_texto(r) for r in respostas_anteriores}:
        penalidade += 6
        avisos.append("Resposta repetida. Adapte o texto ao que o cliente acabou de dizer.")

    empatia = max(0, min(20, pontos - penalidade))
    return empatia, avisos
