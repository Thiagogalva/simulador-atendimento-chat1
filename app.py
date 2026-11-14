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
from routes.painel import bp as painel_bp
from repositories.atendimento_repository import (
    limpar_simulacao_usuario,
    inicializar_atendimentos_usuario,
    listar_atendimentos_usuario,
    buscar_atendimento_usuario,
    salvar_estado_atendimento
)
from repositories.mensagem_repository import adicionar_mensagem
from repositories.avaliacao_repository import adicionar_avaliacao
from services.simulacao_service import reiniciar_simulacao
from services.tempo_service import (
    calcular_inicio_turno,
    atendimento_liberado,
    atendimento_expirado
)
from services.texto_service import (
    detectar_erros_linguisticos,
    validar_pontuacao_final,
    validar_primeira_letra_maiuscula,
    validar_tamanho_minimo
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
app.register_blueprint(painel_bp)

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
        "sugestao": at["resposta_esperada"],
        "finalizado": at["finalizado"],
        "bloqueado_tempo": at["bloqueado_tempo"],
        "liberado_em": at["liberado_em"],
        "ultimo_tempo_backend": at["ultimo_tempo_backend"],
        "irritacao": at["irritacao"],
        "humor": at["humor"],
        "encerrado_por_cliente": at["encerrado_por_cliente"],
        "servidor_agora": time.time()
    }

ENDPOINTS_PUBLICOS = {"auth.login", "auth.registro", "static"}
ENDPOINTS_JSON = {"responder", "painel.finalizar"}


@app.before_request
def exigir_login():
    """Todas as telas (exceto login/cadastro) exigem um operador autenticado e existente."""
    if request.endpoint is None or request.endpoint in ENDPOINTS_PUBLICOS:
        return None

    operador = None
    if session.get("operador_id"):
        operador = buscar_operador_por_id(session["operador_id"])

    if operador is None:
        session.clear()
        if request.endpoint in ENDPOINTS_JSON:
            return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
        return redirect(url_for("auth.login"))

    g.operador = operador
    return None

@app.route("/")
def index():
    usuario_uuid = session["usuario_id"]
    garantir_usuario_no_banco(usuario_uuid)

    reiniciar_simulacao(session)
    limpar_simulacao_usuario(usuario_uuid)
    inicializar_atendimentos_usuario(usuario_uuid)

    atendimentos = listar_atendimentos_usuario(
        usuario_uuid,
        session["simulacao_iniciada_em"]
    )

    return render_template(
        "chat.html",
        atendimentos=atendimentos,
        simulacao_iniciada_em=session["simulacao_iniciada_em"],
        tempo_limite_chat=TEMPO_LIMITE_CHAT,
        intervalo_entre_chats=INTERVALO_ENTRE_CHATS,
        servidor_agora=time.time(),
        operador_nome=g.operador["nome"]
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
    analise_tom = analisar_tom(resposta, respostas_anteriores)
    empatia = analise_tom["empatia"]
    avisos.extend(analise_tom["avisos"])
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