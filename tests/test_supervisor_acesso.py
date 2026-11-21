import csv
import io
import time
import unittest
from unittest import mock

import config
from database.connection import get_connection
from repositories.operador_repository import buscar_operador_por_usuario, criar_operador, listar_auditoria
from repositories.simulacao_repository import ranking, salvar_simulacao
from routes.supervisor import _celula
from services.auth_service import limitador_supervisor
from tests.helpers import (
    cliente_logado,
    completar_simulacao,
    post_form,
    tornar_supervisor,
)

CODIGO = "codigo-de-teste-supervisor"   # definido em tests/__init__.py


def entrar(client, codigo=CODIGO):
    return post_form(client, "/supervisor/entrar", {"codigo": codigo})


def limpar_limitador(addCleanup):
    chave = "sup|127.0.0.1"
    limitador_supervisor.limpar(chave)
    addCleanup(limitador_supervisor.limpar, chave)


class AcessoPorCodigo(unittest.TestCase):
    def setUp(self):
        limpar_limitador(self.addCleanup)
        self.c, self.oid, _ = cliente_logado(nome="Pessoa Qualquer")

    def test_sem_liberar_a_area_fica_fechada(self):
        for caminho in ("/supervisor", "/supervisor/cenarios", "/supervisor/exportar.csv", "/supervisor/calibrador"):
            r = self.c.get(caminho)
            self.assertEqual(r.status_code, 302, caminho)
            self.assertIn("/supervisor/entrar", r.headers["Location"])

    def test_acoes_e_json_sem_liberar_retornam_403(self):
        self.assertEqual(post_form(self.c, "/supervisor/operadores/1/ativo", {"ativo": "0"}).status_code, 403)
        self.assertEqual(post_form(self.c, "/supervisor/cenarios/novo", {"titulo": "x"}).status_code, 403)
        r = self.c.post("/supervisor/calibrador/salvar-passo", json={"cenario_id": 1, "passo_idx": 0, "passo": {}})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["erro"], "Acesso negado.")

    def test_exige_ter_informado_o_nome(self):
        import app as aplicacao
        r = aplicacao.app.test_client().get("/supervisor/entrar")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/identificar", r.headers["Location"])

    def test_codigo_correto_libera(self):
        r = entrar(self.c)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/supervisor").status_code, 200)
        self.assertIn("Painel do supervisor", self.c.get("/supervisor").get_data(as_text=True))
        self.assertIn("entrou na área do supervisor", [a["acao"] for a in listar_auditoria(50)])

    def test_codigo_errado_nao_libera(self):
        for tentativa in ("", "errado", CODIGO + "x", CODIGO[:-1], CODIGO.upper()):
            self.assertEqual(entrar(self.c, tentativa).status_code, 401, repr(tentativa))
        self.assertEqual(self.c.get("/supervisor").status_code, 302)

    def test_bloqueio_apos_varias_tentativas(self):
        for _ in range(5):
            self.assertEqual(entrar(self.c, "errado").status_code, 401)
        self.assertEqual(entrar(self.c).status_code, 429)  # nem o código certo passa durante o bloqueio

    def test_formulario_exige_csrf(self):
        self.assertEqual(self.c.post("/supervisor/entrar", data={"codigo": CODIGO}).status_code, 400)

    def test_liberacao_expira(self):
        entrar(self.c)
        with self.c.session_transaction() as s:
            s["supervisor_ate"] = time.time() - 1
        self.assertEqual(self.c.get("/supervisor").status_code, 302)

    def test_sair_do_modo_supervisor(self):
        entrar(self.c)
        self.assertEqual(post_form(self.c, "/supervisor/sair").status_code, 302)
        self.assertEqual(self.c.get("/supervisor").status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 200)  # continua identificado como operador

    def test_trocar_de_nome_tira_o_acesso_de_supervisor(self):
        entrar(self.c)
        post_form(self.c, "/sair")
        from tests.test_operadores import identificar, nome_novo
        identificar(self.c, nome_novo("Outra"))
        self.assertEqual(self.c.get("/supervisor").status_code, 302)

    def test_cookie_forjado_nao_vale_sem_o_segredo_certo(self):
        """Quem não conhece a SECRET_KEY não consegue fabricar a liberação (o cookie é assinado)."""
        import app as aplicacao
        outro = app_com_outra_chave()
        cookie = outro.dumps({"operador_id": self.oid, "operador_nome": "x", "usuario_id": f"operador-{self.oid}",
                              "supervisor_ate": time.time() + 3600})
        c = aplicacao.app.test_client()
        c.set_cookie("session", cookie)
        self.assertEqual(c.get("/supervisor").status_code, 302)  # assinatura inválida: sessão ignorada

    def test_menu_mostra_o_link_certo(self):
        self.assertIn("Área do supervisor", self.c.get("/").get_data(as_text=True))
        entrar(self.c)
        html = self.c.get("/").get_data(as_text=True)
        self.assertIn(">Supervisor<", html)


def app_com_outra_chave():
    import app as aplicacao
    from flask.sessions import SecureCookieSessionInterface
    from itsdangerous import URLSafeTimedSerializer
    interface = SecureCookieSessionInterface()
    return URLSafeTimedSerializer("uma-chave-qualquer-diferente", salt="cookie-session",
                                  serializer=interface.get_signing_serializer(aplicacao.app).serializer,
                                  signer_kwargs={"key_derivation": "hmac", "digest_method": interface.digest_method})


class AreaDesativada(unittest.TestCase):
    def setUp(self):
        limpar_limitador(self.addCleanup)
        self.c, _, _ = cliente_logado()

    def test_sem_codigo_configurado_a_area_fica_desativada(self):
        with mock.patch.object(config, "SUPERVISOR_CODIGO", ""):
            r = self.c.get("/supervisor/entrar")
            self.assertEqual(r.status_code, 503)
            self.assertIn("SUPERVISOR_CODIGO", r.get_data(as_text=True))
            tornar_supervisor(self.c)  # nem uma sessão "liberada" abre a área
            self.assertEqual(self.c.get("/supervisor").status_code, 302)

    def test_secret_key_padrao_desativa_a_area(self):
        with mock.patch.object(config, "SECRET_KEY", config.SECRET_KEY_PADRAO):
            r = self.c.get("/supervisor/entrar")
            self.assertEqual(r.status_code, 503)
            self.assertIn("SECRET_KEY", r.get_data(as_text=True))
            tornar_supervisor(self.c)
            self.assertEqual(self.c.get("/supervisor").status_code, 302)


class PainelDoSupervisor(unittest.TestCase):
    def setUp(self):
        limpar_limitador(self.addCleanup)
        self.s, self.sid, _ = cliente_logado(nome="Chefe Painel")
        tornar_supervisor(self.s)

    def test_lista_os_operadores_sem_papel_ou_senha(self):
        cliente_logado(nome="Listado Aqui")
        html = self.s.get("/supervisor").get_data(as_text=True)
        self.assertIn("Listado Aqui", html)
        for removido in ("Redefinir senha", "Tornar supervisor", "Senha temporária", "<th>Papel</th>"):
            self.assertNotIn(removido, html)

    def test_acoes_exigem_csrf(self):
        _, alvo_id, _ = cliente_logado()
        self.assertEqual(self.s.post(f"/supervisor/operadores/{alvo_id}/ativo", data={"ativo": "0"}).status_code, 400)

    def test_rotas_de_senha_e_papel_nao_existem(self):
        _, alvo_id, _ = cliente_logado()
        self.assertEqual(post_form(self.s, f"/supervisor/operadores/{alvo_id}/senha").status_code, 404)
        self.assertEqual(post_form(self.s, f"/supervisor/operadores/{alvo_id}/papel", {"papel": "supervisor"}).status_code, 404)

    def test_operador_inexistente_da_404(self):
        self.assertEqual(self.s.get("/supervisor/operadores/99999999").status_code, 404)
        self.assertEqual(post_form(self.s, "/supervisor/operadores/99999999/ativo", {"ativo": "0"}).status_code, 404)

    def test_nao_bloqueia_o_proprio_nome(self):
        r = post_form(self.s, f"/supervisor/operadores/{self.sid}/ativo", {"ativo": "0"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.s.get("/supervisor").status_code, 200)

    def test_bloquear_derruba_a_sessao_tira_do_ranking_e_impede_nova_entrada(self):
        b, b_id, b_chave = cliente_logado(nome="Sera Bloqueado")
        completar_simulacao(b, b_id)
        b.post("/finalizar")
        self.assertIn(b_id, {i["operador_id"] for i in ranking("geral", limite=100000)})

        post_form(self.s, f"/supervisor/operadores/{b_id}/ativo", {"ativo": "0"})
        self.assertEqual(b.get("/").status_code, 302)
        self.assertEqual(b.post("/responder", json={"id": 0, "resposta": "x"}).status_code, 401)
        self.assertNotIn(b_id, {i["operador_id"] for i in ranking("geral", limite=100000)})
        from tests.test_operadores import identificar
        self.assertEqual(identificar(b, buscar_operador_por_usuario(b_chave)["nome"]).status_code, 403)

        post_form(self.s, f"/supervisor/operadores/{b_id}/ativo", {"ativo": "1"})
        self.assertEqual(identificar(b, buscar_operador_por_usuario(b_chave)["nome"]).status_code, 302)
        self.assertIn(b_id, {i["operador_id"] for i in ranking("geral", limite=100000)})
        acoes = [a["acao"] for a in listar_auditoria(50)]
        self.assertIn("bloqueou o nome", acoes)
        self.assertIn("desbloqueou o nome", acoes)

    def test_detalhe_do_operador(self):
        b, b_id, _ = cliente_logado(nome="Detalhe Aqui")
        completar_simulacao(b, b_id)
        b.post("/finalizar")
        html = self.s.get(f"/supervisor/operadores/{b_id}").get_data(as_text=True)
        self.assertIn("Detalhe Aqui", html)
        self.assertIn("Ver atendimentos", html)


class ExportacaoCsv(unittest.TestCase):
    def setUp(self):
        limpar_limitador(self.addCleanup)
        self.s, _, _ = cliente_logado(nome="Chefe Csv")
        tornar_supervisor(self.s)

    def test_csv_com_dados(self):
        b, b_id, b_chave = cliente_logado(nome="Operador Csv")
        completar_simulacao(b, b_id)
        b.post("/finalizar")
        r = self.s.get("/supervisor/exportar.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["Content-Type"])
        self.assertIn("attachment", r.headers["Content-Disposition"])
        texto = r.get_data(as_text=True)
        self.assertTrue(texto.startswith("\ufeff"))
        linhas = list(csv.reader(io.StringIO(texto.lstrip("\ufeff"))))
        self.assertEqual(linhas[0][:4], ["finalizada_em_utc", "usuario", "nome", "modo"])
        self.assertEqual(len([l for l in linhas[1:] if l[1] == b_chave]), 1)
        self.assertIn("exportou o CSV de simulações", [a["acao"] for a in listar_auditoria(50)])

    def test_protecao_contra_formulas(self):
        for perigoso in ("=1+1", "+cmd", "-2", "@soma", "\tx"):
            self.assertTrue(_celula(perigoso).startswith("'"), perigoso)
        self.assertEqual(_celula("normal"), "normal")
        # mesmo que um nome perigoso chegue ao banco por outro caminho, a exportação o neutraliza
        oid = criar_operador("chave formula " + str(time.time()), '=HYPERLINK("http://x")')
        salvar_simulacao(oid, time.time(), {
            "nota_geral": 50.0, "nivel": "x", "media_coerencia": 1.0, "media_empatia": 1.0, "media_tempo": 1.0,
            "total_erros": 0, "total_atendimentos": 1, "detalhes": [], "modo": "avaliacao"})
        texto = self.s.get("/supervisor/exportar.csv").get_data(as_text=True)
        self.assertIn("'=HYPERLINK", texto)
        self.assertNotIn(",=HYPERLINK", texto)


if __name__ == "__main__":
    unittest.main()
