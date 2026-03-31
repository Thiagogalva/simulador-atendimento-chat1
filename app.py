from flask import Flask, render_template, request, jsonify
from spellchecker import SpellChecker
import re
import unicodedata
import time

app = Flask(__name__)

spell = SpellChecker(language="pt")

PALAVRAS_PERMITIDAS = {
    "pix", "bradesco", "app", "ddd", "email", "e-mail",
    "estorno", "extrato", "agência", "agencia", "conta",
    "cesta", "serviços", "servicos", "bloqueio", "cliente",
    "atendimento", "saldo", "transferência", "transferencia",
    "banco", "análise", "analise", "prazo", "contato",
    "setor", "responsável", "responsavel", "horário", "horario", "extorno", "ok",
}

ABREVIACOES_PROIBIDAS = {
    "vc": "você",
    "vcs": "vocês",
    "tb": "também",
    "pq": "porque",
    "blz": "beleza",
    "mha": "minha",
    "fasso": "faço",
    "nao": "não",
    "to": "estou",
    "vo": "vou"
}

SINONIMOS = {
    "verificar": ["analisar", "checar", "consultar", "conferir"],
    "analisar": ["verificar", "checar", "consultar", "conferir"],
    "orientar": ["explicar", "informar", "esclarecer"],
    "explicar": ["orientar", "informar", "esclarecer"],
    "ajudar": ["auxiliar", "apoiar"],
    "resolver": ["solucionar", "regularizar"],
    "problema": ["erro", "falha", "ocorrência", "ocorrencia"],
    "bloqueio": ["restrição", "restricao", "impedimento"],
    "prazo": ["tempo", "período", "periodo"],
    "contato": ["retorno", "atendimento"],
    "solicitação": ["pedido", "demanda", "solicitacao"],
    "cancelamento": ["cancelar"],
    "estorno": ["devolução", "devolucao", "reembolso"],
    "urgência": ["urgencia", "prioridade"],
    "informações": ["informacoes", "dados", "detalhes"]
}

FRASES_CHAVE = [
    ["entendo sua situação", "compreendo sua situação", "entendo a sua situação"],
    ["vou verificar", "vou analisar", "vou consultar", "vou checar"],
    ["posso te ajudar", "posso ajudar", "vou te ajudar"],
    ["prazo previsto", "prazo para retorno", "prazo informado"],
    ["setor responsável", "time especializado", "área responsável", "area responsavel"],
    ["peço um momento", "peço só um momento", "aguarde um momento", "por gentileza aguarde"],
    ["está dentro do prazo", "esta dentro do prazo"],
    ["vou te orientar", "vou explicar", "vou informar"]
]

PALAVRAS_CRITICAS = {
    "tarifa / estorno": ["análise", "prazo", "estorno", "contestação"],
    "pix com bloqueio cautelar": ["bloqueio", "análise", "segurança", "prazo"],
    "conta bloqueada / pix indisponível": ["bloqueio", "setor", "solicitação", "contato"]
}

PALAVRAS_EMPATICAS = [
    "entendo", "compreendo", "lamento", "sinto muito",
    "posso te ajudar", "vou verificar", "por gentileza",
    "agradeço", "obrigada", "obrigado"
]

spell.word_frequency.load_words(PALAVRAS_PERMITIDAS)

atendimentos = [
    {
        "id": 0,
        "titulo": "Tarifa / estorno",
        "mensagens": [
            {"tipo": "cliente", "texto": "Abri uma contestação sobre um valor cobrado na minha conta e ainda não tive retorno."}
        ],
        "fluxo": [
            {
                "cliente": "Abri uma contestação sobre um valor cobrado na minha conta e ainda não tive retorno.",
                "resposta_esperada": "Entendo a sua situação. Vou te explicar como está o andamento da análise e o prazo previsto para retorno."
            },
            {
                "cliente": "No extrato ainda não aparece nada.",
                "resposta_esperada": "Nesse caso, a análise ainda pode estar dentro do prazo. Como a solicitação foi registrada recentemente, o retorno pode levar até cinco dias úteis."
            },
            {
                "cliente": "Foi cobrada uma tarifa de cesta de serviços e eu não fui informada sobre isso.",
                "resposta_esperada": "Entendo o seu questionamento. Essa cobrança pode estar vinculada a um pacote de serviços contratado na abertura da conta ou em momento anterior."
            },
            {
                "cliente": "Mas eu deveria saber disso, correto?",
                "resposta_esperada": "Sim, é importante que você tenha clareza sobre qualquer serviço vinculado à sua conta. Posso te orientar também sobre como verificar ou alterar essa configuração."
            },
            {
                "cliente": "Eu só quero o valor de volta.",
                "resposta_esperada": "Entendo. Como já existe uma solicitação de estorno aberta, o ideal agora é aguardar a conclusão da análise dentro do prazo informado."
            },
            {
                "cliente": "Obrigada.",
                "resposta_esperada": "De nada. Agradeço o seu contato. Se precisar de mais alguma informação, estou à disposição."
            }
        ],
        "etapa_atual": 0,
        "avaliacoes": [],
        "total_erros": 0,
        "total_respostas": 0,
        "media_coerencia": 0,
        "media_empatia": 0,
        "media_tempo": 0,
        "resposta_esperada": "Entendo a sua situação. Vou te explicar como está o andamento da análise e o prazo previsto para retorno.",
        "finalizado": False,
        "ultimo_tempo_backend": None
    },
    {
        "id": 1,
        "titulo": "Pix com bloqueio cautelar",
        "mensagens": [
            {"tipo": "cliente", "texto": "Preciso que esse bloqueio seja liberado. Estou no banco para sacar meu dinheiro e a transferência foi feita de uma conta minha."}
        ],
        "fluxo": [
            {
                "cliente": "Preciso que esse bloqueio seja liberado. Estou no banco para sacar meu dinheiro e a transferência foi feita de uma conta minha.",
                "resposta_esperada": "Entendo a urgência da sua situação. Vou verificar as informações no sistema para te orientar da forma mais clara possível."
            },
            {
                "cliente": "A transferência veio da minha própria conta e o valor é meu.",
                "resposta_esperada": "Obrigada por explicar. Mesmo quando a transferência é de conta da mesma titularidade, o sistema pode aplicar bloqueio cautelar por segurança."
            },
            {
                "cliente": "Minha mãe tem cirurgia amanhã e eu preciso desse valor agora.",
                "resposta_esperada": "Lamento muito pelo transtorno e entendo a gravidade da situação. No momento, esse tipo de bloqueio depende da análise de segurança e pode levar até 72 horas."
            },
            {
                "cliente": "Então devolve o dinheiro para a conta de origem agora.",
                "resposta_esperada": "No momento, a liberação ou devolução do valor só ocorre após a conclusão da análise. Eu não consigo fazer essa liberação manualmente por aqui."
            },
            {
                "cliente": "Vocês estão me causando transtorno e eu preciso de uma solução.",
                "resposta_esperada": "Compreendo a sua insatisfação. Para verificar a possibilidade de continuidade e orientação mais detalhada, vou direcionar o seu caso para o time especializado."
            },
            {
                "cliente": "Obrigada.",
                "resposta_esperada": "Eu que agradeço. O especialista dará continuidade ao atendimento e seguirá com as orientações do seu caso."
            }
        ],
        "etapa_atual": 0,
        "avaliacoes": [],
        "total_erros": 0,
        "total_respostas": 0,
        "media_coerencia": 0,
        "media_empatia": 0,
        "media_tempo": 0,
        "resposta_esperada": "Entendo a urgência da sua situação. Vou verificar as informações no sistema para te orientar da forma mais clara possível.",
        "finalizado": False,
        "ultimo_tempo_backend": None
    },
    {
        "id": 2,
        "titulo": "Conta bloqueada / Pix indisponível",
        "mensagens": [
            {"tipo": "cliente", "texto": "Não consigo fazer Pix. Está dando erro."}
        ],
        "fluxo": [
            {
                "cliente": "Não consigo fazer Pix. Está dando erro.",
                "resposta_esperada": "Entendi. Vou verificar o que está acontecendo na sua conta. Peço só um momento, por gentileza."
            },
            {
                "cliente": "Qual é o problema?",
                "resposta_esperada": "Identifiquei que existe um bloqueio na sua conta neste momento, e por isso algumas movimentações podem ficar indisponíveis."
            },
            {
                "cliente": "Qual o motivo desse bloqueio? Preciso ir até a agência?",
                "resposta_esperada": "No momento, o motivo detalhado não aparece para mim aqui no atendimento. Esse caso precisa ser encaminhado ao setor responsável para análise."
            },
            {
                "cliente": "Posso resolver isso em uma agência?",
                "resposta_esperada": "Nesse caso, a orientação é seguir com a solicitação pelo canal responsável, porque a agência pode não conseguir concluir esse tipo de tratativa diretamente."
            },
            {
                "cliente": "O que vocês precisam para abrir essa solicitação?",
                "resposta_esperada": "Para abrir a solicitação, preciso do seu telefone com DDD, e-mail e do melhor horário para contato."
            },
            {
                "cliente": "Tenho salário para receber nessa conta. Como faço agora?",
                "resposta_esperada": "Entendo sua preocupação. Como existe um bloqueio ativo, o ideal é aguardar o retorno do setor responsável, que poderá orientar os próximos passos com segurança."
            },
            {
                "cliente": "Ok, só isso.",
                "resposta_esperada": "Perfeito. A solicitação já foi registrada. Agradeço o seu contato e, se precisar, estamos à disposição."
            }
        ],
        "etapa_atual": 0,
        "avaliacoes": [],
        "total_erros": 0,
        "total_respostas": 0,
        "media_coerencia": 0,
        "media_empatia": 0,
        "media_tempo": 0,
        "resposta_esperada": "Entendi. Vou verificar o que está acontecendo na sua conta. Peço só um momento, por gentileza.",
        "finalizado": False,
        "ultimo_tempo_backend": None
    }
]


def remover_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def tokenizar_palavras(texto: str):
    return list(re.finditer(r"\b[^\W\d_]+\b", texto, re.UNICODE))

def normalizar_texto(texto: str) -> str:
    texto = texto.lower().strip()
    texto = remover_acentos(texto)
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def expandir_com_sinonimos(palavras: set) -> set:
    expandidas = set(palavras)

    for palavra in list(palavras):
        if palavra in SINONIMOS:
            for sinonimo in SINONIMOS[palavra]:
                expandidas.add(normalizar_texto(sinonimo))

        for chave, sinonimos in SINONIMOS.items():
            sinonimos_normalizados = {normalizar_texto(s) for s in sinonimos}
            if palavra in sinonimos_normalizados:
                expandidas.add(normalizar_texto(chave))
                expandidas.update(sinonimos_normalizados)

    return expandidas


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

def detectar_erros_linguisticos(texto: str):
    erros = []
    avisos = []

    encontrados = tokenizar_palavras(texto)

    for match in encontrados:
        palavra_original = match.group(0)
        palavra = palavra_original.lower()

        if len(palavra) <= 1:
            continue

        if palavra in PALAVRAS_PERMITIDAS:
            continue

        if palavra in ABREVIACOES_PROIBIDAS:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(
                f'A palavra "{palavra_original}" parece abreviação. Prefira "{ABREVIACOES_PROIBIDAS[palavra]}".'
            )
            continue

        if spell.known([palavra]):
            continue

        sugestao = spell.correction(palavra)

        if not sugestao:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(f'A palavra "{palavra_original}" não foi reconhecida no português.')
            continue

        if remover_acentos(sugestao) == remover_acentos(palavra) and sugestao != palavra:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(
                f'A palavra "{palavra_original}" parece estar sem acento. Sugestão: "{sugestao}".'
            )
        elif sugestao != palavra:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(
                f'A palavra "{palavra_original}" pode estar incorreta. Sugestão: "{sugestao}".'
            )

    return erros, avisos


def validar_pontuacao_final(texto: str) -> bool:
    texto = texto.strip()
    if not texto:
        return False
    return texto[-1] in [".", "?", "!"]


def validar_primeira_letra_maiuscula(texto: str) -> bool:
    texto = texto.strip()
    for char in texto:
        if char.isalpha():
            return char.isupper()
    return False


def validar_tamanho_minimo(resposta: str, resposta_esperada: str):
    resposta = resposta.strip()
    resposta_esperada = resposta_esperada.strip()

    tamanho_esperado = len(resposta_esperada)
    tamanho_resposta = len(resposta)

    minimo = max(25, int(tamanho_esperado * 0.6))
    return tamanho_resposta >= minimo, minimo


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


@app.route("/")
def index():
    return render_template("chat.html", atendimentos=atendimentos)


@app.route("/responder", methods=["POST"])
def responder():
    data = request.get_json()
    if not data:
        return jsonify({"erro": "Requisição inválida."}), 400

    id_atendimento = data.get("id")
    resposta = (data.get("resposta") or "").strip()

    if id_atendimento is None or id_atendimento < 0 or id_atendimento >= len(atendimentos):
        return jsonify({"erro": "Atendimento inválido."}), 400

    if not resposta:
        return jsonify({"erro": "Resposta vazia."}), 400

    at = atendimentos[id_atendimento]

    if at["finalizado"]:
        return jsonify({
            "mensagens": at["mensagens"],
            "erros": 0,
            "erros_detalhados": [],
            "avisos": [],
            "total_erros": at["total_erros"],
            "media_coerencia": at["media_coerencia"],
            "media_empatia": at["media_empatia"],
            "media_tempo": at["media_tempo"],
            "nota": calcular_nota(at),
            "nivel": classificar_nivel(calcular_nota(at)),
            "tempo_resposta": 0,
            "sugestao": at["resposta_esperada"],
            "finalizado": True
        })

    etapa = at["etapa_atual"]

    if etapa >= len(at["fluxo"]):
        at["finalizado"] = True
        return jsonify({
            "mensagens": at["mensagens"],
            "erros": 0,
            "erros_detalhados": [],
            "avisos": [],
            "total_erros": at["total_erros"],
            "media_coerencia": at["media_coerencia"],
            "media_empatia": at["media_empatia"],
            "media_tempo": at["media_tempo"],
            "nota": calcular_nota(at),
            "nivel": classificar_nivel(calcular_nota(at)),
            "tempo_resposta": 0,
            "sugestao": at["resposta_esperada"],
            "finalizado": True
        })

    agora = time.time()
    if at["ultimo_tempo_backend"] is None:
        tempo_resposta_segundos = 0
    else:
        tempo_resposta_segundos = round(agora - at["ultimo_tempo_backend"], 1)

    at["resposta_esperada"] = at["fluxo"][etapa]["resposta_esperada"]

    at["mensagens"].append({
        "tipo": "operador",
        "texto": resposta
    })

    erros, avisos = detectar_erros_linguisticos(resposta)

    pontuacao_ok = validar_pontuacao_final(resposta)
    if not pontuacao_ok:
        avisos.append("Finalize a frase com ponto, interrogação ou exclamação.")

    maiuscula_ok = validar_primeira_letra_maiuscula(resposta)
    if not maiuscula_ok:
        for i, char in enumerate(resposta):
            if char.isalpha():
                erros.append({
                    "offset": i,
                    "length": 1
                })
                break
        avisos.append("Comece a frase com letra maiúscula.")

    tamanho_ok, minimo_necessario = validar_tamanho_minimo(resposta, at["resposta_esperada"])
    if not tamanho_ok:
        avisos.append(f"Resposta muito curta. Use pelo menos {minimo_necessario} caracteres.")

    qtd_erros = len(erros)
    coerencia = calcular_coerencia(resposta, at)
    empatia = avaliar_empatia(resposta)
    nota_tempo = avaliar_tempo(tempo_resposta_segundos)

    if not pontuacao_ok:
        coerencia = max(0, coerencia - 10)

    if not maiuscula_ok:
        coerencia = max(0, coerencia - 10)

    if not tamanho_ok:
        coerencia = max(0, coerencia - 25)

    at["avaliacoes"].append({
        "erros": qtd_erros,
        "coerencia": coerencia,
        "empatia": empatia,
        "tempo": nota_tempo,
        "tempo_segundos": tempo_resposta_segundos,
        "avisos": avisos
    })

    at["total_erros"] += qtd_erros
    at["total_respostas"] += 1
    at["media_coerencia"] = sum(a["coerencia"] for a in at["avaliacoes"]) / at["total_respostas"]
    at["media_empatia"] = sum(a["empatia"] for a in at["avaliacoes"]) / at["total_respostas"]
    at["media_tempo"] = sum(a["tempo"] for a in at["avaliacoes"]) / at["total_respostas"]

    at["etapa_atual"] += 1

    if at["etapa_atual"] < len(at["fluxo"]):
        proxima_msg = at["fluxo"][at["etapa_atual"]]["cliente"]
        at["mensagens"].append({
            "tipo": "cliente",
            "texto": proxima_msg
        })
        at["resposta_esperada"] = at["fluxo"][at["etapa_atual"]]["resposta_esperada"]
        at["ultimo_tempo_backend"] = time.time()
    else:
        at["finalizado"] = True

    nota_final = calcular_nota(at)

    return jsonify({
        "mensagens": at["mensagens"],
        "erros": qtd_erros,
        "erros_detalhados": erros,
        "avisos": avisos,
        "total_erros": at["total_erros"],
        "media_coerencia": at["media_coerencia"],
        "media_empatia": at["media_empatia"],
        "media_tempo": at["media_tempo"],
        "nota": nota_final,
        "nivel": classificar_nivel(nota_final),
        "tempo_resposta": tempo_resposta_segundos,
        "sugestao": at["resposta_esperada"],
        "finalizado": at["finalizado"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)