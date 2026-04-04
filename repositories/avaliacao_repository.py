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
                        tempo_nota: int, tempo_segundos: float, avisos: list):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO avaliacoes (
            atendimento_id, erros, coerencia, empatia, tempo, tempo_segundos, avisos_json, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        atendimento_db_id,
        erros,
        coerencia,
        empatia,
        tempo_nota,
        tempo_segundos,
        json.dumps(avisos, ensure_ascii=False),
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()