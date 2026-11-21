import itertools
import random
import string
import time
import uuid

from data.base_atendimentos import BASE_ATENDIMENTOS
from database.connection import get_connection

_contador = itertools.count(1)


def novo_usuario() -> str:
    return f"op{next(_contador)}_{uuid.uuid4().hex[:6]}"


def _letras(quantidade=6) -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(quantidade))


def cliente_logado(nome="Operador Teste", usuario=None):
    """
    Cliente de teste já identificado pelo nome. Cada chamada acrescenta letras aleatórias ao nome
    para que seja SEMPRE um operador novo (o mesmo nome reaproveitaria o mesmo operador).
    Retorna (client, operador_id, chave_de_identidade).
    """
    import app as aplicacao
    from repositories.operador_repository import buscar_operador_por_usuario
    from services.auth_service import chave_do_nome

    nome_unico = f"{nome} {_letras()}"
    client = aplicacao.app.test_client()
    resposta = client.post("/identificar", data={"nome": nome_unico})
    assert resposta.status_code == 302, resposta.get_data(as_text=True)
    chave = chave_do_nome(nome_unico)
    return client, buscar_operador_por_usuario(chave)["id"], chave


def tornar_supervisor(client):
    """Libera a área do supervisor nesta sessão (o fluxo do código é testado à parte)."""
    with client.session_transaction() as s:
        s["supervisor_ate"] = time.time() + 3600
    return client


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
