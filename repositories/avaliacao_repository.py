import json
from datetime import datetime
from database.connection import get_connection

def buscar_avaliacoes(cursor, atendimento_db_id: int):
    cursor.execute("""
        SELECT erros, coerencia, empatia, tempo, tempo_segundos, avisos_json
        FROM avaliacoes
        WHERE atendimento_id = ?
        ORDER BY id
    """, (atendimento_db_id,))
    avaliacoes = []
    for row in cursor.fetchall():
        avaliacoes.append({
            "erros": row["erros"],
            "coerencia": row["coerencia"],
            "empatia": row["empatia"],
            "tempo": row["tempo"],
            "tempo_segundos": row["tempo_segundos"],
            "avisos": json.loads(row["avisos_json"] or "[]")
        })
    return avaliacoes

def adicionar_avaliacao(atendimento_db_id: int, erros: int, coerencia: int, empatia: int,
                        tempo_nota: int, tempo_segundos: float, avisos: list,
                        etapa: int = None, resposta_texto: str = None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO avaliacoes (
            atendimento_id, erros, coerencia, empatia, tempo, tempo_segundos, avisos_json, criado_em,
            etapa, resposta_texto
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        atendimento_db_id,
        erros,
        coerencia,
        empatia,
        tempo_nota,
        tempo_segundos,
        json.dumps(avisos, ensure_ascii=False),
        datetime.now().isoformat(),
        etapa,
        resposta_texto
    ))

    conn.commit()
    conn.close()


def buscar_ultima_avaliacao(atendimento_db_id: int):
    """Última resposta avaliada do atendimento (com o feedback já gerado, se houver)."""
    conn = get_connection()
    try:
        row = conn.cursor().execute("""
            SELECT id, etapa, resposta_texto, erros, coerencia, empatia, tempo, avisos_json,
                   feedback_texto, feedback_origem
            FROM avaliacoes WHERE atendimento_id = ? ORDER BY id DESC LIMIT 1
        """, (atendimento_db_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row["id"], "etapa": row["etapa"], "resposta_texto": row["resposta_texto"],
        "erros": row["erros"], "coerencia": row["coerencia"], "empatia": row["empatia"], "tempo": row["tempo"],
        "avisos": json.loads(row["avisos_json"] or "[]"),
        "feedback_texto": row["feedback_texto"], "feedback_origem": row["feedback_origem"],
    }


def salvar_feedback_avaliacao(avaliacao_id: int, texto: str, origem: str):
    conn = get_connection()
    try:
        conn.cursor().execute(
            "UPDATE avaliacoes SET feedback_texto = ?, feedback_origem = ? WHERE id = ?",
            (texto, origem, avaliacao_id),
        )
        conn.commit()
    finally:
        conn.close()
