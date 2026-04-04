from database.connection import get_connection

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_uuid TEXT UNIQUE NOT NULL,
            criado_em TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atendimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_uuid TEXT NOT NULL,
            id_publico INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            fluxo_json TEXT NOT NULL,
            etapa_atual INTEGER NOT NULL DEFAULT 0,
            total_erros INTEGER NOT NULL DEFAULT 0,
            total_respostas INTEGER NOT NULL DEFAULT 0,
            media_coerencia REAL NOT NULL DEFAULT 0,
            media_empatia REAL NOT NULL DEFAULT 0,
            media_tempo REAL NOT NULL DEFAULT 0,
            resposta_esperada TEXT NOT NULL,
            finalizado INTEGER NOT NULL DEFAULT 0,
            bloqueado_tempo INTEGER NOT NULL DEFAULT 0,
            ultimo_tempo_backend REAL,
            UNIQUE(usuario_uuid, id_publico)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atendimento_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (atendimento_id) REFERENCES atendimentos (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS avaliacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atendimento_id INTEGER NOT NULL,
            erros INTEGER NOT NULL DEFAULT 0,
            coerencia INTEGER NOT NULL DEFAULT 0,
            empatia INTEGER NOT NULL DEFAULT 0,
            tempo INTEGER NOT NULL DEFAULT 0,
            tempo_segundos REAL NOT NULL DEFAULT 0,
            avisos_json TEXT NOT NULL DEFAULT '[]',
            criado_em TEXT NOT NULL,
            FOREIGN KEY (atendimento_id) REFERENCES atendimentos (id)
        )
    """)

    conn.commit()
    conn.close()