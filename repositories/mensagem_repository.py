from datetime import datetime
from database.connection import get_connection

def buscar_mensagens(cursor, atendimento_db_id: int):
    cursor.execute("""
        SELECT tipo, texto
        FROM mensagens
        WHERE atendimento_id = ?
        ORDER BY id
    """, (atendimento_db_id,))
    return [{"tipo": row["tipo"], "texto": row["texto"]} for row in cursor.fetchall()]

def adicionar_mensagem(atendimento_db_id: int, tipo: str, texto: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO mensagens (atendimento_id, tipo, texto, criado_em)
        VALUES (?, ?, ?, ?)
    """, (atendimento_db_id, tipo, texto, datetime.now().isoformat()))

    conn.commit()
    conn.close()