import unittest

from database.connection import get_connection, usando_postgres
from database.init_db import init_db
from repositories.operador_repository import buscar_operador_por_id, buscar_operador_por_usuario, criar_operador
from tests.helpers import novo_usuario


class CamadaDeBanco(unittest.TestCase):
    def test_init_db_e_idempotente(self):
        init_db()
        init_db()
        conn = get_connection()
        for tabela in ("operadores", "simulacoes", "atendimentos", "mensagens", "avaliacoes", "usuarios"):
            conn.execute(f"SELECT COUNT(*) AS n FROM {tabela}").fetchone()
        conn.close()

    def test_inserir_devolve_ids_crescentes(self):
        a = criar_operador(novo_usuario(), "A", "hash")
        b = criar_operador(novo_usuario(), "B", "hash")
        self.assertIsInstance(a, int)
        self.assertGreater(b, a)

    def test_unicidade_devolve_none_e_conexao_continua_utilizavel(self):
        usuario = novo_usuario()
        self.assertIsNotNone(criar_operador(usuario, "A", "hash"))
        self.assertIsNone(criar_operador(usuario, "B", "hash"))
        self.assertEqual(buscar_operador_por_usuario(usuario)["nome"], "A")  # sem transação abortada

    def test_placeholders_e_tipos(self):
        conn = get_connection()
        linha = conn.execute("SELECT ? AS texto, ? AS inteiro, ? AS real", ("áé", 7, 1760000000.123456)).fetchone() \
            if not usando_postgres() else \
            conn.execute("SELECT CAST(? AS TEXT) AS texto, CAST(? AS INTEGER) AS inteiro, "
                         "CAST(? AS DOUBLE PRECISION) AS real", ("áé", 7, 1760000000.123456)).fetchone()
        conn.close()
        self.assertEqual((linha["texto"], linha["inteiro"]), ("áé", 7))
        self.assertAlmostEqual(linha["real"], 1760000000.123456, places=5)  # timestamps não perdem precisão


@unittest.skipUnless(usando_postgres(), "requer PostgreSQL (defina DATABASE_URL)")
class ConexaoPostgres(unittest.TestCase):
    def test_reconecta_quando_o_servidor_derruba_a_conexao(self):
        import config
        import psycopg

        operador_id = criar_operador(novo_usuario(), "Reconexao", "hash")
        conn = get_connection()
        pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        conn.close()

        with psycopg.connect(config.DATABASE_URL, autocommit=True) as outro:
            outro.execute("SELECT pg_terminate_backend(%s)", (pid,))

        self.assertEqual(buscar_operador_por_id(operador_id)["nome"], "Reconexao")

    def test_conexao_e_reaproveitada_na_mesma_thread(self):
        a = get_connection().execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        b = get_connection().execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        self.assertEqual(a, b)

    def test_erro_de_sql_nao_deixa_a_conexao_inutilizavel(self):
        conn = get_connection()
        with self.assertRaises(Exception):
            conn.execute("SELECT * FROM tabela_que_nao_existe")
        # sem close() de propósito: o próximo get_connection() precisa limpar a transação abortada
        self.assertEqual(get_connection().execute("SELECT 1 AS x").fetchone()["x"], 1)


if __name__ == "__main__":
    unittest.main()
