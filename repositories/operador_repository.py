from datetime import datetime, timezone

from database.connection import get_connection, violacao_unicidade


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def criar_operador(usuario: str, nome: str, senha_hash: str):
    """Cria o operador. Retorna o id, ou None se o usuário já existe."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        operador_id = cursor.inserir(
            "INSERT INTO operadores (usuario, nome, senha_hash, criado_em) VALUES (?, ?, ?, ?)",
            (usuario, nome, senha_hash, _agora_iso())
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


def _linha_para_dict(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "usuario": row["usuario"],
        "nome": row["nome"],
        "senha_hash": row["senha_hash"],
        "criado_em": row["criado_em"],
    }


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
