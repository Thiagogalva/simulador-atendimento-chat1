from statistics import mean

from flask import Blueprint, g, jsonify, render_template, request, session

from repositories.atendimento_repository import listar_atendimentos_usuario
from repositories.simulacao_repository import (
    PERIODOS_RANKING,
    listar_simulacoes_do_operador,
    posicao_do_operador,
    ranking,
    salvar_simulacao,
)
from services.avaliacao_service import calcular_nota, classificar_nivel

bp = Blueprint("painel", __name__)

ROTULOS_PERIODO = {"geral": "Geral", "30d": "Últimos 30 dias", "7d": "Últimos 7 dias"}


def montar_resumo(atendimentos: list) -> dict:
    """Resumo da simulação calculado só com o estado do servidor (nada vem do navegador)."""
    detalhes = []
    for at in atendimentos:
        nota = calcular_nota(at)
        if at["encerrado_por_cliente"]:
            status = "Encerrado pelo cliente"
        elif at["finalizado"]:
            status = "Finalizado"
        else:
            status = "Encerrado por tempo"
        detalhes.append({
            "id": at["id"],
            "titulo": at["titulo"],
            "nota": nota,
            "nivel": classificar_nivel(nota),
            "coerencia": round(at["media_coerencia"], 1),
            "empatia": round(at["media_empatia"], 1),
            "tempo": round(at["media_tempo"], 1),
            "erros": at["total_erros"],
            "status": status,
            "humor": at["humor"],
        })

    nota_geral = round(mean(d["nota"] for d in detalhes), 1) if detalhes else 0.0
    return {
        "nota_geral": nota_geral,
        "nivel": classificar_nivel(nota_geral),
        "media_coerencia": round(mean(d["coerencia"] for d in detalhes), 1) if detalhes else 0.0,
        "media_empatia": round(mean(d["empatia"] for d in detalhes), 1) if detalhes else 0.0,
        "media_tempo": round(mean(d["tempo"] for d in detalhes), 1) if detalhes else 0.0,
        "total_erros": sum(d["erros"] for d in detalhes),
        "total_atendimentos": len(detalhes),
        "detalhes": detalhes,
    }


def montar_grafico(notas_cronologicas: list, largura=640, altura=180, margem=24):
    """Pontos de um gráfico de linha (SVG) com a evolução das notas (0-100)."""
    if not notas_cronologicas:
        return None

    n = len(notas_cronologicas)
    area_x = largura - 2 * margem
    area_y = altura - 2 * margem

    pontos = []
    for i, nota in enumerate(notas_cronologicas):
        x = margem + (area_x / 2 if n == 1 else area_x * i / (n - 1))
        y = margem + area_y * (1 - max(0, min(100, nota)) / 100)
        pontos.append({"x": round(x, 1), "y": round(y, 1), "nota": nota})

    return {
        "largura": largura,
        "altura": altura,
        "margem": margem,
        "linha": " ".join(f"{p['x']},{p['y']}" for p in pontos),
        "pontos": pontos,
    }


@bp.route("/finalizar", methods=["POST"])
def finalizar():
    iniciada_em = session.get("simulacao_iniciada_em")
    if iniciada_em is None:
        return jsonify({"erro": "Sessão expirada. Inicie uma nova simulação."}), 409

    atendimentos = listar_atendimentos_usuario(session["usuario_id"], iniciada_em)
    if not atendimentos or not all(a["finalizado"] or a["bloqueado_tempo"] for a in atendimentos):
        return jsonify({"erro": "A simulação ainda não terminou."}), 409

    resumo = montar_resumo(atendimentos)
    simulacao_id, criada = salvar_simulacao(g.operador["id"], iniciada_em, resumo)
    posicao, total = posicao_do_operador(g.operador["id"])

    return jsonify({
        "id": simulacao_id,
        "salva_agora": criada,
        "nota_geral": resumo["nota_geral"],
        "nivel": resumo["nivel"],
        "posicao": posicao,
        "total_operadores": total,
    })


@bp.route("/historico")
def historico():
    simulacoes = listar_simulacoes_do_operador(g.operador["id"])
    notas = [s["nota_geral"] for s in simulacoes]

    resumo = None
    if simulacoes:
        resumo = {
            "total": len(simulacoes),
            "media": round(mean(notas), 1),
            "melhor": round(max(notas), 1),
            "ultima": round(notas[0], 1),
        }
        # Variação entre as 3 últimas e as 3 anteriores (quando há dados suficientes).
        if len(notas) >= 4:
            recentes = notas[:3]
            anteriores = notas[3:6]
            resumo["tendencia"] = round(mean(recentes) - mean(anteriores), 1)

    posicao, total = posicao_do_operador(g.operador["id"])
    ultimas_30 = list(reversed(notas[:30]))  # cronológico para o gráfico

    return render_template(
        "historico.html",
        simulacoes=simulacoes,
        resumo=resumo,
        grafico=montar_grafico(ultimas_30),
        posicao=posicao,
        total_operadores=total,
    )


@bp.route("/ranking")
def ranking_view():
    periodo = request.args.get("periodo", "geral")
    if periodo not in PERIODOS_RANKING:
        periodo = "geral"

    return render_template(
        "ranking.html",
        itens=ranking(periodo),
        periodo=periodo,
        periodos=ROTULOS_PERIODO,
        meu_id=g.operador["id"],
    )
