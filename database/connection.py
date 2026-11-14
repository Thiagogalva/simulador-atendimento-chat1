"""
Acesso ao banco com dois backends e a mesma interface para os repositórios:

  * SQLite  (padrão, arquivo local DB_NAME)          -> desenvolvimento / uso local
  * PostgreSQL (quando DATABASE_URL está definida)    -> produção persistente (Neon, Supabase, Render...)

Os repositórios escrevem SQL com placeholders "?" e leem as linhas por nome (row["coluna"]).
No PostgreSQL os "?" são convertidos para "%s" e a conexão é reaproveitada por thread
(evita abrir uma conexão TLS a cada consulta).
"""
import sqlite3
import threading
import time

import config

_local = threading.local()
_REVALIDAR_APOS_SEGUNDOS = 30


def usando_postgres() -> bool:
    return bool(config.DATABASE_URL)


class Cursor:
    def __init__(self, conexao, cursor_bruto):
        self._conexao = conexao
        self._cur = cursor_bruto

    def execute(self, sql, params=()):
        if self._conexao.postgres:
            sql = sql.replace("?", "%s")
        params = tuple(params)
        try:
            self._cur.execute(sql, params)
        except Exception as erro:
            if not self._conexao.recuperavel(erro):
                raise
            # Conexão reaproveitada que o servidor derrubou: reconecta e repete este comando.
            self._cur = self._conexao.reconectar().cursor()
            self._cur.execute(sql, params)
        self._conexao.comandos += 1
        return self

    def inserir(self, sql, params=()):
        """Executa um INSERT e devolve o id gerado (nos dois bancos)."""
        if self._conexao.postgres:
            self.execute(sql + " RETURNING id", params)
            return self._cur.fetchone()["id"]
        self.execute(sql, params)
        return self._cur.lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)

    @property
    def postgres(self) -> bool:
        return self._conexao.postgres

    @property
    def rowcount(self):
        return self._cur.rowcount


class Conexao:
    def __init__(self, bruta, postgres: bool):
        self._bruta = bruta
        self.postgres = postgres
        self.comandos = 0  # comandos já executados nesta "retirada" da conexão

    def recuperavel(self, erro: Exception) -> bool:
        """Só é seguro reconectar e repetir se nada foi executado ainda na transação atual."""
        if not self.postgres or self.comandos != 0:
            return False
        import psycopg
        return isinstance(erro, (psycopg.OperationalError, psycopg.InterfaceError))

    def reconectar(self):
        import psycopg
        from psycopg.rows import dict_row

        try:
            self._bruta.close()
        except Exception:
            pass
        self._bruta = psycopg.connect(config.DATABASE_URL, row_factory=dict_row, connect_timeout=10)
        _local.pg = (self._bruta, time.monotonic())
        return self._bruta

    def cursor(self):
        return Cursor(self, self._bruta.cursor())

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._bruta.commit()

    def rollback(self):
        self._bruta.rollback()

    def close(self):
        if self.postgres:
            # Mantém a conexão aberta para reutilização; só encerra a transação.
            try:
                self._bruta.rollback()
            except Exception:
                pass
        else:
            self._bruta.close()


def _conexao_postgres() -> Conexao:
    import psycopg
    from psycopg.rows import dict_row

    estado = getattr(_local, "pg", None)
    agora = time.monotonic()

    if estado is not None:
        bruta, ultimo_uso = estado
        try:
            if bruta.closed or bruta.broken:
                raise psycopg.OperationalError("conexão encerrada")
            bruta.rollback()  # limpa qualquer transação deixada por um erro anterior
            if agora - ultimo_uso > _REVALIDAR_APOS_SEGUNDOS:
                bruta.execute("SELECT 1")  # serviços serverless derrubam conexões ociosas
                bruta.rollback()
        except Exception:
            try:
                bruta.close()
            except Exception:
                pass
            estado = None

    if estado is None:
        bruta = psycopg.connect(config.DATABASE_URL, row_factory=dict_row, connect_timeout=10)

    _local.pg = (bruta, agora)
    return Conexao(bruta, True)


def get_connection() -> Conexao:
    if usando_postgres():
        return _conexao_postgres()

    bruta = sqlite3.connect(config.DB_NAME, timeout=10)
    bruta.row_factory = sqlite3.Row
    return Conexao(bruta, False)


def violacao_unicidade(erro: Exception) -> bool:
    """True se `erro` é violação de UNIQUE em qualquer um dos bancos."""
    if isinstance(erro, sqlite3.IntegrityError):
        return True
    if usando_postgres():
        import psycopg
        return isinstance(erro, psycopg.errors.UniqueViolation)
    return False
