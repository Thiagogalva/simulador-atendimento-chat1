from datetime import datetime
from database.connection import get_connection

def garantir_usuario_no_banco(usuario_uuid: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM usuarios WHERE usuario_uuid = ?",
        (usuario_uuid,)
    )
    usuario = cursor.fetchone()

    if not usuario:
        cursor.execute(
            "INSERT INTO usuarios (usuario_uuid, criado_em) VALUES (?, ?)",
            (usuario_uuid, datetime.now().isoformat())
        )
        conn.commit()

    conn.close()