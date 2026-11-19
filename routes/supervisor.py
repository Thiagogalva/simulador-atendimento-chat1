import csv
import io
from functools import wraps
from statistics import mean

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, session, url_for, jsonify

from services.calibrador_service import extrair_ancoras, simular_reacao_especialista

from repositories.cenario_repository import (
    atualizar_cenario,
    buscar_cenario,
    contar_ativos,
    criar_cenario,
    definir_ativo_cenario,
    listar_cenarios,
    proxima_ordem,
)
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
from services.cenario_service import MAX_PASSOS, validar_cenario
from services.conduta_service import REGRAS_PADRAO

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


# ---------------------------------------------------------------- cenários

LINHAS_EM_BRANCO = 2


def _passos_do_formulario():
    clientes = request.form.getlist("cliente")
    respostas = request.form.getlist("resposta")
    return [{"cliente": c, "resposta_esperada": r} for c, r in zip(clientes, respostas)]


@bp.route("/cenarios")
@requer_supervisor
def cenarios():
    return render_template("cenarios.html", cenarios=listar_cenarios(), ativos=contar_ativos())


@bp.route("/cenarios/novo", methods=["GET", "POST"])
@requer_supervisor
def cenario_novo():
    return _formulario_cenario(None)


@bp.route("/cenarios/<int:cenario_id>", methods=["GET", "POST"])
@requer_supervisor
def cenario_editar(cenario_id):
    cenario = buscar_cenario(cenario_id)
    if cenario is None:
        abort(404)
    return _formulario_cenario(cenario)


def _formulario_cenario(cenario):
    erros, status = [], 200
    valores = {
        "titulo": cenario["titulo"] if cenario else "",
        "ordem": cenario["ordem"] if cenario else proxima_ordem(),
        "palavras": ", ".join(cenario["palavras_criticas"]) if cenario else "",
        "passos": list(cenario["fluxo"]) if cenario else [],
        "espera_ativa": cenario["regras"]["espera"]["ativa"] if cenario else REGRAS_PADRAO["espera"]["ativa"],
        "espera_max": cenario["regras"]["espera"]["max"] if cenario else REGRAS_PADRAO["espera"]["max"],
    }

    if request.method == "POST":
        erros, avisos, dados = validar_cenario(
            request.form.get("titulo"), request.form.get("ordem"), request.form.get("palavras"),
            request.form.getlist("cliente"), request.form.getlist("resposta"),
            ordem_padrao=valores["ordem"],
            espera_ativa=request.form.get("espera_ativa") == "1",
            espera_max=request.form.get("espera_max", ""),
        )
        valores = {
            "titulo": request.form.get("titulo", ""),
            "ordem": request.form.get("ordem", ""),
            "palavras": request.form.get("palavras", ""),
            "passos": _passos_do_formulario(),
            "espera_ativa": request.form.get("espera_ativa") == "1",
            "espera_max": request.form.get("espera_max", ""),
        }

        if not erros:
            if cenario is None:
                cenario_id = criar_cenario(dados, criado_por=g.operador["id"])
                registrar_auditoria(g.operador["id"], f"criou o cenário \"{dados['titulo']}\"")
            else:
                cenario_id = cenario["id"]
                atualizar_cenario(cenario_id, dados)
                registrar_auditoria(g.operador["id"], f"editou o cenário \"{dados['titulo']}\"")
            flash("Cenário salvo. Simulações já em andamento não são afetadas.", "ok")
            for aviso in avisos:
                flash(aviso, "aviso")
            return redirect(url_for("supervisor.cenarios"))
        status = 400

    while len(valores["passos"]) < LINHAS_EM_BRANCO:
        valores["passos"].append({"cliente": "", "resposta_esperada": ""})

    return render_template("cenario_form.html", cenario=cenario, valores=valores, erros=erros,
                           max_passos=MAX_PASSOS), status


@bp.route("/cenarios/<int:cenario_id>/ativo", methods=["POST"])
@requer_supervisor
def cenario_ativo(cenario_id):
    cenario = buscar_cenario(cenario_id)
    if cenario is None:
        abort(404)

    ativar = request.form.get("ativo") == "1"
    if not ativar and cenario["ativo"] and contar_ativos() <= 1:
        flash("Mantenha pelo menos um cenário ativo, senão ninguém consegue iniciar simulações.", "erro")
        return redirect(url_for("supervisor.cenarios"))

    definir_ativo_cenario(cenario_id, ativar)
    registrar_auditoria(g.operador["id"], f"{'ativou' if ativar else 'arquivou'} o cenário \"{cenario['titulo']}\"")
    flash(f"Cenário {'ativado' if ativar else 'arquivado'}.", "ok")
    return redirect(url_for("supervisor.cenarios"))


# ---------------------------------------------------------------- calibrador de processo (modo especialista)

@bp.route("/calibrador")
@requer_supervisor
def calibrador():
    cenarios = listar_cenarios()
    if not cenarios:
        flash("Nenhum cenário cadastrado para calibração.", "aviso")
        return redirect(url_for("supervisor.cenarios"))
    cenario_id = request.args.get("cenario_id")
    if not cenario_id:
        cenario_id = cenarios[0]["id"]
    return redirect(url_for("supervisor.calibrador_cenario", cenario_id=cenario_id))


@bp.route("/calibrador/<int:cenario_id>")
@requer_supervisor
def calibrador_cenario(cenario_id):
    cenario = buscar_cenario(cenario_id)
    if cenario is None:
        abort(404)
    cenarios = listar_cenarios()
    passo_idx = int(request.args.get("passo", 0))
    if passo_idx < 0 or passo_idx >= len(cenario["fluxo"]):
        passo_idx = 0
    passo_atual = cenario["fluxo"][passo_idx] if cenario["fluxo"] else None
    return render_template(
        "calibrador.html",
        cenario=cenario,
        cenarios=cenarios,
        passo_idx=passo_idx,
        passo_atual=passo_atual,
        total_passos=len(cenario["fluxo"])
    )


@bp.route("/calibrador/extrair-ancoras", methods=["POST"])
@requer_supervisor
def calibrador_extrair_ancoras():
    dados = request.get_json(silent=True) or {}
    respostas = dados.get("respostas", [])
    ancoras = extrair_ancoras(respostas)
    return jsonify({"ancoras": ancoras})


@bp.route("/calibrador/simular-resposta", methods=["POST"])
@requer_supervisor
def calibrador_simular_resposta():
    dados = request.get_json(silent=True) or {}
    resposta_teste = dados.get("resposta_teste", "")
    passo = dados.get("passo", {})
    resultado = simular_reacao_especialista(resposta_teste, passo)
    return jsonify(resultado)


@bp.route("/calibrador/salvar-passo", methods=["POST"])
@requer_supervisor
def calibrador_salvar_passo():
    dados = request.get_json(silent=True) or {}
    cenario_id = dados.get("cenario_id")
    passo_idx = dados.get("passo_idx")
    passo_calibrado = dados.get("passo")

    if cenario_id is None or passo_idx is None or not passo_calibrado:
        return jsonify({"erro": "Dados inválidos."}), 400

    cenario = buscar_cenario(cenario_id)
    if cenario is None:
        return jsonify({"erro": "Cenário não encontrado."}), 404

    if passo_idx < 0 or passo_idx >= len(cenario["fluxo"]):
        return jsonify({"erro": "Índice de passo inválido."}), 400

    cenario["fluxo"][passo_idx] = passo_calibrado
    atualizar_cenario(cenario_id, cenario)
    registrar_auditoria(g.operador["id"], f"calibrou o passo {passo_idx + 1} do cenário \"{cenario['titulo']}\"")
    return jsonify({"sucesso": True, "mensagem": "Passo calibrado e salvo com sucesso."})

