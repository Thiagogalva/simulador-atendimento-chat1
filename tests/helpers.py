import itertools
import time
import uuid

from data.base_atendimentos import BASE_ATENDIMENTOS
from database.connection import get_connection

SENHA = "senhaforte1"
_contador = itertools.count(1)


def novo_usuario() -> str:
    return f"op{next(_contador)}_{uuid.uuid4().hex[:6]}"


def cliente_logado(nome="Operador Teste", usuario=None):
    """Cliente de teste já cadastrado e autenticado. Retorna (client, operador_id, usuario)."""
    import app as aplicacao
    from repositories.operador_repository import buscar_operador_por_usuario

    usuario = usuario or novo_usuario()
    client = aplicacao.app.test_client()
    resposta = client.post("/registro", data={
        "usuario": usuario, "nome": nome, "senha": SENHA, "confirmacao": SENHA,
    })
    assert resposta.status_code == 302, resposta.get_data(as_text=True)
    return client, buscar_operador_por_usuario(usuario)["id"], usuario


def token_csrf(client) -> str:
    with client.session_transaction() as s:
        s.setdefault("csrf", "token-de-teste")
        return s["csrf"]


def post_form(client, url, data=None, **kwargs):
    """POST de formulário HTML já com o token CSRF da sessão."""
    dados = dict(data or {})
    dados["csrf_token"] = token_csrf(client)
    return client.post(url, data=dados, **kwargs)


def iniciar(client, modo="avaliacao"):
    """Inicia uma nova simulação (substitui o antigo GET / que reiniciava)."""
    r = post_form(client, "/iniciar", {"modo": modo})
    assert r.status_code == 303, r.get_data(as_text=True)
    return r


def preparar_turno(operador_id: int, id_publico: int):
    """Reinicia o relógio do turno do atendimento (evita expirar durante os testes)."""
    conn = get_connection()
    conn.execute(
        "UPDATE atendimentos SET ultimo_tempo_backend = ? WHERE usuario_uuid = ? AND id_publico = ?",
        (time.time(), f"operador-{operador_id}", id_publico),
    )
    conn.commit()
    conn.close()


def liberar_todos(client):
    """Faz todos os atendimentos já estarem liberados (simulação 'iniciada há 1000 s')."""
    with client.session_transaction() as s:
        s["simulacao_iniciada_em"] = time.time() - 1000


def completar_simulacao(client, operador_id: int, respostas=None, modo="avaliacao"):
    """
    Responde todos os passos de todos os atendimentos. Por padrão usa as respostas sugeridas;
    `respostas` pode ser uma função (atendimento, passo) -> texto.
    """
    iniciar(client, modo)
    liberar_todos(client)
    ultimo = None
    for at in BASE_ATENDIMENTOS:
        preparar_turno(operador_id, at["id"])
        for passo in at["fluxo"]:
            texto = respostas(at, passo) if respostas else passo["resposta_esperada"]
            r = client.post("/responder", json={"id": at["id"], "resposta": texto})
            assert r.status_code == 200, r.get_json()
            ultimo = r.get_json()
            if ultimo["finalizado"]:
                break
    return ultimo


def apagar_cenario(cenario_id: int):
    """Remove um cenário criado por um teste (para não afetar os demais)."""
    conn = get_connection()
    conn.execute("DELETE FROM cenarios WHERE id = ?", (cenario_id,))
    conn.commit()
    conn.close()
