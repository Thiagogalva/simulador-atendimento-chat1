from datetime import datetime, timezone

from database.connection import get_connection, violacao_unicidade

def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _linha_para_dict(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "usuario": row["usuario"],      # chave de identidade (nome normalizado)
        "nome": row["nome"],            # nome de exibição, como foi digitado na primeira vez
        "criado_em": row["criado_em"],
        "ativo": bool(row["ativo"]),
    }


def criar_operador(usuario: str, nome: str, senha_hash: str = "", recuperacao_hash: str = None):
    """Cria o operador. Retorna o id, ou None se a chave já existe. (senha_hash fica vazio: não há senha.)"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        operador_id = cursor.inserir(
            "INSERT INTO operadores (usuario, nome, senha_hash, criado_em, recuperacao_hash) VALUES (?, ?, ?, ?, ?)",
            (usuario, nome, senha_hash, _agora_iso(), recuperacao_hash)
        )
        conn.commit()
        return operador_id
    except Exception as erro:
        conn.rollback()
        if violacao_unicidade(erro):
            return None
        raise
    finally:
        conn.close()


def buscar_operador_por_usuario(usuario: str):
    conn = get_connection()
    try:
        row = conn.cursor().execute("SELECT * FROM operadores WHERE usuario = ?", (usuario,)).fetchone()
        return _linha_para_dict(row)
    finally:
        conn.close()


def buscar_operador_por_id(operador_id):
    conn = get_connection()
    try:
        row = conn.cursor().execute("SELECT * FROM operadores WHERE id = ?", (operador_id,)).fetchone()
        return _linha_para_dict(row)
    finally:
        conn.close()


def obter_ou_criar_por_nome(nome: str, chave: str):
    """
    Devolve (operador, criado). O mesmo nome (mesma chave) sempre volta ao mesmo operador,
    com o mesmo histórico e a mesma posição no ranking.
    """
    existente = buscar_operador_por_usuario(chave)
    if existente:
        return existente, False

    novo_id = criar_operador(chave, nome)
    if novo_id is None:  # outra requisição criou o mesmo nome neste instante
        return buscar_operador_por_usuario(chave), False
    return buscar_operador_por_id(novo_id), True


def _atualizar(sql: str, params: tuple):
    conn = get_connection()
    try:
        conn.cursor().execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def definir_ativo(operador_id: int, ativo: bool):
    conn = get_connection()
    try:
        conn.cursor().execute("UPDATE operadores SET ativo = ? WHERE id = ?", (1 if ativo else 0, operador_id))
        conn.commit()
    finally:
        conn.close()


def listar_operadores_com_estatisticas() -> list:
    conn = get_connection()
    try:
        linhas = conn.cursor().execute("""
            SELECT o.id, o.usuario, o.nome, o.ativo, o.criado_em,
                   COUNT(CASE WHEN s.modo = 'avaliacao' THEN 1 END) AS avaliacoes,
                   AVG(CASE WHEN s.modo = 'avaliacao' THEN s.nota_geral END) AS media,
                   COUNT(CASE WHEN s.modo = 'treino' THEN 1 END) AS treinos,
                   MAX(s.finalizada_em) AS ultima
            FROM operadores o
            LEFT JOIN simulacoes s ON s.operador_id = o.id
            GROUP BY o.id, o.usuario, o.nome, o.ativo, o.criado_em
            ORDER BY o.nome ASC, o.id ASC
        """).fetchall()
    finally:
        conn.close()

    return [{
        "id": r["id"],
        "usuario": r["usuario"],
        "nome": r["nome"],
        "ativo": bool(r["ativo"]),
        "criado_em": r["criado_em"],
        "avaliacoes": int(r["avaliacoes"]),
        "media": float(r["media"]) if r["media"] is not None else None,
        "treinos": int(r["treinos"]),
        "ultima": r["ultima"],
    } for r in linhas]


def registrar_auditoria(ator_id, acao: str, alvo_id=None, detalhes: str = ""):
    _atualizar(
        "INSERT INTO auditoria (ator_id, acao, alvo_id, detalhes, criado_em) VALUES (?, ?, ?, ?, ?)",
        (ator_id, acao, alvo_id, detalhes, _agora_iso())
    )


def listar_auditoria(limite: int = 30) -> list:
    conn = get_connection()
    try:
        linhas = conn.cursor().execute("""
            SELECT a.id, a.acao, a.detalhes, a.criado_em,
                   ator.nome AS ator_nome, alvo.nome AS alvo_nome
            FROM auditoria a
            LEFT JOIN operadores ator ON ator.id = a.ator_id
            LEFT JOIN operadores alvo ON alvo.id = a.alvo_id
            ORDER BY a.id DESC
            LIMIT ?
        """, (int(limite),)).fetchall()
    finally:
        conn.close()
    return [{"acao": r["acao"], "detalhes": r["detalhes"], "criado_em": r["criado_em"],
             "ator": r["ator_nome"], "alvo": r["alvo_nome"]} for r in linhas]
