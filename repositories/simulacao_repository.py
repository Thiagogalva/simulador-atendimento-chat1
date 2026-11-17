import json
from datetime import datetime, timedelta, timezone

from database.connection import get_connection


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def salvar_simulacao(operador_id: int, iniciada_em: float, resumo: dict):
    """
    Grava a simulação concluída. É idempotente: (operador, iniciada_em) é único,
    então repetir a chamada não duplica o histórico.
    Retorna (id, criada).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO simulacoes (
                operador_id, iniciada_em, finalizada_em, nota_geral, nivel,
                media_coerencia, media_empatia, media_tempo, total_erros,
                total_atendimentos, detalhes_json, modo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (operador_id, iniciada_em) DO NOTHING
        """, (
            operador_id,
            iniciada_em,
            _agora().isoformat(timespec="seconds"),
            resumo["nota_geral"],
            resumo["nivel"],
            resumo["media_coerencia"],
            resumo["media_empatia"],
            resumo["media_tempo"],
            resumo["total_erros"],
            resumo["total_atendimentos"],
            json.dumps(resumo["detalhes"], ensure_ascii=False),
            resumo.get("modo", "avaliacao"),
        ))
        criada = cursor.rowcount == 1
        row = cursor.execute(
            "SELECT id FROM simulacoes WHERE operador_id = ? AND iniciada_em = ?",
            (operador_id, iniciada_em)
        ).fetchone()
        conn.commit()
        return row["id"], criada
    finally:
        conn.close()


def _simulacao_para_dict(row) -> dict:
    return {
        "id": row["id"],
        "finalizada_em": row["finalizada_em"],
        "nota_geral": float(row["nota_geral"]),
        "nivel": row["nivel"],
        "media_coerencia": float(row["media_coerencia"]),
        "media_empatia": float(row["media_empatia"]),
        "media_tempo": float(row["media_tempo"]),
        "total_erros": row["total_erros"],
        "total_atendimentos": row["total_atendimentos"],
        "detalhes": json.loads(row["detalhes_json"] or "[]"),
        "modo": row["modo"],
        "feedback_texto": row["feedback_texto"],
        "feedback_origem": row["feedback_origem"],
    }


def listar_simulacoes_do_operador(operador_id: int, limite: int = 100) -> list:
    """Mais recentes primeiro."""
    conn = get_connection()
    try:
        linhas = conn.cursor().execute(
            "SELECT * FROM simulacoes WHERE operador_id = ? ORDER BY finalizada_em DESC, id DESC LIMIT ?",
            (operador_id, int(limite))
        ).fetchall()
        return [_simulacao_para_dict(r) for r in linhas]
    finally:
        conn.close()


PERIODOS_RANKING = {
    "geral": None,
    "30d": timedelta(days=30),
    "7d": timedelta(days=7),
}


def ranking(periodo: str = "geral", limite: int = 50) -> list:
    """
    Operadores ordenados pela média das notas das simulações de AVALIAÇÃO no período
    (desempate: mais simulações, depois nome). Só expõe nome de exibição.
    """
    janela = PERIODOS_RANKING.get(periodo)
    desde = (_agora() - janela).isoformat(timespec="seconds") if janela else ""

    conn = get_connection()
    try:
        linhas = conn.cursor().execute("""
            SELECT o.id AS operador_id,
                   o.nome AS nome,
                   COUNT(s.id) AS simulacoes,
                   AVG(s.nota_geral) AS media,
                   MAX(s.nota_geral) AS melhor,
                   MAX(s.finalizada_em) AS ultima
            FROM operadores o
            JOIN simulacoes s ON s.operador_id = o.id
            WHERE s.finalizada_em >= ? AND s.modo = 'avaliacao' AND o.ativo = 1
            GROUP BY o.id, o.nome
            ORDER BY media DESC, simulacoes DESC, o.nome ASC
            LIMIT ?
        """, (desde, int(limite))).fetchall()
    finally:
        conn.close()

    resultado = []
    for posicao, r in enumerate(linhas, start=1):
        resultado.append({
            "posicao": posicao,
            "operador_id": r["operador_id"],
            "nome": r["nome"],
            "simulacoes": int(r["simulacoes"]),
            "media": float(r["media"]),
            "melhor": float(r["melhor"]),
            "ultima": r["ultima"],
        })
    return resultado


def posicao_do_operador(operador_id: int, periodo: str = "geral"):
    """(posição, total de operadores no ranking) ou (None, total) se ainda não ranqueado."""
    lista = ranking(periodo, limite=100000)
    for item in lista:
        if item["operador_id"] == operador_id:
            return item["posicao"], len(lista)
    return None, len(lista)


def listar_todas_as_simulacoes() -> list:
    """Todas as simulações com o operador (para exportação do supervisor). Mais recentes primeiro."""
    conn = get_connection()
    try:
        linhas = conn.cursor().execute("""
            SELECT s.*, o.usuario AS usuario, o.nome AS nome
            FROM simulacoes s
            JOIN operadores o ON o.id = s.operador_id
            ORDER BY s.finalizada_em DESC, s.id DESC
        """).fetchall()
    finally:
        conn.close()

    resultado = []
    for r in linhas:
        item = _simulacao_para_dict(r)
        item["usuario"] = r["usuario"]
        item["nome"] = r["nome"]
        resultado.append(item)
    return resultado


def buscar_simulacao_do_operador(operador_id: int, simulacao_id: int):
    conn = get_connection()
    try:
        row = conn.cursor().execute(
            "SELECT * FROM simulacoes WHERE id = ? AND operador_id = ?", (simulacao_id, operador_id)
        ).fetchone()
        return _simulacao_para_dict(row) if row else None
    finally:
        conn.close()


def salvar_feedback_simulacao(simulacao_id: int, texto: str, origem: str):
    conn = get_connection()
    try:
        conn.cursor().execute(
            "UPDATE simulacoes SET feedback_texto = ?, feedback_origem = ? WHERE id = ?",
            (texto, origem, simulacao_id),
        )
        conn.commit()
    finally:
        conn.close()
