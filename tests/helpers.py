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


def completar_simulacao(client, operador_id: int, respostas=None):
    """
    Responde todos os passos de todos os atendimentos. Por padrão usa as respostas sugeridas;
    `respostas` pode ser uma função (atendimento, passo) -> texto.
    """
    client.get("/")
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
