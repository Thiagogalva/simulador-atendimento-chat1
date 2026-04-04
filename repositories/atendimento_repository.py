import json
import time

from database.connection import get_connection
from data.base_atendimentos import BASE_ATENDIMENTOS
from repositories.mensagem_repository import buscar_mensagens
from repositories.avaliacao_repository import buscar_avaliacoes
from services.tempo_service import calcular_liberado_em, atendimento_expirado

def limpar_simulacao_usuario(usuario_uuid: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM atendimentos WHERE usuario_uuid = ?", (usuario_uuid,))
    atendimentos_ids = [row["id"] for row in cursor.fetchall()]

    for atendimento_id in atendimentos_ids:
        cursor.execute("DELETE FROM mensagens WHERE atendimento_id = ?", (atendimento_id,))
        cursor.execute("DELETE FROM avaliacoes WHERE atendimento_id = ?", (atendimento_id,))

    cursor.execute("DELETE FROM atendimentos WHERE usuario_uuid = ?", (usuario_uuid,))

    conn.commit()
    conn.close()

def inicializar_atendimentos_usuario(usuario_uuid: str):
    conn = get_connection()
    cursor = conn.cursor()

    for item in BASE_ATENDIMENTOS:
        primeiro_passo = item["fluxo"][0]

        cursor.execute("""
            INSERT INTO atendimentos (
                usuario_uuid,
                id_publico,
                titulo,
                fluxo_json,
                etapa_atual,
                total_erros,
                total_respostas,
                media_coerencia,
                media_empatia,
                media_tempo,
                resposta_esperada,
                finalizado,
                bloqueado_tempo,
                ultimo_tempo_backend
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            usuario_uuid,
            item["id"],
            item["titulo"],
            json.dumps(item["fluxo"], ensure_ascii=False),
            0,
            0,
            0,
            0,
            0,
            0,
            primeiro_passo["resposta_esperada"],
            0,
            0,
            None
        ))

        atendimento_db_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO mensagens (atendimento_id, tipo, texto, criado_em)
            VALUES (?, ?, ?, datetime('now'))
        """, (
            atendimento_db_id,
            "cliente",
            primeiro_passo["cliente"]
        ))

    conn.commit()
    conn.close()

def montar_atendimento_dict(row, cursor, simulacao_iniciada_em):
    atendimento = {
        "db_id": row["id"],
        "id": row["id_publico"],
        "titulo": row["titulo"],
        "fluxo": json.loads(row["fluxo_json"]),
        "etapa_atual": row["etapa_atual"],
        "avaliacoes": buscar_avaliacoes(cursor, row["id"]),
        "total_erros": row["total_erros"],
        "total_respostas": row["total_respostas"],
        "media_coerencia": row["media_coerencia"],
        "media_empatia": row["media_empatia"],
        "media_tempo": row["media_tempo"],
        "resposta_esperada": row["resposta_esperada"],
        "finalizado": bool(row["finalizado"]),
        "bloqueado_tempo": bool(row["bloqueado_tempo"]),
        "ultimo_tempo_backend": row["ultimo_tempo_backend"],
        "mensagens": buscar_mensagens(cursor, row["id"]),
        "liberado_em": calcular_liberado_em(simulacao_iniciada_em, row["id_publico"])
    }

    expirado = atendimento_expirado(atendimento, simulacao_iniciada_em)
    atendimento["bloqueado_tempo"] = atendimento["bloqueado_tempo"] or expirado
    return atendimento

def listar_atendimentos_usuario(usuario_uuid: str, simulacao_iniciada_em):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM atendimentos
        WHERE usuario_uuid = ?
        ORDER BY id_publico
    """, (usuario_uuid,))

    atendimentos = [
        montar_atendimento_dict(row, cursor, simulacao_iniciada_em)
        for row in cursor.fetchall()
    ]
    conn.close()
    return atendimentos

def buscar_atendimento_usuario(usuario_uuid: str, id_publico: int, simulacao_iniciada_em):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM atendimentos
        WHERE usuario_uuid = ? AND id_publico = ?
    """, (usuario_uuid, id_publico))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    atendimento = montar_atendimento_dict(row, cursor, simulacao_iniciada_em)
    conn.close()
    return atendimento

def salvar_estado_atendimento(at):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE atendimentos
        SET
            etapa_atual = ?,
            total_erros = ?,
            total_respostas = ?,
            media_coerencia = ?,
            media_empatia = ?,
            media_tempo = ?,
            resposta_esperada = ?,
            finalizado = ?,
            bloqueado_tempo = ?,
            ultimo_tempo_backend = ?
        WHERE id = ?
    """, (
        at["etapa_atual"],
        at["total_erros"],
        at["total_respostas"],
        at["media_coerencia"],
        at["media_empatia"],
        at["media_tempo"],
        at["resposta_esperada"],
        1 if at["finalizado"] else 0,
        1 if at["bloqueado_tempo"] else 0,
        at["ultimo_tempo_backend"],
        at["db_id"]
    ))

    conn.commit()
    conn.close()