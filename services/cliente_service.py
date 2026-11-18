"""
Cliente simulado reativo (regras locais, sem API, determinístico).

Cada atendimento tem um nível de irritação (0-100) que sobe ou desce conforme a qualidade das respostas:

  * resposta fora de contexto, seca, hostil ou gritando  -> o cliente reage e REPETE a pergunta;
  * resposta incompleta, com descaso, gíria etc.          -> o cliente segue, mas comenta o problema;
  * resposta boa                                          -> o cliente se acalma;
  * irritação >= LIMITE_ENCERRAMENTO, ou falhas repetidas no mesmo passo -> o cliente desiste e
    pede um supervisor (atendimento encerrado).

As frases são escolhidas por um índice determinístico (sem aleatoriedade), o que torna o
comportamento reproduzível e fácil de testar.
"""

LIMITE_ENCERRAMENTO = 85
AUMENTO_MAXIMO_POR_RESPOSTA = 40  # a primeira ofensa irrita muito, mas só a reincidência faz desistir
TENTATIVAS_MAXIMAS_POR_ETAPA = 2  # repetições permitidas antes de o cliente desistir

COERENCIA_FORA_DE_CONTEXTO = 30
COERENCIA_INCOMPLETA = 55
COERENCIA_BOA = 75

IMPACTO_SINAL = {
    "hostil": 30,
    "gritando": 20,
    "cobranca": 15,
    "descaso": 15,
    "repetida": 10,
    "calma": 10,
    "giria": 8,
    "exclamacoes": 0,
}

REACOES_REPETIR = {
    "fora": {
        "leve": [
            "Desculpe, acho que não era isso que eu queria saber. Repito: {msg}",
            "Não entendi como isso responde a minha dúvida. Eu perguntei: {msg}",
        ],
        "medio": [
            "Isso não tem nada a ver com o que eu perguntei. Vou repetir: {msg}",
            "Parece que você não leu o que eu escrevi. {msg}",
        ],
        "alto": [
            "Você não está me ouvindo! Já perguntei e ninguém responde: {msg}",
            "Eu estou perdendo tempo aqui. Responda o que eu perguntei: {msg}",
        ],
    },
    "seca": {
        "leve": ["Só isso? Pode explicar melhor, por favor? {msg}"],
        "medio": ["Essa resposta não me ajuda em nada. Preciso de mais detalhes. {msg}"],
        "alto": ["Uma resposta dessas não resolve nada! Eu preciso de uma explicação de verdade. {msg}"],
    },
    "hostil": {
        "leve": ["Não precisa falar assim comigo. Eu só quero resolver. {msg}"],
        "medio": ["Que falta de respeito! Quero ser atendido com educação. {msg}"],
        "alto": ["Isso é um absurdo! Não é assim que se trata um cliente! {msg}"],
    },
    "gritando": {
        "leve": ["Não precisa gritar comigo, por favor. {msg}"],
        "medio": ["Por que está gritando? Eu só preciso de ajuda. {msg}"],
        "alto": ["Não admito que gritem comigo! Eu exijo respeito! {msg}"],
    },
}

PREFIXOS_AVANCAR = {
    "incompleta": [
        "Hum, não ficou muito claro, mas vamos em frente.",
        "Acho que entendi só em parte...",
    ],
    "descaso": [
        "Então não tem nada que possam fazer? Isso parece descaso.",
        "Não gostei dessa resposta, parece que ninguém se importa.",
    ],
    "cobranca": [
        "Não precisa me cobrar assim, eu só estou tentando entender.",
    ],
    "calma": [
        "Não me peça calma, a situação é séria para mim.",
    ],
    "giria": [
        "Poderia falar de forma mais séria? Esse assunto é importante para mim.",
    ],
    "repetida": [
        "Você já me disse isso. Poderia explicar de outro jeito?",
    ],
    "irritado": [
        "Já estou ficando sem paciência com este atendimento.",
        "Estou há muito tempo nisso e nada se resolve.",
    ],
    "recuperacao": [
        "Ok, agora ficou mais claro.",
        "Certo, agora sim entendi.",
    ],
}

ENCERRAMENTOS = [
    "Já perdi tempo demais. Quero falar com um supervisor agora.",
    "Chega, isso não está me ajudando. Vou procurar outro canal e registrar uma reclamação.",
]


def humor_da_irritacao(irritacao: float) -> str:
    if irritacao >= 60:
        return "atritado"
    if irritacao >= 30:
        return "impaciente"
    return "calmo"


def _limitar(valor: float) -> int:
    return int(max(0, min(100, round(valor))))


def _impacto(coerencia: int, sinais: set, qtd_erros: int, tempo_nota: int) -> int:
    if coerencia < COERENCIA_FORA_DE_CONTEXTO:
        delta = 25
    elif coerencia < COERENCIA_INCOMPLETA:
        delta = 10
    elif coerencia < COERENCIA_BOA:
        delta = 0
    else:
        delta = -12

    delta += sum(IMPACTO_SINAL.get(s, 0) for s in sinais)

    if qtd_erros >= 3:
        delta += 5
    if tempo_nota == 0:
        delta += 5  # demorou para responder
    return min(delta, AUMENTO_MAXIMO_POR_RESPOSTA)


def _escolher(opcoes: list, semente: int) -> str:
    return opcoes[semente % len(opcoes)]


def _nivel(irritacao: int) -> str:
    if irritacao >= 60:
        return "alto"
    if irritacao >= 30:
        return "medio"
    return "leve"


def decidir_reacao(*, coerencia: int, sinais: set, qtd_erros: int, tempo_nota: int,
                   palavras: int, irritacao: int, tentativas_etapa: int,
                   ultima_etapa: bool = False) -> dict:
    """
    Decide como o cliente reage à resposta do operador.
    Retorna {"acao": "avancar"|"repetir"|"encerrar", "categoria", "irritacao", "humor", "delta"}.
    """
    delta = _impacto(coerencia, sinais, qtd_erros, tempo_nota)
    nova = _limitar(irritacao + delta)

    # Categoria principal (a mais grave primeiro).
    if "hostil" in sinais:
        categoria = "hostil"
    elif "gritando" in sinais:
        categoria = "gritando"
    elif coerencia < COERENCIA_FORA_DE_CONTEXTO and palavras < 4:
        categoria = "seca"
    elif coerencia < COERENCIA_FORA_DE_CONTEXTO:
        categoria = "fora"
    elif "descaso" in sinais:
        categoria = "descaso"
    elif "cobranca" in sinais:
        categoria = "cobranca"
    elif "calma" in sinais:
        categoria = "calma"
    elif "repetida" in sinais:
        categoria = "repetida"
    elif "giria" in sinais:
        categoria = "giria"
    elif coerencia < COERENCIA_INCOMPLETA:
        categoria = "incompleta"
    elif irritacao >= 30 and coerencia >= COERENCIA_BOA and delta < 0:
        categoria = "recuperacao"
    elif nova >= 60:
        categoria = "irritado"
    else:
        categoria = "ok"

    acao = "repetir" if categoria in REACOES_REPETIR else "avancar"

    if nova >= LIMITE_ENCERRAMENTO or (acao == "repetir" and tentativas_etapa >= TENTATIVAS_MAXIMAS_POR_ETAPA):
        acao = "encerrar"
    elif acao == "repetir" and ultima_etapa:
        # Na despedida não faz sentido repetir a pergunta: o cliente apenas vai embora.
        acao = "avancar"
        categoria = "incompleta"

    return {
        "acao": acao,
        "categoria": categoria,
        "irritacao": nova,
        "humor": "encerrado" if acao == "encerrar" else humor_da_irritacao(nova),
        "delta": delta,
    }


def mensagem_encerramento(semente: int) -> str:
    return _escolher(ENCERRAMENTOS, semente)


def mensagem_repeticao(decisao: dict, mensagem_cliente: str, semente: int) -> str:
    modelo = _escolher(REACOES_REPETIR[decisao["categoria"]][_nivel(decisao["irritacao"])], semente)
    return modelo.format(msg=mensagem_cliente)


def mensagem_proxima(decisao: dict, proxima_mensagem: str, semente: int) -> str:
    """Próxima fala do roteiro, com um comentário do cliente quando há motivo."""
    categoria = decisao["categoria"]
    if categoria in PREFIXOS_AVANCAR:
        return f"{_escolher(PREFIXOS_AVANCAR[categoria], semente)} {proxima_mensagem}"
    return proxima_mensagem


# ---------------------------------------------------------------- pedidos de espera

ESPERA_ACEITA = [
    "Tudo bem, aguardo.",
    "Ok, pode verificar. Estou aguardando.",
    "Certo, fico no aguardo.",
    "Sem problemas, aguardo o seu retorno.",
]
ESPERA_EXCEDIDA = [
    "Já é a {n}ª vez que você me pede um momento. Consegue me dar uma posição?",
    "Estou esperando há muito tempo e ainda não tenho uma resposta. Preciso de uma posição agora.",
]
AUMENTO_POR_EXCESSO = {1: 20, 2: 25}
EXCESSO_PARA_DESISTIR = 3  # 3 pedidos além do limite e o cliente vai embora


def decidir_espera(pedidos: int, limite: int, irritacao: int) -> dict:
    """
    Reação do cliente ao `pedidos`-ésimo pedido de espera (contando este), sendo `limite` quantos ele tolera.
    Retorna {"acao": "aguardar"|"reclamar"|"encerrar", "irritacao", "humor", "mensagem"}.
    """
    excesso = pedidos - limite
    semente = pedidos

    if excesso <= 0:
        return {"acao": "aguardar", "irritacao": irritacao, "humor": humor_da_irritacao(irritacao),
                "mensagem": _escolher(ESPERA_ACEITA, semente)}

    nova = _limitar(irritacao + AUMENTO_POR_EXCESSO.get(excesso, 30))
    if excesso >= EXCESSO_PARA_DESISTIR or nova >= LIMITE_ENCERRAMENTO:
        return {"acao": "encerrar", "irritacao": max(nova, LIMITE_ENCERRAMENTO), "humor": "encerrado",
                "mensagem": mensagem_encerramento(semente)}

    modelo = _escolher(ESPERA_EXCEDIDA, excesso - 1)
    return {"acao": "reclamar", "irritacao": nova, "humor": humor_da_irritacao(nova),
            "mensagem": modelo.format(n=pedidos)}
