from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from repositories.operador_repository import (
    atualizar_senha,
    buscar_operador_por_id,
    salvar_recuperacao_hash,
)
from routes.auth import exibir_codigo_uma_vez
from services.auth_service import (
    fingerprint_senha,
    gerar_codigo_recuperacao,
    gerar_hash,
    limitador_login,
    normalizar_codigo,
    validar_nova_senha,
    verificar_senha,
)

bp = Blueprint("conta", __name__)


def _senha_atual_confere() -> bool:
    chave = f"senha|{request.remote_addr}|{g.operador['id']}"
    if limitador_login.bloqueado(chave):
        return False
    if verificar_senha(g.operador["senha_hash"], request.form.get("senha_atual") or ""):
        limitador_login.limpar(chave)
        return True
    limitador_login.registrar_falha(chave)
    return False


@bp.route("/senha", methods=["GET", "POST"])
def senha():
    erros = []
    obrigatoria = g.operador["senha_temporaria"]
    status = 200

    if request.method == "POST":
        nova = request.form.get("senha") or ""
        confirmacao = request.form.get("confirmacao") or ""

        if not _senha_atual_confere():
            erros.append("Senha atual incorreta (ou muitas tentativas; aguarde alguns minutos).")
        erros.extend(validar_nova_senha(nova, confirmacao))
        if not erros and verificar_senha(g.operador["senha_hash"], nova):
            erros.append("A nova senha deve ser diferente da atual.")

        if not erros:
            novo_hash = gerar_hash(nova)
            atualizar_senha(g.operador["id"], novo_hash, temporaria=False)
            session["sv"] = fingerprint_senha(novo_hash)  # esta sessão continua; as outras caem
            flash("Senha alterada com sucesso.", "ok")
            return redirect(url_for("index"))
        status = 400

    return render_template("senha.html", erros=erros, obrigatoria=obrigatoria), status


@bp.route("/conta/novo-codigo", methods=["POST"])
def novo_codigo():
    """Gera um novo código de recuperação (invalida o anterior). Exige a senha atual."""
    if not _senha_atual_confere():
        flash("Senha atual incorreta. O código de recuperação não foi alterado.", "erro")
        return redirect(url_for("conta.senha"))

    codigo = gerar_codigo_recuperacao()
    salvar_recuperacao_hash(g.operador["id"], gerar_hash(normalizar_codigo(codigo)))
    return exibir_codigo_uma_vez(codigo)
