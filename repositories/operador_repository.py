from datetime import datetime, timezone

import config
from database.connection import get_connection, violacao_unicidade

PAPEIS = ("operador", "supervisor")


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _linha_para_dict(row):
    if row is None:
        return None
    papel = row["papel"]
    return {
        "id": row["id"],
        "usuario": row["usuario"],
        "nome": row["nome"],
        "senha_hash": row["senha_hash"],
        "criado_em": row["criado_em"],
        "papel": papel,
        "ativo": bool(row["ativo"]),
        "senha_temporaria": bool(row["senha_temporaria"]),
        "recuperacao_hash": row["recuperacao_hash"],
        # supervisores definidos por variável de ambiente nunca perdem o acesso
        "supervisor_fixo": row["usuario"] in config.SUPERVISORES,
        "e_supervisor": papel == "supervisor" or row["usuario"] in config.SUPERVISORES,
    }


def criar_operador(usuario: str, nome: str, senha_hash: str, recuperacao_hash: str = None):
    """Cria o operador. Retorna o id, ou None se o usuário já existe."""
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


def _atualizar(sql: str, params: tuple):
    conn = get_connection()
    try:
        conn.cursor().execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def atualizar_senha(operador_id: int, senha_hash: str, temporaria: bool = False):
    _atualizar("UPDATE operadores SET senha_hash = ?, senha_temporaria = ? WHERE id = ?",
               (senha_hash, 1 if temporaria else 0, operador_id))


def salvar_recuperacao_hash(operador_id: int, recuperacao_hash):
    _atualizar("UPDATE operadores SET recuperacao_hash = ? WHERE id = ?", (recuperacao_hash, operador_id))


def definir_ativo(operador_id: int, ativo: bool):
    _atualizar("UPDATE operadores SET ativo = ? WHERE id = ?", (1 if ativo else 0, operador_id))


def definir_papel(operador_id: int, papel: str):
    if papel not in PAPEIS:
        raise ValueError("papel inválido")
    _atualizar("UPDATE operadores SET papel = ? WHERE id = ?", (papel, operador_id))


def listar_operadores_com_estatisticas() -> list:
    conn = get_connection()
    try:
        linhas = conn.cursor().execute("""
            SELECT o.id, o.usuario, o.nome, o.papel, o.ativo, o.criado_em,
                   COUNT(CASE WHEN s.modo = 'avaliacao' THEN 1 END) AS avaliacoes,
                   AVG(CASE WHEN s.modo = 'avaliacao' THEN s.nota_geral END) AS media,
                   COUNT(CASE WHEN s.modo = 'treino' THEN 1 END) AS treinos,
                   MAX(s.finalizada_em) AS ultima
            FROM operadores o
            LEFT JOIN simulacoes s ON s.operador_id = o.id
            GROUP BY o.id, o.usuario, o.nome, o.papel, o.ativo, o.criado_em
            ORDER BY o.nome ASC, o.id ASC
        """).fetchall()
    finally:
        conn.close()

    return [{
        "id": r["id"],
        "usuario": r["usuario"],
        "nome": r["nome"],
        "papel": r["papel"],
        "ativo": bool(r["ativo"]),
        "criado_em": r["criado_em"],
        "avaliacoes": int(r["avaliacoes"]),
        "media": float(r["media"]) if r["media"] is not None else None,
        "treinos": int(r["treinos"]),
        "ultima": r["ultima"],
        "supervisor_fixo": r["usuario"] in config.SUPERVISORES,
        "e_supervisor": r["papel"] == "supervisor" or r["usuario"] in config.SUPERVISORES,
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
