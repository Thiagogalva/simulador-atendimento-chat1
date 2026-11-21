import unittest
from unittest import mock

import config
from data.base_atendimentos import BASE_ATENDIMENTOS
from database.connection import get_connection
from repositories.operador_repository import buscar_operador_por_usuario
from repositories.simulacao_repository import ranking
from services.auth_service import chave_do_nome, limitador_nomes_novos
from tests.helpers import (
    _letras,
    cliente_logado,
    completar_simulacao,
    iniciar,
    liberar_todos,
    post_form,
)

FORA = [
    "Hoje o dia está bonito e vamos almoçar mais tarde, tudo bem com você.",
    "O jogo de futebol começa às oito horas da noite no estádio da cidade.",
    "Amanhã vou viajar para a praia com a minha família durante o feriado.",
]


def app_client():
    import app as aplicacao
    return aplicacao.app.test_client()


def nome_novo(base="Ana"):
    return f"{base} {_letras()}"


def identificar(client, nome):
    return client.post("/identificar", data={"nome": nome})


class Identificacao(unittest.TestCase):
    def test_rotas_exigem_o_nome(self):
        c = app_client()
        for caminho in ("/", "/historico", "/ranking", "/simulacao"):
            r = c.get(caminho)
            self.assertEqual(r.status_code, 302, caminho)
            self.assertIn("/identificar", r.headers["Location"])
        for caminho in ("/responder", "/finalizar", "/dica", "/feedback"):
            r = c.post(caminho, json={})
            self.assertEqual(r.status_code, 401, caminho)

    def test_login_e_cadastro_nao_existem_mais(self):
        c = app_client()
        for caminho in ("/login", "/registro", "/recuperar", "/senha", "/conta/codigo"):
            self.assertIn(c.get(caminho).status_code, (302, 404), caminho)
        self.assertEqual(c.get("/identificar").status_code, 200)

    def test_tela_de_identificacao_pede_so_o_nome(self):
        html = app_client().get("/identificar").get_data(as_text=True)
        self.assertIn('name="nome"', html)
        self.assertNotIn("senha", html.lower())
        self.assertNotIn('type="password"', html)

    def test_informar_o_nome_libera_o_sistema(self):
        c = app_client()
        r = identificar(c, nome_novo("Maria Souza"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)

    def test_mesmo_nome_escrito_de_formas_diferentes_e_a_mesma_pessoa(self):
        base = nome_novo("João Silva")
        a, b = app_client(), app_client()
        identificar(a, base)
        identificar(b, "  " + base.upper().replace(" ", "   ") + " ")
        id_a = buscar_operador_por_usuario(chave_do_nome(base))["id"]
        conn = get_connection()
        total = conn.execute("SELECT COUNT(*) AS n FROM operadores WHERE usuario = ?", (chave_do_nome(base),)).fetchone()["n"]
        conn.close()
        self.assertEqual(total, 1)
        self.assertIn(base, a.get("/historico").get_data(as_text=True))
        self.assertIn(base, b.get("/historico").get_data(as_text=True))  # mostra o nome da 1ª vez
        iniciar(a, "treino")
        # o histórico/ranking do mesmo operador vale para as duas sessões
        completar_simulacao(a, id_a, modo="treino")
        a.post("/finalizar")
        self.assertIn("Treino", b.get("/historico").get_data(as_text=True))

    def test_acentos_nao_criam_outra_pessoa(self):
        base = nome_novo("Jose")
        identificar(app_client(), base)
        identificar(app_client(), base.replace("Jose", "José"))
        conn = get_connection()
        n = conn.execute("SELECT COUNT(*) AS n FROM operadores WHERE usuario = ?", (chave_do_nome(base),)).fetchone()["n"]
        conn.close()
        self.assertEqual(n, 1)

    def test_nomes_invalidos_sao_recusados(self):
        for nome in ("", "   ", "A", "12345", "<script>alert(1)</script>", "Maria 2", "x" * 41, "=cmd|calc"):
            r = identificar(app_client(), nome)
            self.assertEqual(r.status_code, 400, repr(nome))
            self.assertIn("alerta-erro", r.get_data(as_text=True))
            self.assertIsNone(buscar_operador_por_usuario(chave_do_nome(nome)) if chave_do_nome(nome) else None, repr(nome))

    def test_nome_com_acentos_hifen_e_apostrofo_e_aceito(self):
        for base in ("José D'Ávila-Souza", "Ana Clara"):
            self.assertEqual(identificar(app_client(), nome_novo(base)).status_code, 302, base)

    def test_nome_bloqueado_pelo_supervisor_nao_entra(self):
        c, oid, chave = cliente_logado()
        conn = get_connection()
        conn.execute("UPDATE operadores SET ativo = 0 WHERE id = ?", (oid,))
        conn.commit()
        conn.close()
        self.assertEqual(c.get("/").status_code, 302)                       # a sessão aberta cai
        r = identificar(app_client(), buscar_operador_por_usuario(chave)["nome"])
        self.assertEqual(r.status_code, 403)
        self.assertIn("bloqueado", r.get_data(as_text=True))

    def test_trocar_de_nome(self):
        c, _, _ = cliente_logado()
        self.assertEqual(c.post("/sair").status_code, 400)                   # exige CSRF
        r = post_form(c, "/sair")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/identificar", r.headers["Location"])
        self.assertEqual(c.get("/").status_code, 302)

    def test_sessao_com_operador_inexistente_volta_para_a_identificacao(self):
        c, oid, _ = cliente_logado()
        conn = get_connection()
        conn.execute("DELETE FROM operadores WHERE id = ?", (oid,))
        conn.commit()
        conn.close()
        self.assertEqual(c.get("/").status_code, 302)
        self.assertEqual(c.post("/responder", json={"id": 0, "resposta": "texto"}).status_code, 401)

    def test_limite_de_nomes_novos_por_ip(self):
        chave = "nome|127.0.0.1"
        limitador_nomes_novos.limpar(chave)
        self.addCleanup(limitador_nomes_novos.limpar, chave)
        with mock.patch.object(config, "NOMES_NOVOS_POR_HORA", 2):
            self.assertEqual(identificar(app_client(), nome_novo("Um")).status_code, 302)
            self.assertEqual(identificar(app_client(), nome_novo("Dois")).status_code, 302)
            self.assertEqual(identificar(app_client(), nome_novo("Tres")).status_code, 429)
            # quem já existe continua entrando normalmente
            existente = nome_novo("Existente")
            limitador_nomes_novos.limpar(chave)
            identificar(app_client(), existente)
            limitador_nomes_novos.registrar_falha(chave)
            limitador_nomes_novos.registrar_falha(chave)
            self.assertEqual(identificar(app_client(), existente).status_code, 302)

    def test_cookie_de_sessao_e_seguro(self):
        r = identificar(app_client(), nome_novo())
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_nome_com_apostrofo_e_exibido_escapado(self):
        c, _, _ = cliente_logado(nome="Ana O'Neil")
        self.assertIn("O&#39;Neil", c.get("/historico").get_data(as_text=True))


class HistoricoERanking(unittest.TestCase):
    def test_nao_finaliza_antes_de_terminar_nem_aceita_nota_do_cliente(self):
        c, _, _ = cliente_logado()
        iniciar(c)
        r = c.post("/finalizar", json={"nota_geral": 100, "nivel": "Especialista"})
        self.assertEqual(r.status_code, 409)

    def test_simulacao_completa_vai_para_o_historico_sem_duplicar(self):
        c, operador_id, _ = cliente_logado(nome="Maria Historico")
        ultimo = completar_simulacao(c, operador_id)
        self.assertTrue(ultimo["finalizado"])

        r = c.post("/finalizar")
        self.assertEqual(r.status_code, 200, r.get_json())
        dados = r.get_json()
        self.assertTrue(dados["salva_agora"])
        self.assertGreaterEqual(dados["nota_geral"], 90)
        self.assertIsInstance(dados["posicao"], int)

        repetida = c.post("/finalizar").get_json()
        self.assertEqual(repetida["id"], dados["id"])
        self.assertFalse(repetida["salva_agora"])

        conn = get_connection()
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM simulacoes WHERE operador_id = ?", (operador_id,)
        ).fetchone()["n"]
        conn.close()
        self.assertEqual(total, 1)

        pagina = c.get("/historico").get_data(as_text=True)
        self.assertIn(str(dados["nota_geral"]), pagina)
        self.assertIn(BASE_ATENDIMENTOS[0]["titulo"], pagina)
        self.assertIn("<svg", pagina)

    def test_historico_vazio(self):
        c, _, _ = cliente_logado()
        pagina = c.get("/historico").get_data(as_text=True)
        self.assertIn("ainda não concluiu", pagina)

    def test_tempo_esgotado_em_todos_os_chats_conta_nota_zero(self):
        c, operador_id, _ = cliente_logado()
        iniciar(c)
        liberar_todos(c)  # todos liberados há muito tempo e sem resposta
        r = c.post("/finalizar")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["nota_geral"], 0)

    def test_ranking_ordena_por_media(self):
        bom, id_bom, _ = cliente_logado(nome="Rank Bom")
        ruim, id_ruim, _ = cliente_logado(nome="Rank Ruim")

        completar_simulacao(bom, id_bom)
        i = {"n": 0}

        def fora_de_contexto(at, passo):
            i["n"] += 1
            return FORA[i["n"] % len(FORA)]

        completar_simulacao(ruim, id_ruim, respostas=fora_de_contexto)

        nota_bom = bom.post("/finalizar").get_json()["nota_geral"]
        nota_ruim = ruim.post("/finalizar").get_json()["nota_geral"]
        self.assertGreater(nota_bom, nota_ruim)

        itens = {r["operador_id"]: r for r in ranking("geral", limite=100000)}
        self.assertLess(itens[id_bom]["posicao"], itens[id_ruim]["posicao"])
        self.assertAlmostEqual(itens[id_bom]["media"], nota_bom, places=1)

        pagina = bom.get("/ranking").get_data(as_text=True)
        self.assertIn("Rank Bom", pagina)
        self.assertIn("linha-eu", pagina)

    def test_ranking_periodos(self):
        c, _, _ = cliente_logado()
        for periodo in ("geral", "30d", "7d", "invalido"):
            self.assertEqual(c.get(f"/ranking?periodo={periodo}").status_code, 200, periodo)


if __name__ == "__main__":
    unittest.main()
