import unittest
from unittest import mock

import config
from data.base_atendimentos import BASE_ATENDIMENTOS
from database.connection import get_connection
from repositories.operador_repository import buscar_operador_por_usuario
from repositories.simulacao_repository import ranking
from tests.helpers import (
    SENHA,
    cliente_logado,
    completar_simulacao,
    iniciar,
    liberar_todos,
    novo_usuario,
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


def cadastrar(client, usuario, nome="Fulano", senha=SENHA, confirmacao=None, **extra):
    dados = {"usuario": usuario, "nome": nome, "senha": senha,
             "confirmacao": senha if confirmacao is None else confirmacao}
    dados.update(extra)
    return client.post("/registro", data=dados)


class Autenticacao(unittest.TestCase):
    def test_rotas_exigem_login(self):
        c = app_client()
        for caminho in ("/", "/historico", "/ranking"):
            r = c.get(caminho)
            self.assertEqual(r.status_code, 302, caminho)
            self.assertIn("/login", r.headers["Location"])
        for caminho in ("/responder", "/finalizar"):
            r = c.post(caminho, json={})
            self.assertEqual(r.status_code, 401, caminho)

    def test_paginas_publicas(self):
        c = app_client()
        self.assertEqual(c.get("/login").status_code, 200)
        self.assertEqual(c.get("/registro").status_code, 200)

    def test_registro_valido_ja_entra_logado(self):
        c, _, _ = cliente_logado()
        self.assertEqual(c.get("/").status_code, 200)  # tela de escolha do modo

    def test_usuario_duplicado_e_recusado(self):
        usuario = novo_usuario()
        cadastrar(app_client(), usuario)
        r = cadastrar(app_client(), usuario, nome="Outro")
        self.assertEqual(r.status_code, 400)
        self.assertIn("já está em uso", r.get_data(as_text=True))

    def test_usuario_e_normalizado_para_minusculas(self):
        usuario = novo_usuario()
        cadastrar(app_client(), usuario.upper())
        self.assertIsNotNone(buscar_operador_por_usuario(usuario))
        r = app_client().post("/login", data={"usuario": usuario.upper(), "senha": SENHA})
        self.assertEqual(r.status_code, 302)

    def test_validacoes_do_cadastro(self):
        casos = [
            dict(usuario="ab", nome="Fulano", senha=SENHA),                      # usuário curto
            dict(usuario=novo_usuario(), nome="F", senha=SENHA),                 # nome curto
            dict(usuario=novo_usuario(), nome="Fulano", senha="curta"),          # senha curta
            dict(usuario=novo_usuario(), nome="Fulano", senha=SENHA, confirmacao="diferente1"),
            dict(usuario="com espaco", nome="Fulano", senha=SENHA),              # caractere inválido
        ]
        for caso in casos:
            r = cadastrar(app_client(), **caso)
            self.assertEqual(r.status_code, 400, caso)
            self.assertIn("alerta-erro", r.get_data(as_text=True))
        self.assertIsNone(buscar_operador_por_usuario("com espaco"))

    def test_senha_e_guardada_com_hash(self):
        _, _, usuario = cliente_logado()
        operador = buscar_operador_por_usuario(usuario)
        self.assertNotIn(SENHA, operador["senha_hash"])
        self.assertTrue(operador["senha_hash"].startswith(("scrypt:", "pbkdf2:")))

    def test_login_correto_e_incorreto(self):
        _, _, usuario = cliente_logado()
        ok = app_client().post("/login", data={"usuario": usuario, "senha": SENHA})
        self.assertEqual(ok.status_code, 302)

        errada = app_client().post("/login", data={"usuario": usuario, "senha": "errada123"})
        inexistente = app_client().post("/login", data={"usuario": "ninguem_aqui", "senha": "errada123"})
        self.assertEqual((errada.status_code, inexistente.status_code), (401, 401))
        # mesma mensagem: não revela se o usuário existe
        self.assertIn("Usuário ou senha inválidos", errada.get_data(as_text=True))
        self.assertIn("Usuário ou senha inválidos", inexistente.get_data(as_text=True))

    def test_bloqueio_apos_varias_falhas(self):
        _, _, usuario = cliente_logado()
        c = app_client()
        for _ in range(5):
            self.assertEqual(c.post("/login", data={"usuario": usuario, "senha": "errada123"}).status_code, 401)
        r = c.post("/login", data={"usuario": usuario, "senha": SENHA})  # mesmo com a senha certa
        self.assertEqual(r.status_code, 429)

    def test_codigo_de_convite(self):
        with mock.patch.object(config, "CODIGO_CONVITE", "segredo-123"):
            self.assertEqual(cadastrar(app_client(), novo_usuario()).status_code, 400)
            self.assertEqual(cadastrar(app_client(), novo_usuario(), convite="errado").status_code, 400)
            self.assertEqual(cadastrar(app_client(), novo_usuario(), convite="segredo-123").status_code, 302)

    def test_logout(self):
        c, _, _ = cliente_logado()
        self.assertEqual(c.get("/sair").status_code, 405)   # só POST
        self.assertEqual(c.post("/sair").status_code, 400)   # sem token CSRF
        self.assertEqual(post_form(c, "/sair").status_code, 302)
        self.assertEqual(c.get("/").status_code, 302)

    def test_cookie_de_sessao_seguro(self):
        usuario = novo_usuario()
        r = cadastrar(app_client(), usuario)
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_operador_removido_do_banco_invalida_a_sessao(self):
        c, operador_id, _ = cliente_logado()
        conn = get_connection()
        conn.execute("DELETE FROM operadores WHERE id = ?", (operador_id,))
        conn.commit()
        conn.close()
        self.assertEqual(c.get("/").status_code, 302)
        self.assertEqual(c.post("/responder", json={"id": 0, "resposta": "texto"}).status_code, 401)

    def test_nome_com_html_e_escapado(self):
        c, _, _ = cliente_logado(nome="<script>alert(1)</script>")
        html = c.get("/historico").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


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
