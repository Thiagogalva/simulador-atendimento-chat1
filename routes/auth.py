import hmac

from flask import Blueprint, redirect, render_template, request, session, url_for

import config
from repositories.operador_repository import buscar_operador_por_usuario, criar_operador
from services.auth_service import (
    gerar_hash,
    limitador_login,
    normalizar_usuario,
    validar_cadastro,
    verificar_senha,
)

bp = Blueprint("auth", __name__)


def iniciar_sessao(operador: dict):
    """Nova sessão limpa (evita fixação de sessão) já vinculada ao operador."""
    session.clear()
    session["operador_id"] = operador["id"]
    session["operador_nome"] = operador["nome"]
    session["usuario_id"] = f"operador-{operador['id']}"


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("operador_id"):
        return redirect(url_for("index"))

    erro = None
    usuario = ""
    status = 200

    if request.method == "POST":
        usuario = normalizar_usuario(request.form.get("usuario"))
        senha = request.form.get("senha") or ""
        chave = f"{request.remote_addr}|{usuario}"

        if limitador_login.bloqueado(chave):
            erro = "Muitas tentativas de login. Aguarde alguns minutos e tente novamente."
            status = 429
        else:
            operador = buscar_operador_por_usuario(usuario)
            senha_ok = verificar_senha(operador["senha_hash"] if operador else None, senha)

            if operador and senha_ok:
                limitador_login.limpar(chave)
                iniciar_sessao(operador)
                return redirect(url_for("index"))

            limitador_login.registrar_falha(chave)
            erro = "Usuário ou senha inválidos."
            status = 401

    return render_template("login.html", erro=erro, usuario=usuario), status


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if session.get("operador_id"):
        return redirect(url_for("index"))

    erros = []
    valores = {"usuario": "", "nome": ""}
    status = 200

    if request.method == "POST":
        usuario = normalizar_usuario(request.form.get("usuario"))
        nome = (request.form.get("nome") or "").strip()
        senha = request.form.get("senha") or ""
        confirmacao = request.form.get("confirmacao") or ""
        convite = (request.form.get("convite") or "").strip()
        valores = {"usuario": usuario, "nome": nome}

        erros = validar_cadastro(usuario, nome, senha, confirmacao)

        if config.CODIGO_CONVITE and not hmac.compare_digest(convite, config.CODIGO_CONVITE):
            erros.append("Código de convite inválido.")

        if not erros:
            operador_id = criar_operador(usuario, nome, gerar_hash(senha))
            if operador_id is None:
                erros.append("Este usuário já está em uso. Escolha outro.")
            else:
                iniciar_sessao({"id": operador_id, "nome": nome})
                return redirect(url_for("index"))

        status = 400

    return render_template(
        "registro.html",
        erros=erros,
        valores=valores,
        exige_convite=bool(config.CODIGO_CONVITE),
    ), status


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("auth.login"))
