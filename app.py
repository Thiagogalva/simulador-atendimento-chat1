from flask import Flask, render_template, request, jsonify, session
from spellchecker import SpellChecker
import re
import unicodedata
import time
import sqlite3
import uuid
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "troque-esta-chave-por-uma-chave-secreta-forte"

DB_NAME = "simulador.db"
TEMPO_LIMITE_CHAT = 50
INTERVALO_ENTRE_CHATS = 50

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

BASE_ATENDIMENTOS = [
    {
        "id": 0,
        "titulo": "Tarifa / estorno",
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
        ]
    },
    {
        "id": 1,
        "titulo": "Pix com bloqueio cautelar",
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
        ]
    },
    {
        "id": 2,
        "titulo": "Conta bloqueada / Pix indisponível",
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
        ]
    }
]


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_uuid TEXT UNIQUE NOT NULL,
            criado_em TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atendimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_uuid TEXT NOT NULL,
            id_publico INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            fluxo_json TEXT NOT NULL,
            etapa_atual INTEGER NOT NULL DEFAULT 0,
            total_erros INTEGER NOT NULL DEFAULT 0,
            total_respostas INTEGER NOT NULL DEFAULT 0,
            media_coerencia REAL NOT NULL DEFAULT 0,
            media_empatia REAL NOT NULL DEFAULT 0,
            media_tempo REAL NOT NULL DEFAULT 0,
            resposta_esperada TEXT NOT NULL,
            finalizado INTEGER NOT NULL DEFAULT 0,
            bloqueado_tempo INTEGER NOT NULL DEFAULT 0,
            ultimo_tempo_backend REAL,
            UNIQUE(usuario_uuid, id_publico)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atendimento_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (atendimento_id) REFERENCES atendimentos (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS avaliacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atendimento_id INTEGER NOT NULL,
            erros INTEGER NOT NULL DEFAULT 0,
            coerencia INTEGER NOT NULL DEFAULT 0,
            empatia INTEGER NOT NULL DEFAULT 0,
            tempo INTEGER NOT NULL DEFAULT 0,
            tempo_segundos REAL NOT NULL DEFAULT 0,
            avisos_json TEXT NOT NULL DEFAULT '[]',
            criado_em TEXT NOT NULL,
            FOREIGN KEY (atendimento_id) REFERENCES atendimentos (id)
        )
    """)

    conn.commit()
    conn.close()


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


def garantir_usuario_no_banco(usuario_uuid: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM usuarios WHERE usuario_uuid = ?",
        (usuario_uuid,)
    )
    usuario = cursor.fetchone()

    if not usuario:
        cursor.execute(
            "INSERT INTO usuarios (usuario_uuid, criado_em) VALUES (?, ?)",
            (usuario_uuid, datetime.now().isoformat())
        )
        conn.commit()

    conn.close()


def limpar_simulacao_usuario(usuario_uuid: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM atendimentos WHERE usuario_uuid = ?", (usuario_uuid,))
    atendimentos_ids = [row["id"] for row in cursor.fetchall()]

    for atendimento_id in atendimentos_ids:
        cursor.execute("DELETE FROM mensagens WHERE atendimento_id = ?", (atendimento_id,))
        cursor.execute("DELETE FROM avaliacoes WHERE atendimento_id = ?", (atendimento_id,))

    cursor.execute("DELETE FROM atendimentos WHERE usuario_uuid = ?", (usuario_uuid,))

    conn.commit()
    conn.close()


def inicializar_atendimentos_usuario(usuario_uuid: str):
    conn = get_connection()
    cursor = conn.cursor()

    for item in BASE_ATENDIMENTOS:
        primeiro_passo = item["fluxo"][0]

        cursor.execute("""
            INSERT INTO atendimentos (
                usuario_uuid,
                id_publico,
                titulo,
                fluxo_json,
                etapa_atual,
                total_erros,
                total_respostas,
                media_coerencia,
                media_empatia,
                media_tempo,
                resposta_esperada,
                finalizado,
                bloqueado_tempo,
                ultimo_tempo_backend
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            usuario_uuid,
            item["id"],
            item["titulo"],
            json.dumps(item["fluxo"], ensure_ascii=False),
            0,
            0,
            0,
            0,
            0,
            0,
            primeiro_passo["resposta_esperada"],
            0,
            0,
            None
        ))

        atendimento_db_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO mensagens (atendimento_id, tipo, texto, criado_em)
            VALUES (?, ?, ?, ?)
        """, (
            atendimento_db_id,
            "cliente",
            primeiro_passo["cliente"],
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()


def reiniciar_simulacao():
    session["simulacao_iniciada_em"] = time.time()


@app.before_request
def garantir_usuario():
    if "usuario_id" not in session:
        session["usuario_id"] = str(uuid.uuid4())

    garantir_usuario_no_banco(session["usuario_id"])


def buscar_mensagens(cursor, atendimento_db_id: int):
    cursor.execute("""
        SELECT tipo, texto
        FROM mensagens
        WHERE atendimento_id = ?
        ORDER BY id
    """, (atendimento_db_id,))
    return [{"tipo": row["tipo"], "texto": row["texto"]} for row in cursor.fetchall()]


def buscar_avaliacoes(cursor, atendimento_db_id: int):
    cursor.execute("""
        SELECT erros, coerencia, empatia, tempo, tempo_segundos, avisos_json
        FROM avaliacoes
        WHERE atendimento_id = ?
        ORDER BY id
    """, (atendimento_db_id,))
    avaliacoes = []
    for row in cursor.fetchall():
        avaliacoes.append({
            "erros": row["erros"],
            "coerencia": row["coerencia"],
            "empatia": row["empatia"],
            "tempo": row["tempo"],
            "tempo_segundos": row["tempo_segundos"],
            "avisos": json.loads(row["avisos_json"] or "[]")
        })
    return avaliacoes


def calcular_liberado_em(id_publico: int) -> float:
    return session["simulacao_iniciada_em"] + (id_publico * INTERVALO_ENTRE_CHATS)


def calcular_inicio_turno(at: dict) -> float:
    if at["ultimo_tempo_backend"] is not None:
        return at["ultimo_tempo_backend"]
    return calcular_liberado_em(at["id"])


def atendimento_liberado(at: dict) -> bool:
    return time.time() >= calcular_liberado_em(at["id"])


def atendimento_expirado(at: dict) -> bool:
    if at["finalizado"]:
        return False
    if not atendimento_liberado(at):
        return False

    inicio_turno = calcular_inicio_turno(at)
    return (time.time() - inicio_turno) >= TEMPO_LIMITE_CHAT


def montar_atendimento_dict(row, cursor):
    atendimento = {
        "db_id": row["id"],
        "id": row["id_publico"],
        "titulo": row["titulo"],
        "fluxo": json.loads(row["fluxo_json"]),
        "etapa_atual": row["etapa_atual"],
        "avaliacoes": buscar_avaliacoes(cursor, row["id"]),
        "total_erros": row["total_erros"],
        "total_respostas": row["total_respostas"],
        "media_coerencia": row["media_coerencia"],
        "media_empatia": row["media_empatia"],
        "media_tempo": row["media_tempo"],
        "resposta_esperada": row["resposta_esperada"],
        "finalizado": bool(row["finalizado"]),
        "bloqueado_tempo": bool(row["bloqueado_tempo"]),
        "ultimo_tempo_backend": row["ultimo_tempo_backend"],
        "mensagens": buscar_mensagens(cursor, row["id"]),
        "liberado_em": calcular_liberado_em(row["id_publico"])
    }

    expirado = atendimento_expirado(atendimento)
    atendimento["bloqueado_tempo"] = atendimento["bloqueado_tempo"] or expirado
    return atendimento


def listar_atendimentos_usuario(usuario_uuid: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM atendimentos
        WHERE usuario_uuid = ?
        ORDER BY id_publico
    """, (usuario_uuid,))

    atendimentos = [montar_atendimento_dict(row, cursor) for row in cursor.fetchall()]
    conn.close()
    return atendimentos


def buscar_atendimento_usuario(usuario_uuid: str, id_publico: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM atendimentos
        WHERE usuario_uuid = ? AND id_publico = ?
    """, (usuario_uuid, id_publico))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    atendimento = montar_atendimento_dict(row, cursor)
    conn.close()
    return atendimento


def salvar_estado_atendimento(at):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE atendimentos
        SET
            etapa_atual = ?,
            total_erros = ?,
            total_respostas = ?,
            media_coerencia = ?,
            media_empatia = ?,
            media_tempo = ?,
            resposta_esperada = ?,
            finalizado = ?,
            bloqueado_tempo = ?,
            ultimo_tempo_backend = ?
        WHERE id = ?
    """, (
        at["etapa_atual"],
        at["total_erros"],
        at["total_respostas"],
        at["media_coerencia"],
        at["media_empatia"],
        at["media_tempo"],
        at["resposta_esperada"],
        1 if at["finalizado"] else 0,
        1 if at["bloqueado_tempo"] else 0,
        at["ultimo_tempo_backend"],
        at["db_id"]
    ))

    conn.commit()
    conn.close()


def adicionar_mensagem(atendimento_db_id: int, tipo: str, texto: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO mensagens (atendimento_id, tipo, texto, criado_em)
        VALUES (?, ?, ?, ?)
    """, (atendimento_db_id, tipo, texto, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def adicionar_avaliacao(atendimento_db_id: int, erros: int, coerencia: int, empatia: int, tempo_nota: int,
                        tempo_segundos: float, avisos: list):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO avaliacoes (
            atendimento_id, erros, coerencia, empatia, tempo, tempo_segundos, avisos_json, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        atendimento_db_id,
        erros,
        coerencia,
        empatia,
        tempo_nota,
        tempo_segundos,
        json.dumps(avisos, ensure_ascii=False),
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def resposta_api_atendimento(at, qtd_erros=0, erros_detalhados=None, avisos=None, tempo_resposta=0):
    if erros_detalhados is None:
        erros_detalhados = []
    if avisos is None:
        avisos = []

    nota_final = calcular_nota(at)

    return {
        "mensagens": at["mensagens"],
        "erros": qtd_erros,
        "erros_detalhados": erros_detalhados,
        "avisos": avisos,
        "total_erros": at["total_erros"],
        "media_coerencia": at["media_coerencia"],
        "media_empatia": at["media_empatia"],
        "media_tempo": at["media_tempo"],
        "nota": nota_final,
        "nivel": classificar_nivel(nota_final),
        "tempo_resposta": tempo_resposta,
        "sugestao": at["resposta_esperada"],
        "finalizado": at["finalizado"],
        "bloqueado_tempo": at["bloqueado_tempo"],
        "liberado_em": at["liberado_em"]
    }


@app.route("/")
def index():
    usuario_uuid = session["usuario_id"]

    reiniciar_simulacao()
    limpar_simulacao_usuario(usuario_uuid)
    inicializar_atendimentos_usuario(usuario_uuid)

    atendimentos = listar_atendimentos_usuario(usuario_uuid)

    return render_template(
        "chat.html",
        atendimentos=atendimentos,
        simulacao_iniciada_em=session["simulacao_iniciada_em"],
        tempo_limite_chat=TEMPO_LIMITE_CHAT,
        intervalo_entre_chats=INTERVALO_ENTRE_CHATS
    )


@app.route("/responder", methods=["POST"])
def responder():
    data = request.get_json()
    if not data:
        return jsonify({"erro": "Requisição inválida."}), 400

    id_atendimento = data.get("id")
    resposta = (data.get("resposta") or "").strip()

    if id_atendimento is None:
        return jsonify({"erro": "Atendimento inválido."}), 400

    if not isinstance(id_atendimento, int):
        try:
            id_atendimento = int(id_atendimento)
        except (TypeError, ValueError):
            return jsonify({"erro": "Atendimento inválido."}), 400

    if not resposta:
        return jsonify({"erro": "Resposta vazia."}), 400

    at = buscar_atendimento_usuario(session["usuario_id"], id_atendimento)

    if not at:
        return jsonify({"erro": "Atendimento inválido."}), 400

    if at["finalizado"]:
        return jsonify(resposta_api_atendimento(at, tempo_resposta=0))

    if not atendimento_liberado(at):
        return jsonify({"erro": "Este atendimento ainda não foi liberado para resposta."}), 403

    if atendimento_expirado(at):
        at["bloqueado_tempo"] = True
        salvar_estado_atendimento(at)
        return jsonify({"erro": "O tempo deste atendimento expirou. A digitação está bloqueada para este chat."}), 403

    etapa = at["etapa_atual"]

    if etapa >= len(at["fluxo"]):
        at["finalizado"] = True
        salvar_estado_atendimento(at)
        at = buscar_atendimento_usuario(session["usuario_id"], id_atendimento)
        return jsonify(resposta_api_atendimento(at, tempo_resposta=0))

    inicio_turno = calcular_inicio_turno(at)
    tempo_resposta_segundos = round(max(0, time.time() - inicio_turno), 1)

    at["resposta_esperada"] = at["fluxo"][etapa]["resposta_esperada"]

    adicionar_mensagem(at["db_id"], "operador", resposta)
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

    avaliacao = {
        "erros": qtd_erros,
        "coerencia": coerencia,
        "empatia": empatia,
        "tempo": nota_tempo,
        "tempo_segundos": tempo_resposta_segundos,
        "avisos": avisos
    }

    adicionar_avaliacao(
        at["db_id"],
        qtd_erros,
        coerencia,
        empatia,
        nota_tempo,
        tempo_resposta_segundos,
        avisos
    )
    at["avaliacoes"].append(avaliacao)

    at["total_erros"] += qtd_erros
    at["total_respostas"] += 1
    at["media_coerencia"] = sum(a["coerencia"] for a in at["avaliacoes"]) / at["total_respostas"]
    at["media_empatia"] = sum(a["empatia"] for a in at["avaliacoes"]) / at["total_respostas"]
    at["media_tempo"] = sum(a["tempo"] for a in at["avaliacoes"]) / at["total_respostas"]

    at["etapa_atual"] += 1
    at["bloqueado_tempo"] = False

    if at["etapa_atual"] < len(at["fluxo"]):
        proxima_msg = at["fluxo"][at["etapa_atual"]]["cliente"]
        adicionar_mensagem(at["db_id"], "cliente", proxima_msg)
        at["mensagens"].append({
            "tipo": "cliente",
            "texto": proxima_msg
        })
        at["resposta_esperada"] = at["fluxo"][at["etapa_atual"]]["resposta_esperada"]
        at["ultimo_tempo_backend"] = time.time()
    else:
        at["finalizado"] = True
        at["ultimo_tempo_backend"] = time.time()

    salvar_estado_atendimento(at)

    at = buscar_atendimento_usuario(session["usuario_id"], id_atendimento)

    return jsonify(resposta_api_atendimento(
        at,
        qtd_erros=qtd_erros,
        erros_detalhados=erros,
        avisos=avisos,
        tempo_resposta=tempo_resposta_segundos
    ))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
else:
    init_db()