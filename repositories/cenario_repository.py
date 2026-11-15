import json
import random
from datetime import datetime, timezone

import config
from database.connection import get_connection


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _para_dict(row) -> dict:
    return {
        "id": row["id"],
        "titulo": row["titulo"],
        "fluxo": json.loads(row["fluxo_json"]),
        "palavras_criticas": json.loads(row["palavras_criticas_json"] or "[]"),
        "ativo": bool(row["ativo"]),
        "ordem": row["ordem"],
        "criado_em": row["criado_em"],
        "atualizado_em": row["atualizado_em"],
    }


def listar_cenarios(apenas_ativos: bool = False) -> list:
    conn = get_connection()
    try:
        filtro = "WHERE ativo = 1" if apenas_ativos else ""
        linhas = conn.cursor().execute(f"SELECT * FROM cenarios {filtro} ORDER BY ordem ASC, id ASC").fetchall()
        return [_para_dict(r) for r in linhas]
    finally:
        conn.close()


def buscar_cenario(cenario_id: int):
    conn = get_connection()
    try:
        row = conn.cursor().execute("SELECT * FROM cenarios WHERE id = ?", (cenario_id,)).fetchone()
        return _para_dict(row) if row else None
    finally:
        conn.close()


def proxima_ordem() -> int:
    conn = get_connection()
    try:
        row = conn.cursor().execute("SELECT MAX(ordem) AS m FROM cenarios").fetchone()
        return (row["m"] or 0) + 10
    finally:
        conn.close()


def criar_cenario(dados: dict, criado_por=None) -> int:
    agora = _agora_iso()
    conn = get_connection()
    try:
        novo_id = conn.cursor().inserir(
            "INSERT INTO cenarios (titulo, fluxo_json, palavras_criticas_json, ativo, ordem, criado_por, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
            (dados["titulo"], json.dumps(dados["fluxo"], ensure_ascii=False),
             json.dumps(dados["palavras_criticas"], ensure_ascii=False), dados["ordem"], criado_por, agora, agora),
        )
        conn.commit()
        return novo_id
    finally:
        conn.close()


def atualizar_cenario(cenario_id: int, dados: dict):
    conn = get_connection()
    try:
        conn.cursor().execute(
            "UPDATE cenarios SET titulo = ?, fluxo_json = ?, palavras_criticas_json = ?, ordem = ?, atualizado_em = ? "
            "WHERE id = ?",
            (dados["titulo"], json.dumps(dados["fluxo"], ensure_ascii=False),
             json.dumps(dados["palavras_criticas"], ensure_ascii=False), dados["ordem"], _agora_iso(), cenario_id),
        )
        conn.commit()
    finally:
        conn.close()


def definir_ativo_cenario(cenario_id: int, ativo: bool):
    conn = get_connection()
    try:
        conn.cursor().execute(
            "UPDATE cenarios SET ativo = ?, atualizado_em = ? WHERE id = ?",
            (1 if ativo else 0, _agora_iso(), cenario_id),
        )
        conn.commit()
    finally:
        conn.close()


def contar_ativos() -> int:
    conn = get_connection()
    try:
        return conn.cursor().execute("SELECT COUNT(*) AS n FROM cenarios WHERE ativo = 1").fetchone()["n"]
    finally:
        conn.close()


def cenarios_para_nova_simulacao() -> list:
    """Cenários ativos na ordem definida; com CENARIOS_POR_SIMULACAO > 0, sorteia essa quantidade."""
    ativos = listar_cenarios(apenas_ativos=True)
    limite = config.CENARIOS_POR_SIMULACAO
    if limite and 0 < limite < len(ativos):
        escolhidos = random.sample(ativos, limite)
        ativos = sorted(escolhidos, key=lambda c: (c["ordem"], c["id"]))
    return ativos
