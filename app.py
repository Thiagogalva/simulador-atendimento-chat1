from flask import Flask, render_template, request, jsonify, session
import uuid
import time

from config import SECRET_KEY, TEMPO_LIMITE_CHAT, INTERVALO_ENTRE_CHATS
from database.init_db import init_db
from repositories.usuario_repository import garantir_usuario_no_banco
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
    avaliar_empatia,
    avaliar_tempo,
    calcular_nota,
    classificar_nivel
)

app = Flask(__name__)
app.secret_key = SECRET_KEY

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

@app.before_request
def garantir_usuario():
    if "usuario_id" not in session:
        session["usuario_id"] = str(uuid.uuid4())

    garantir_usuario_no_banco(session["usuario_id"])

@app.route("/")
def index():
    usuario_uuid = session["usuario_id"]

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

    simulacao_iniciada_em = session["simulacao_iniciada_em"]

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
    app.run(host="0.0.0.0", port=5000, debug=True)
else:
    init_db()