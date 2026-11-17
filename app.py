from flask import Flask, render_template, request, jsonify, session, g, redirect, url_for
import time

from config import (
    SECRET_KEY,
    TEMPO_LIMITE_CHAT,
    INTERVALO_ENTRE_CHATS,
    DEBUG,
    SESSION_COOKIE_SECURE
)
from database.init_db import init_db
from repositories.usuario_repository import garantir_usuario_no_banco
from repositories.operador_repository import buscar_operador_por_id
from routes.auth import bp as auth_bp
from routes.conta import bp as conta_bp
from routes.painel import bp as painel_bp
from routes.supervisor import bp as supervisor_bp
from services.auth_service import fingerprint_senha
from routes.seguranca import csrf_valido, token_csrf
from services.dica_service import NIVEL_MAXIMO, gerar_dica
from repositories.atendimento_repository import (
    limpar_simulacao_usuario,
    inicializar_atendimentos_usuario,
    listar_atendimentos_usuario,
    buscar_atendimento_usuario,
    salvar_estado_atendimento
)
from repositories.mensagem_repository import adicionar_mensagem
from repositories.avaliacao_repository import (
    adicionar_avaliacao,
    buscar_ultima_avaliacao,
    salvar_feedback_avaliacao
)
from services.feedback_service import feedback_resposta
from services.simulacao_service import reiniciar_simulacao
from services.tempo_service import (
    MODO_TREINO,
    MODOS,
    calcular_inicio_turno,
    atendimento_liberado,
    atendimento_expirado
)
from services.texto_service import (
    detectar_erros_linguisticos,
    validar_pontuacao_final,
    validar_primeira_letra_maiuscula,
    validar_tamanho_minimo,
    vocabulario_do_fluxo
)
from services.avaliacao_service import (
    calcular_coerencia,
    avaliar_tempo,
    calcular_nota,
    classificar_nivel
)
from services.tom_service import analisar_tom
from services.cliente_service import (
    decidir_reacao,
    mensagem_encerramento,
    mensagem_repeticao,
    mensagem_proxima
)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
)
app.register_blueprint(auth_bp)
app.register_blueprint(conta_bp)
app.register_blueprint(painel_bp)
app.register_blueprint(supervisor_bp)

if SECRET_KEY == "dev-only-troque-em-producao" and not DEBUG:
    app.logger.warning("SECRET_KEY padrão em uso. Defina a variável de ambiente SECRET_KEY em produção.")

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
        "modo": at["modo"],
        "etapa_atual": at["etapa_atual"],
        "total_passos": len(at["fluxo"]),
        "dica_nivel": at["dica_nivel"],
        "dicas_usadas": at["dicas_usadas"],
        "finalizado": at["finalizado"],
        "bloqueado_tempo": at["bloqueado_tempo"],
        "liberado_em": at["liberado_em"],
        "ultimo_tempo_backend": at["ultimo_tempo_backend"],
        "irritacao": at["irritacao"],
        "humor": at["humor"],
        "encerrado_por_cliente": at["encerrado_por_cliente"],
        "servidor_agora": time.time()
    }

ENDPOINTS_PUBLICOS = {"auth.login", "auth.registro", "auth.recuperar", "static"}
ENDPOINTS_SENHA_TEMPORARIA = {"conta.senha", "auth.sair"}
ENDPOINTS_JSON = {"responder", "dica", "feedback", "painel.finalizar", "painel.feedback_final"}


@app.before_request
def exigir_login():
    """Todas as telas (exceto login/cadastro) exigem um operador autenticado e existente."""
    if request.endpoint is None or request.endpoint in ENDPOINTS_PUBLICOS:
        return None

    operador = None
    if session.get("operador_id"):
        operador = buscar_operador_por_id(session["operador_id"])

    # Conta removida/desativada ou senha trocada em outro lugar: a sessão deixa de valer.
    if (operador is None or not operador["ativo"]
            or session.get("sv") != fingerprint_senha(operador["senha_hash"])):
        session.clear()
        if request.endpoint in ENDPOINTS_JSON:
            return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
        return redirect(url_for("auth.login"))

    g.operador = operador

    # Senha temporária (definida por um supervisor): só libera depois de escolher a própria senha.
    if operador["senha_temporaria"] and request.endpoint not in ENDPOINTS_SENHA_TEMPORARIA:
        if request.endpoint in ENDPOINTS_JSON:
            return jsonify({"erro": "Defina uma nova senha para continuar."}), 403
        return redirect(url_for("conta.senha"))

    if request.method == "POST" and request.endpoint not in ENDPOINTS_JSON and not csrf_valido():
        return "Requisição inválida (CSRF). Volte e tente novamente.", 400
    return None


@app.errorhandler(403)
def proibido(_erro):
    if request.path in ("/responder", "/dica", "/feedback", "/finalizar", "/feedback-final"):
        return jsonify({"erro": "Acesso negado."}), 403
    return render_template("erro.html", titulo="Acesso negado",
                           mensagem="Você não tem permissão para acessar esta página."), 403


@app.errorhandler(404)
def nao_encontrado(_erro):
    return render_template("erro.html", titulo="Página não encontrada",
                           mensagem="O endereço informado não existe."), 404


@app.context_processor
def injetar_csrf():
    return {"csrf_token": token_csrf}


CAMPOS_PRIVADOS = ("fluxo", "resposta_esperada", "palavras_criticas", "avaliacoes")


def atendimento_publico(at: dict) -> dict:
    """O que pode ir para o navegador: nunca o roteiro nem as respostas esperadas."""
    publico = {k: v for k, v in at.items() if k not in CAMPOS_PRIVADOS}
    publico["total_passos"] = len(at["fluxo"])
    return publico

def simulacao_em_andamento():
    """Modo da simulação ainda não concluída desta sessão, ou None."""
    iniciada_em = session.get("simulacao_iniciada_em")
    if iniciada_em is None:
        return None
    atendimentos = listar_atendimentos_usuario(session["usuario_id"], iniciada_em)
    if atendimentos and not all(a["finalizado"] or a["bloqueado_tempo"] for a in atendimentos):
        return atendimentos[0]["modo"]
    return None


@app.route("/")
def index():
    return render_template("iniciar.html", em_andamento=simulacao_em_andamento())


@app.route("/iniciar", methods=["POST"])
def iniciar():
    modo = request.form.get("modo", "")
    if modo not in MODOS:
        return render_template("iniciar.html", em_andamento=simulacao_em_andamento(),
                               erro="Escolha um modo válido."), 400

    usuario_uuid = session["usuario_id"]
    garantir_usuario_no_banco(usuario_uuid)

    reiniciar_simulacao(session)
    limpar_simulacao_usuario(usuario_uuid)
    if inicializar_atendimentos_usuario(usuario_uuid, modo) == 0:
        session.pop("simulacao_iniciada_em", None)
        return render_template("iniciar.html", em_andamento=None,
                               erro="Não há cenários ativos. Peça a um supervisor para ativar algum."), 503
    return redirect(url_for("simulacao"), code=303)


@app.route("/simulacao")
def simulacao():
    iniciada_em = session.get("simulacao_iniciada_em")
    if iniciada_em is None:
        return redirect(url_for("index"))

    atendimentos = listar_atendimentos_usuario(session["usuario_id"], iniciada_em)
    if not atendimentos:
        return redirect(url_for("index"))

    return render_template(
        "chat.html",
        atendimentos=[atendimento_publico(a) for a in atendimentos],
        modo=atendimentos[0]["modo"],
        simulacao_iniciada_em=iniciada_em,
        tempo_limite_chat=TEMPO_LIMITE_CHAT,
        intervalo_entre_chats=INTERVALO_ENTRE_CHATS,
        servidor_agora=time.time(),
        operador_nome=g.operador["nome"]
    )


def _ler_id_atendimento(data):
    if not data or data.get("id") is None:
        return None
    try:
        return int(data.get("id"))
    except (TypeError, ValueError):
        return None


@app.route("/dica", methods=["POST"])
def dica():
    """Dicas progressivas (só no modo treino): 1 = pontos a cobrir, 2 = resposta sugerida."""
    corpo = request.get_json(silent=True) or {}
    id_atendimento = _ler_id_atendimento(corpo)
    iniciada_em = session.get("simulacao_iniciada_em")

    if id_atendimento is None:
        return jsonify({"erro": "Atendimento inválido."}), 400
    if iniciada_em is None:
        return jsonify({"erro": "Sessão expirada. Recarregue a página para iniciar uma nova simulação."}), 409

    at = buscar_atendimento_usuario(session["usuario_id"], id_atendimento, iniciada_em)
    if not at:
        return jsonify({"erro": "Atendimento inválido."}), 400
    if at["modo"] != MODO_TREINO:
        return jsonify({"erro": "Dicas só estão disponíveis no modo treino."}), 403
    if at["finalizado"] or at["etapa_atual"] >= len(at["fluxo"]):
        return jsonify({"erro": "Este atendimento já foi encerrado."}), 409

    if corpo.get("atual"):
        # Só reexibe a dica já liberada neste passo (ex.: depois de recarregar a página).
        if at["dica_nivel"] == 0:
            return jsonify({"nivel": 0, "texto": None, "ultimo_nivel": False, "dicas_usadas": at["dicas_usadas"]})
        nivel = at["dica_nivel"]
    else:
        nivel = min(at["dica_nivel"] + 1, NIVEL_MAXIMO)
        if nivel > at["dica_nivel"]:
            at["dica_nivel"] = nivel
            at["dicas_usadas"] += 1
            salvar_estado_atendimento(at)

    texto = gerar_dica(at["fluxo"][at["etapa_atual"]]["resposta_esperada"], nivel, at["palavras_criticas"])
    return jsonify({
        "nivel": nivel,
        "texto": texto,
        "ultimo_nivel": nivel >= NIVEL_MAXIMO,
        "dicas_usadas": at["dicas_usadas"],
    })


@app.route("/feedback", methods=["POST"])
def feedback():
    """Feedback em texto sobre a última resposta (só no treino; na avaliação o feedback vem ao final)."""
    id_atendimento = _ler_id_atendimento(request.get_json(silent=True))
    iniciada_em = session.get("simulacao_iniciada_em")

    if id_atendimento is None:
        return jsonify({"erro": "Atendimento inválido."}), 400
    if iniciada_em is None:
        return jsonify({"erro": "Sessão expirada. Recarregue a página para iniciar uma nova simulação."}), 409

    at = buscar_atendimento_usuario(session["usuario_id"], id_atendimento, iniciada_em)
    if not at:
        return jsonify({"erro": "Atendimento inválido."}), 400
    if at["modo"] != MODO_TREINO:
        return jsonify({"erro": "Na avaliação o feedback só é liberado ao final da simulação."}), 403

    av = buscar_ultima_avaliacao(at["db_id"])
    if av is None:
        return jsonify({"erro": "Envie uma resposta antes de pedir feedback."}), 409

    if av["feedback_texto"]:
        return jsonify({"texto": av["feedback_texto"], "origem": av["feedback_origem"],
                        "aviso": None, "em_cache": True})

    etapa = av["etapa"] if av["etapa"] is not None else max(0, at["etapa_atual"] - 1)
    etapa = min(etapa, len(at["fluxo"]) - 1)
    passo = at["fluxo"][etapa]

    resultado = feedback_resposta(g.operador["id"], av, passo["cliente"],
                                  passo["resposta_esperada"], at["palavras_criticas"])
    if resultado["origem"] == "ia":  # só guarda o que veio da IA; o fallback pode ser refeito depois
        salvar_feedback_avaliacao(av["id"], resultado["texto"], "ia")
    resultado["em_cache"] = False
    return jsonify(resultado)


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

    simulacao_iniciada_em = session.get("simulacao_iniciada_em")
    if simulacao_iniciada_em is None:
        return jsonify({"erro": "Sessão expirada. Recarregue a página para iniciar uma nova simulação."}), 409

    at = buscar_atendimento_usuario(
        session["usuario_id"],
        id_atendimento,
        simulacao_iniciada_em
    )

    if not at:
        return jsonify({"erro": "Atendimento inválido."}), 400

    if at["finalizado"]:
        return jsonify(resposta_api_atendimento(at, tempo_resposta=0))

    if not atendimento_liberado(at, simulacao_iniciada_em):
        return jsonify({"erro": "Este atendimento ainda não foi liberado para resposta."}), 403

    if atendimento_expirado(at, simulacao_iniciada_em):
        at["bloqueado_tempo"] = True
        salvar_estado_atendimento(at)
        return jsonify({"erro": "O tempo deste atendimento expirou. A digitação está bloqueada para este chat."}), 403

    etapa = at["etapa_atual"]

    if etapa >= len(at["fluxo"]):
        at["finalizado"] = True
        salvar_estado_atendimento(at)
        at = buscar_atendimento_usuario(
            session["usuario_id"],
            id_atendimento,
            simulacao_iniciada_em
        )
        return jsonify(resposta_api_atendimento(at, tempo_resposta=0))

    inicio_turno = calcular_inicio_turno(at, simulacao_iniciada_em)
    tempo_resposta_segundos = round(max(0, time.time() - inicio_turno), 1)

    at["resposta_esperada"] = at["fluxo"][etapa]["resposta_esperada"]

    respostas_anteriores = [m["texto"] for m in at["mensagens"] if m["tipo"] == "operador"]

    adicionar_mensagem(at["db_id"], "operador", resposta)
    at["mensagens"].append({
        "tipo": "operador",
        "texto": resposta
    })

    erros, avisos = detectar_erros_linguisticos(resposta, vocabulario_do_fluxo(at["fluxo"]))

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
    analise_tom = analisar_tom(resposta, respostas_anteriores)
    empatia = analise_tom["empatia"]
    avisos.extend(analise_tom["avisos"])
    nota_tempo = 20 if at["modo"] == MODO_TREINO else avaliar_tempo(tempo_resposta_segundos)

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
        avisos,
        etapa=etapa,
        resposta_texto=resposta
    )
    at["avaliacoes"].append(avaliacao)

    at["total_erros"] += qtd_erros
    at["total_respostas"] += 1
    at["media_coerencia"] = sum(a["coerencia"] for a in at["avaliacoes"]) / at["total_respostas"]
    at["media_empatia"] = sum(a["empatia"] for a in at["avaliacoes"]) / at["total_respostas"]
    at["media_tempo"] = sum(a["tempo"] for a in at["avaliacoes"]) / at["total_respostas"]

    at["bloqueado_tempo"] = False

    # O cliente simulado reage à qualidade da resposta (ver services/cliente_service.py).
    decisao = decidir_reacao(
        coerencia=coerencia,
        sinais=analise_tom["sinais"],
        qtd_erros=qtd_erros,
        tempo_nota=nota_tempo,
        palavras=len(resposta.split()),
        irritacao=at["irritacao"],
        tentativas_etapa=at["tentativas_etapa"],
        ultima_etapa=(etapa == len(at["fluxo"]) - 1)
    )
    semente = at["db_id"] + etapa + at["tentativas_etapa"]
    at["irritacao"] = decisao["irritacao"]
    agora = time.time()

    def responder_como_cliente(texto, humor):
        adicionar_mensagem(at["db_id"], "cliente", texto, humor)
        at["mensagens"].append({"tipo": "cliente", "texto": texto, "humor": humor})

    if decisao["acao"] == "encerrar":
        responder_como_cliente(mensagem_encerramento(semente), "encerrado")
        at["finalizado"] = True
        at["encerrado_por_cliente"] = True
        at["ultimo_tempo_backend"] = agora

    elif decisao["acao"] == "repetir":
        # Mesma etapa: o operador precisa responder de novo ao que o cliente perguntou.
        at["tentativas_etapa"] += 1
        responder_como_cliente(
            mensagem_repeticao(decisao, at["fluxo"][etapa]["cliente"], semente),
            decisao["humor"]
        )
        at["ultimo_tempo_backend"] = agora

    else:
        at["tentativas_etapa"] = 0
        at["dica_nivel"] = 0
        at["etapa_atual"] += 1

        if at["etapa_atual"] < len(at["fluxo"]):
            proxima_msg = at["fluxo"][at["etapa_atual"]]["cliente"]
            humor_msg = decisao["humor"] if decisao["irritacao"] >= 30 else None
            responder_como_cliente(mensagem_proxima(decisao, proxima_msg, semente), humor_msg)
            at["resposta_esperada"] = at["fluxo"][at["etapa_atual"]]["resposta_esperada"]
        else:
            at["finalizado"] = True
        at["ultimo_tempo_backend"] = agora

    salvar_estado_atendimento(at)

    at = buscar_atendimento_usuario(
        session["usuario_id"],
        id_atendimento,
        simulacao_iniciada_em
    )

    return jsonify(resposta_api_atendimento(
        at,
        qtd_erros=qtd_erros,
        erros_detalhados=erros,
        avisos=avisos,
        tempo_resposta=tempo_resposta_segundos
    ))

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=DEBUG)
else:
    init_db()