from datetime import datetime
from database.connection import get_connection

def buscar_mensagens(cursor, atendimento_db_id: int):
    cursor.execute("""
        SELECT tipo, texto, humor
        FROM mensagens
        WHERE atendimento_id = ?
        ORDER BY id
    """, (atendimento_db_id,))
    return [{"tipo": row["tipo"], "texto": row["texto"], "humor": row["humor"]} for row in cursor.fetchall()]

def adicionar_mensagem(atendimento_db_id: int, tipo: str, texto: str, humor: str = None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO mensagens (atendimento_id, tipo, texto, criado_em, humor)
        VALUES (?, ?, ?, ?, ?)
    """, (atendimento_db_id, tipo, texto, datetime.now().isoformat(), humor))

    conn.commit()
    conn.close()