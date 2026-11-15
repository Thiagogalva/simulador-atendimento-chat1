from database.connection import get_connection, usando_postgres

# Colunas adicionadas depois da primeira versão (aplicadas também a bancos já existentes).
COLUNAS_NOVAS = {
    "mensagens": {
        "humor": "TEXT",
    },
    "atendimentos": {
        "irritacao": "INTEGER NOT NULL DEFAULT 0",
        "tentativas_etapa": "INTEGER NOT NULL DEFAULT 0",
        "encerrado_por_cliente": "INTEGER NOT NULL DEFAULT 0",
        "modo": "TEXT NOT NULL DEFAULT 'avaliacao'",
        "dica_nivel": "INTEGER NOT NULL DEFAULT 0",
        "dicas_usadas": "INTEGER NOT NULL DEFAULT 0",
        "cenario_id": "INTEGER",
        "palavras_criticas_json": "TEXT",
    },
    "operadores": {
        "papel": "TEXT NOT NULL DEFAULT 'operador'",
        "ativo": "INTEGER NOT NULL DEFAULT 1",
        "senha_temporaria": "INTEGER NOT NULL DEFAULT 0",
        "recuperacao_hash": "TEXT",
    },
    "simulacoes": {
        "modo": "TEXT NOT NULL DEFAULT 'avaliacao'",
        "feedback_texto": "TEXT",
    },
    "avaliacoes": {
        "feedback_texto": "TEXT",
    },
}


def colunas_existentes(cursor, tabela: str) -> set:
    """Nomes das colunas da tabela (aceita cursor do wrapper ou do sqlite3 puro)."""
    if getattr(cursor, "postgres", False):
        linhas = cursor.execute(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (tabela,)
        ).fetchall()
    else:
        linhas = cursor.execute(f"PRAGMA table_info({tabela})").fetchall()
    return {linha["name"] for linha in linhas}


def garantir_colunas(cursor):
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = colunas_existentes(cursor, tabela)
        for nome, definicao in colunas.items():
            if nome not in existentes:
                cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")


def _tabelas(pk: str) -> list:
    """DDL das tabelas; `pk` é a definição de chave primária auto-incremental do dialeto."""
    return [
        f"""
        CREATE TABLE IF NOT EXISTS usuarios (
            id {pk},
            usuario_uuid TEXT UNIQUE NOT NULL,
            criado_em TEXT NOT NULL
        )""",
        f"""
        CREATE TABLE IF NOT EXISTS atendimentos (
            id {pk},
            usuario_uuid TEXT NOT NULL,
            id_publico INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            fluxo_json TEXT NOT NULL,
            etapa_atual INTEGER NOT NULL DEFAULT 0,
            total_erros INTEGER NOT NULL DEFAULT 0,
            total_respostas INTEGER NOT NULL DEFAULT 0,
            media_coerencia DOUBLE PRECISION NOT NULL DEFAULT 0,
            media_empatia DOUBLE PRECISION NOT NULL DEFAULT 0,
            media_tempo DOUBLE PRECISION NOT NULL DEFAULT 0,
            resposta_esperada TEXT NOT NULL,
            finalizado INTEGER NOT NULL DEFAULT 0,
            bloqueado_tempo INTEGER NOT NULL DEFAULT 0,
            ultimo_tempo_backend DOUBLE PRECISION,
            UNIQUE(usuario_uuid, id_publico)
        )""",
        f"""
        CREATE TABLE IF NOT EXISTS mensagens (
            id {pk},
            atendimento_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (atendimento_id) REFERENCES atendimentos (id)
        )""",
        f"""
        CREATE TABLE IF NOT EXISTS avaliacoes (
            id {pk},
            atendimento_id INTEGER NOT NULL,
            erros INTEGER NOT NULL DEFAULT 0,
            coerencia INTEGER NOT NULL DEFAULT 0,
            empatia INTEGER NOT NULL DEFAULT 0,
            tempo INTEGER NOT NULL DEFAULT 0,
            tempo_segundos DOUBLE PRECISION NOT NULL DEFAULT 0,
            avisos_json TEXT NOT NULL DEFAULT '[]',
            criado_em TEXT NOT NULL,
            FOREIGN KEY (atendimento_id) REFERENCES atendimentos (id)
        )""",
        f"""
        CREATE TABLE IF NOT EXISTS operadores (
            id {pk},
            usuario TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )""",
        f"""
        CREATE TABLE IF NOT EXISTS simulacoes (
            id {pk},
            operador_id INTEGER NOT NULL,
            iniciada_em DOUBLE PRECISION NOT NULL,
            finalizada_em TEXT NOT NULL,
            nota_geral DOUBLE PRECISION NOT NULL,
            nivel TEXT NOT NULL,
            media_coerencia DOUBLE PRECISION NOT NULL DEFAULT 0,
            media_empatia DOUBLE PRECISION NOT NULL DEFAULT 0,
            media_tempo DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_erros INTEGER NOT NULL DEFAULT 0,
            total_atendimentos INTEGER NOT NULL DEFAULT 0,
            detalhes_json TEXT NOT NULL DEFAULT '[]',
            UNIQUE(operador_id, iniciada_em),
            FOREIGN KEY (operador_id) REFERENCES operadores (id)
        )""",
        f"""
        CREATE TABLE IF NOT EXISTS cenarios (
            id {pk},
            titulo TEXT NOT NULL,
            fluxo_json TEXT NOT NULL,
            palavras_criticas_json TEXT NOT NULL DEFAULT '[]',
            ativo INTEGER NOT NULL DEFAULT 1,
            ordem INTEGER NOT NULL DEFAULT 0,
            criado_por INTEGER,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )""",
        f"""
        CREATE TABLE IF NOT EXISTS auditoria (
            id {pk},
            ator_id INTEGER,
            acao TEXT NOT NULL,
            alvo_id INTEGER,
            detalhes TEXT,
            criado_em TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_simulacoes_operador ON simulacoes (operador_id, finalizada_em)",
        "CREATE INDEX IF NOT EXISTS idx_simulacoes_data ON simulacoes (finalizada_em)",
    ]


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    postgres = usando_postgres()

    if postgres:
        # Evita corrida entre instâncias que sobem ao mesmo tempo (liberado no commit).
        cursor.execute("SELECT pg_advisory_xact_lock(724001)")

    pk = "SERIAL PRIMARY KEY" if postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    for ddl in _tabelas(pk):
        cursor.execute(ddl)

    garantir_colunas(cursor)
    semear_cenarios(cursor)

    conn.commit()
    conn.close()


def semear_cenarios(cursor):
    """Na primeira execução, carrega os cenários iniciais (data/base_atendimentos.py) para o banco."""
    import json
    from datetime import datetime, timezone

    from data.base_atendimentos import BASE_ATENDIMENTOS
    from services.texto_service import PALAVRAS_CRITICAS

    total = cursor.execute("SELECT COUNT(*) AS n FROM cenarios").fetchone()["n"]
    if total:
        return

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for posicao, item in enumerate(BASE_ATENDIMENTOS):
        cursor.execute(
            "INSERT INTO cenarios (titulo, fluxo_json, palavras_criticas_json, ativo, ordem, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, 1, ?, ?, ?)",
            (
                item["titulo"],
                json.dumps(item["fluxo"], ensure_ascii=False),
                json.dumps(PALAVRAS_CRITICAS.get(item["titulo"].lower(), []), ensure_ascii=False),
                (posicao + 1) * 10,
                agora,
                agora,
            ),
        )
