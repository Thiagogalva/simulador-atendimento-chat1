import hmac

from flask import Blueprint, redirect, render_template, request, session, url_for

import config
from repositories.operador_repository import (
    atualizar_senha,
    buscar_operador_por_id,
    buscar_operador_por_usuario,
    criar_operador,
    salvar_recuperacao_hash,
)
from services.auth_service import (
    fingerprint_senha,
    gerar_codigo_recuperacao,
    gerar_hash,
    limitador_login,
    limitador_recuperacao,
    normalizar_codigo,
    normalizar_usuario,
    validar_cadastro,
    validar_nova_senha,
    verificar_senha,
)

bp = Blueprint("auth", __name__)


def iniciar_sessao(operador: dict):
    """Nova sessão limpa (evita fixação de sessão) já vinculada ao operador."""
    session.clear()
    session["operador_id"] = operador["id"]
    session["operador_nome"] = operador["nome"]
    session["usuario_id"] = f"operador-{operador['id']}"
    session["sv"] = fingerprint_senha(operador["senha_hash"])  # troca de senha derruba as outras sessões


def exibir_codigo_uma_vez(codigo: str):
    """Guarda o código só até a próxima página (que o mostra e o descarta)."""
    session["codigo_novo"] = codigo
    return redirect(url_for("auth.codigo_recuperacao"))


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
                if not operador["ativo"]:
                    return render_template(
                        "login.html", usuario=usuario,
                        erro="Conta desativada. Fale com um supervisor."), 403
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
            codigo = gerar_codigo_recuperacao()
            senha_hash = gerar_hash(senha)
            operador_id = criar_operador(
                usuario, nome, senha_hash, gerar_hash(normalizar_codigo(codigo))
            )
            if operador_id is None:
                erros.append("Este usuário já está em uso. Escolha outro.")
            else:
                iniciar_sessao({"id": operador_id, "nome": nome, "senha_hash": senha_hash})
                return exibir_codigo_uma_vez(codigo)

        status = 400

    return render_template(
        "registro.html",
        erros=erros,
        valores=valores,
        exige_convite=bool(config.CODIGO_CONVITE),
    ), status


@bp.route("/conta/codigo")
def codigo_recuperacao():
    codigo = session.pop("codigo_novo", None)
    if not codigo:
        return redirect(url_for("index"))
    resposta = render_template("codigo_recuperacao.html", codigo=codigo)
    return resposta, 200, {"Cache-Control": "no-store"}


@bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """Redefine a senha com o código de recuperação entregue no cadastro (não usa e-mail)."""
    if session.get("operador_id"):
        return redirect(url_for("index"))

    erros = []
    usuario = ""
    status = 200

    if request.method == "POST":
        usuario = normalizar_usuario(request.form.get("usuario"))
        codigo = normalizar_codigo(request.form.get("codigo"))
        nova = request.form.get("senha") or ""
        confirmacao = request.form.get("confirmacao") or ""
        chave = f"rec|{request.remote_addr}|{usuario}"

        if limitador_recuperacao.bloqueado(chave):
            erros.append("Muitas tentativas. Aguarde alguns minutos e tente novamente.")
            status = 429
        else:
            operador = buscar_operador_por_usuario(usuario)
            hash_codigo = operador["recuperacao_hash"] if operador else None
            codigo_ok = verificar_senha(hash_codigo, codigo) if codigo else False
            erros_senha = validar_nova_senha(nova, confirmacao)

            if not (operador and operador["ativo"] and codigo_ok):
                limitador_recuperacao.registrar_falha(chave)
                erros.append("Usuário ou código de recuperação inválidos.")
                status = 400
            elif erros_senha:
                erros.extend(erros_senha)
                status = 400
            else:
                limitador_recuperacao.limpar(chave)
                novo_hash = gerar_hash(nova)
                atualizar_senha(operador["id"], novo_hash, temporaria=False)
                novo_codigo = gerar_codigo_recuperacao()  # o código usado deixa de valer
                salvar_recuperacao_hash(operador["id"], gerar_hash(normalizar_codigo(novo_codigo)))
                iniciar_sessao(buscar_operador_por_id(operador["id"]))
                return exibir_codigo_uma_vez(novo_codigo)

    return render_template("recuperar.html", erros=erros, usuario=usuario), status


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("auth.login"))
