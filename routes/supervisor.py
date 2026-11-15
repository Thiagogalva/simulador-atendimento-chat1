import csv
import io
from functools import wraps
from statistics import mean

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, session, url_for

from repositories.operador_repository import (
    PAPEIS,
    atualizar_senha,
    buscar_operador_por_id,
    definir_ativo,
    definir_papel,
    listar_auditoria,
    listar_operadores_com_estatisticas,
    registrar_auditoria,
)
from repositories.simulacao_repository import listar_simulacoes_do_operador, listar_todas_as_simulacoes
from services.auth_service import gerar_hash, gerar_senha_temporaria

bp = Blueprint("supervisor", __name__, url_prefix="/supervisor")


def requer_supervisor(funcao):
    @wraps(funcao)
    def protegida(*args, **kwargs):
        if not g.operador["e_supervisor"]:
            abort(403)
        return funcao(*args, **kwargs)
    return protegida


def _alvo_ou_404(operador_id: int):
    alvo = buscar_operador_por_id(operador_id)
    if alvo is None:
        abort(404)
    return alvo


def _recusar_se_for_si_mesmo(alvo, mensagem: str):
    if alvo["id"] == g.operador["id"]:
        flash(mensagem, "erro")
        return redirect(url_for("supervisor.painel"))
    return None


@bp.route("")
@requer_supervisor
def painel():
    operadores = listar_operadores_com_estatisticas()
    medias = [o["media"] for o in operadores if o["media"] is not None]
    resumo = {
        "operadores": sum(1 for o in operadores if o["ativo"]),
        "avaliacoes": sum(o["avaliacoes"] for o in operadores),
        "treinos": sum(o["treinos"] for o in operadores),
        "media": round(mean(medias), 1) if medias else None,
    }
    return render_template(
        "supervisor.html",
        operadores=operadores,
        resumo=resumo,
        auditoria=listar_auditoria(20),
        senha_gerada=session.pop("senha_temporaria_gerada", None),
        meu_id=g.operador["id"],
    )


@bp.route("/operadores/<int:operador_id>")
@requer_supervisor
def detalhe(operador_id):
    alvo = _alvo_ou_404(operador_id)
    simulacoes = listar_simulacoes_do_operador(operador_id)
    notas = [s["nota_geral"] for s in simulacoes if s["modo"] == "avaliacao"]
    return render_template(
        "supervisor_operador.html",
        alvo=alvo,
        simulacoes=simulacoes,
        media=round(mean(notas), 1) if notas else None,
        melhor=round(max(notas), 1) if notas else None,
    )


@bp.route("/operadores/<int:operador_id>/senha", methods=["POST"])
@requer_supervisor
def redefinir_senha(operador_id):
    alvo = _alvo_ou_404(operador_id)
    recusa = _recusar_se_for_si_mesmo(alvo, "Para trocar a sua própria senha use a página Conta.")
    if recusa:
        return recusa

    temporaria = gerar_senha_temporaria()
    atualizar_senha(alvo["id"], gerar_hash(temporaria), temporaria=True)
    registrar_auditoria(g.operador["id"], "redefiniu a senha", alvo["id"])
    session["senha_temporaria_gerada"] = {"nome": alvo["nome"], "usuario": alvo["usuario"], "senha": temporaria}
    return redirect(url_for("supervisor.painel"))


@bp.route("/operadores/<int:operador_id>/ativo", methods=["POST"])
@requer_supervisor
def alterar_ativo(operador_id):
    alvo = _alvo_ou_404(operador_id)
    recusa = _recusar_se_for_si_mesmo(alvo, "Você não pode desativar a sua própria conta.")
    if recusa:
        return recusa

    ativo = request.form.get("ativo") == "1"
    if not ativo and alvo["supervisor_fixo"]:
        flash("Este supervisor é definido na configuração do sistema e não pode ser desativado aqui.", "erro")
        return redirect(url_for("supervisor.painel"))

    definir_ativo(alvo["id"], ativo)
    registrar_auditoria(g.operador["id"], "reativou a conta" if ativo else "desativou a conta", alvo["id"])
    flash(f"Conta de {alvo['nome']} {'reativada' if ativo else 'desativada'}.", "ok")
    return redirect(url_for("supervisor.painel"))


@bp.route("/operadores/<int:operador_id>/papel", methods=["POST"])
@requer_supervisor
def alterar_papel(operador_id):
    alvo = _alvo_ou_404(operador_id)
    recusa = _recusar_se_for_si_mesmo(alvo, "Você não pode alterar o seu próprio papel.")
    if recusa:
        return recusa

    papel = request.form.get("papel", "")
    if papel not in PAPEIS:
        abort(400)
    if alvo["supervisor_fixo"]:
        flash("Este supervisor é definido na configuração do sistema e não pode ser rebaixado aqui.", "erro")
        return redirect(url_for("supervisor.painel"))

    definir_papel(alvo["id"], papel)
    registrar_auditoria(g.operador["id"], f"definiu o papel como {papel}", alvo["id"])
    flash(f"{alvo['nome']} agora é {papel}.", "ok")
    return redirect(url_for("supervisor.painel"))


def _celula(valor):
    """Evita injeção de fórmulas ao abrir o CSV no Excel/Planilhas."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


@bp.route("/exportar.csv")
@requer_supervisor
def exportar_csv():
    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(["finalizada_em_utc", "usuario", "nome", "modo", "nota_geral", "nivel",
                       "coerencia", "empatia", "tempo", "erros", "atendimentos"])
    for s in listar_todas_as_simulacoes():
        escritor.writerow([_celula(v) for v in (
            s["finalizada_em"], s["usuario"], s["nome"], s["modo"], s["nota_geral"], s["nivel"],
            s["media_coerencia"], s["media_empatia"], s["media_tempo"], s["total_erros"],
            s["total_atendimentos"],
        )])

    registrar_auditoria(g.operador["id"], "exportou o CSV de simulações")
    return Response(
        "\ufeff" + saida.getvalue(),  # BOM para o Excel reconhecer UTF-8
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=simulacoes.csv",
            "Cache-Control": "no-store",
        },
    )
