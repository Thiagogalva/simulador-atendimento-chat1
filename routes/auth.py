from flask import Blueprint, redirect, render_template, request, session, url_for

import config
from repositories.operador_repository import buscar_operador_por_usuario, obter_ou_criar_por_nome
from services.auth_service import chave_do_nome, limitador_nomes_novos, validar_nome

bp = Blueprint("auth", __name__)


def iniciar_sessao(operador: dict):
    """Sessão nova (e sem acesso de supervisor) vinculada ao nome informado."""
    session.clear()
    session["operador_id"] = operador["id"]
    session["operador_nome"] = operador["nome"]
    session["usuario_id"] = f"operador-{operador['id']}"


@bp.route("/identificar", methods=["GET", "POST"])
def identificar():
    """Único passo de entrada: o operador informa o nome (usado no histórico e no ranking)."""
    if request.method == "GET" and session.get("operador_id"):
        return redirect(url_for("index"))

    erros, status = [], 200
    nome = request.form.get("nome", "") if request.method == "POST" else ""

    if request.method == "POST":
        nome, erros = validar_nome(nome)

        if not erros:
            chave = chave_do_nome(nome)
            origem = f"nome|{request.remote_addr}"
            limitador_nomes_novos.max_falhas = config.NOMES_NOVOS_POR_HORA

            if buscar_operador_por_usuario(chave) is None and limitador_nomes_novos.bloqueado(origem):
                erros.append("Muitos nomes novos em pouco tempo. Aguarde um pouco e tente novamente.")
                status = 429
            else:
                operador, criado = obter_ou_criar_por_nome(nome, chave)
                if criado:
                    limitador_nomes_novos.registrar_falha(origem)  # conta como "uso" do limite

                if not operador["ativo"]:
                    erros.append("Este nome foi bloqueado por um supervisor. Fale com a coordenação.")
                    status = 403
                else:
                    iniciar_sessao(operador)
                    return redirect(url_for("index"))
        else:
            status = 400

    return render_template("identificar.html", erros=erros, nome=nome), status


@bp.route("/sair", methods=["POST"])
def sair():
    """Trocar de nome (útil em computador compartilhado)."""
    session.clear()
    return redirect(url_for("auth.identificar"))
