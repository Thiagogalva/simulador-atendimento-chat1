import csv
import io
import re
import unittest
from unittest import mock

import config
from database.connection import get_connection
from repositories.operador_repository import buscar_operador_por_usuario, definir_papel, listar_auditoria
from repositories.simulacao_repository import ranking
from tests.helpers import (
    SENHA,
    cliente_logado,
    completar_simulacao,
    novo_usuario,
    post_form,
)

PADRAO_CODIGO = r"[A-Z2-9]{4}(?:-[A-Z2-9]{4}){3}"
NOVA_SENHA = "outrasenha99"


def app_client():
    import app as aplicacao
    return aplicacao.app.test_client()


def ler_codigo(client) -> str:
    """Lê o código mostrado uma única vez (e confirma que não reaparece)."""
    html = client.get("/conta/codigo").get_data(as_text=True)
    achado = re.search(r'class="codigo-recuperacao"[^>]*>(' + PADRAO_CODIGO + ")<", html)
    assert achado, html[:500]
    assert client.get("/conta/codigo").status_code == 302  # segunda visita: nada para mostrar
    return achado.group(1)


def operador_com_codigo(nome="Maria Recupera"):
    c, oid, usuario = cliente_logado(nome=nome)
    return c, oid, usuario, ler_codigo(c)


def supervisor(nome="Chefe Teste"):
    c, oid, usuario = cliente_logado(nome=nome)
    definir_papel(oid, "supervisor")
    return c, oid, usuario


def recuperar(client, usuario, codigo, senha=NOVA_SENHA, confirmacao=None):
    return client.post("/recuperar", data={
        "usuario": usuario, "codigo": codigo, "senha": senha,
        "confirmacao": senha if confirmacao is None else confirmacao,
    })


def login(usuario, senha):
    c = app_client()
    r = c.post("/login", data={"usuario": usuario, "senha": senha})
    return c, r


class CodigoDeRecuperacao(unittest.TestCase):
    def test_codigo_aparece_uma_vez_apos_o_cadastro(self):
        c, _, _, codigo = operador_com_codigo()
        self.assertRegex(codigo, "^" + PADRAO_CODIGO + "$")

    def test_codigo_nao_e_guardado_em_texto_puro(self):
        _, _, usuario, codigo = operador_com_codigo()
        guardado = buscar_operador_por_usuario(usuario)["recuperacao_hash"]
        self.assertNotIn(codigo.replace("-", ""), guardado)

    def test_recuperacao_completa(self):
        _, _, usuario, codigo = operador_com_codigo()
        novo = app_client()
        r = recuperar(novo, usuario, codigo.lower())  # aceita minúsculas
        self.assertEqual(r.status_code, 302)
        novo_codigo = ler_codigo(novo)               # entra logado e recebe um novo código
        self.assertNotEqual(novo_codigo, codigo)

        self.assertEqual(login(usuario, SENHA)[1].status_code, 401)        # senha antiga morreu
        self.assertEqual(login(usuario, NOVA_SENHA)[1].status_code, 302)   # nova funciona
        self.assertEqual(recuperar(app_client(), usuario, codigo).status_code, 400)  # código usado não vale
        self.assertEqual(recuperar(app_client(), usuario, novo_codigo, senha="terceira123").status_code, 302)

    def test_senha_fraca_nao_consome_o_codigo(self):
        _, _, usuario, codigo = operador_com_codigo()
        self.assertEqual(recuperar(app_client(), usuario, codigo, senha="curta").status_code, 400)
        self.assertEqual(recuperar(app_client(), usuario, codigo).status_code, 302)

    def test_erros_nao_revelam_se_o_usuario_existe(self):
        _, _, usuario, _ = operador_com_codigo()
        errado = recuperar(app_client(), usuario, "AAAA-BBBB-CCCC-DDDD")
        inexistente = recuperar(app_client(), "ninguem_aqui_xyz", "AAAA-BBBB-CCCC-DDDD")
        self.assertEqual((errado.status_code, inexistente.status_code), (400, 400))
        self.assertIn("inválidos", errado.get_data(as_text=True))
        self.assertIn("inválidos", inexistente.get_data(as_text=True))

    def test_bloqueio_apos_varias_tentativas(self):
        _, _, usuario, codigo = operador_com_codigo()
        c = app_client()
        for _ in range(5):
            self.assertEqual(recuperar(c, usuario, "AAAA-BBBB-CCCC-DDDD").status_code, 400)
        self.assertEqual(recuperar(c, usuario, codigo).status_code, 429)  # nem o código certo passa

    def test_conta_desativada_nao_recupera(self):
        _, oid, usuario, codigo = operador_com_codigo()
        conn = get_connection()
        conn.execute("UPDATE operadores SET ativo = 0 WHERE id = ?", (oid,))
        conn.commit()
        conn.close()
        self.assertEqual(recuperar(app_client(), usuario, codigo).status_code, 400)


class TrocaDeSenha(unittest.TestCase):
    def test_troca_com_senha_atual_correta(self):
        c, _, usuario = cliente_logado()
        outra_sessao, _ = login(usuario, SENHA)
        self.assertEqual(outra_sessao.get("/").status_code, 200)

        r = post_form(c, "/senha", {"senha_atual": SENHA, "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)                 # esta sessão continua
        self.assertEqual(outra_sessao.get("/").status_code, 302)      # as outras caem
        self.assertEqual(login(usuario, SENHA)[1].status_code, 401)
        self.assertEqual(login(usuario, NOVA_SENHA)[1].status_code, 302)

    def test_senha_atual_errada_ou_nova_igual(self):
        c, _, _ = cliente_logado()
        errada = post_form(c, "/senha", {"senha_atual": "x" * 9, "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA})
        igual = post_form(c, "/senha", {"senha_atual": SENHA, "senha": SENHA, "confirmacao": SENHA})
        fraca = post_form(c, "/senha", {"senha_atual": SENHA, "senha": "curta", "confirmacao": "curta"})
        self.assertEqual((errada.status_code, igual.status_code, fraca.status_code), (400, 400, 400))

    def test_senha_exige_csrf(self):
        c, _, _ = cliente_logado()
        r = c.post("/senha", data={"senha_atual": SENHA, "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA})
        self.assertEqual(r.status_code, 400)

    def test_novo_codigo_invalida_o_anterior(self):
        c, _, usuario, antigo = operador_com_codigo()
        recusado = post_form(c, "/conta/novo-codigo", {"senha_atual": "errada1234"})
        self.assertEqual(recusado.status_code, 302)
        self.assertIn("/senha", recusado.headers["Location"])

        r = post_form(c, "/conta/novo-codigo", {"senha_atual": SENHA})
        self.assertEqual(r.status_code, 302)
        novo = ler_codigo(c)
        self.assertEqual(recuperar(app_client(), usuario, antigo).status_code, 400)
        self.assertEqual(recuperar(app_client(), usuario, novo).status_code, 302)


class PermissoesDoSupervisor(unittest.TestCase):
    def test_operador_comum_nao_acessa(self):
        c, _, _ = cliente_logado()
        _, alvo_id, _ = cliente_logado()
        self.assertEqual(c.get("/supervisor").status_code, 403)
        self.assertEqual(c.get("/supervisor/exportar.csv").status_code, 403)
        self.assertEqual(c.get(f"/supervisor/operadores/{alvo_id}").status_code, 403)
        for acao, dados in (("senha", {}), ("ativo", {"ativo": "0"}), ("papel", {"papel": "supervisor"})):
            r = post_form(c, f"/supervisor/operadores/{alvo_id}/{acao}", dados)
            self.assertEqual(r.status_code, 403, acao)

    def test_anonimo_vai_para_o_login(self):
        r = app_client().get("/supervisor")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_painel_lista_operadores(self):
        s, _, _ = supervisor()
        _, _, _ = cliente_logado(nome="Listado Aqui")
        html = s.get("/supervisor").get_data(as_text=True)
        self.assertIn("Painel do supervisor", html)
        self.assertIn("Listado Aqui", html)

    def test_acoes_exigem_csrf(self):
        s, _, _ = supervisor()
        _, alvo_id, _ = cliente_logado()
        r = s.post(f"/supervisor/operadores/{alvo_id}/ativo", data={"ativo": "0"})
        self.assertEqual(r.status_code, 400)

    def test_operador_inexistente_da_404(self):
        s, _, _ = supervisor()
        self.assertEqual(s.get("/supervisor/operadores/99999999").status_code, 404)
        self.assertEqual(post_form(s, "/supervisor/operadores/99999999/ativo", {"ativo": "0"}).status_code, 404)

    def test_supervisor_nao_age_sobre_si_mesmo(self):
        s, sid, _ = supervisor()
        for acao, dados in (("senha", {}), ("ativo", {"ativo": "0"}), ("papel", {"papel": "operador"})):
            r = post_form(s, f"/supervisor/operadores/{sid}/{acao}", dados)
            self.assertEqual(r.status_code, 302, acao)
        self.assertEqual(s.get("/supervisor").status_code, 200)  # continua supervisor e ativo

    def test_papel_invalido_e_recusado(self):
        s, _, _ = supervisor()
        _, alvo_id, _ = cliente_logado()
        self.assertEqual(post_form(s, f"/supervisor/operadores/{alvo_id}/papel", {"papel": "admin"}).status_code, 400)

    def test_promover_e_rebaixar(self):
        s, _, _ = supervisor()
        b, b_id, _ = cliente_logado()
        self.assertEqual(b.get("/supervisor").status_code, 403)
        post_form(s, f"/supervisor/operadores/{b_id}/papel", {"papel": "supervisor"})
        self.assertEqual(b.get("/supervisor").status_code, 200)
        post_form(s, f"/supervisor/operadores/{b_id}/papel", {"papel": "operador"})
        self.assertEqual(b.get("/supervisor").status_code, 403)

    def test_supervisor_definido_na_configuracao_e_fixo(self):
        fixo, fixo_id, usuario_fixo = cliente_logado(nome="Fixo Config")
        s, _, _ = supervisor()
        with mock.patch.object(config, "SUPERVISORES", frozenset({usuario_fixo})):
            self.assertEqual(fixo.get("/supervisor").status_code, 200)  # sem papel no banco
            post_form(s, f"/supervisor/operadores/{fixo_id}/ativo", {"ativo": "0"})
            post_form(s, f"/supervisor/operadores/{fixo_id}/papel", {"papel": "operador"})
            self.assertEqual(fixo.get("/supervisor").status_code, 200)  # nada mudou
            self.assertTrue(buscar_operador_por_usuario(usuario_fixo)["ativo"])


class AcoesSobreOperadores(unittest.TestCase):
    def test_redefinir_senha_gera_temporaria_que_obriga_a_trocar(self):
        s, _, _ = supervisor()
        b, b_id, b_usuario = cliente_logado(nome="Esqueceu Senha")

        r = post_form(s, f"/supervisor/operadores/{b_id}/senha")
        self.assertEqual(r.status_code, 302)
        painel = s.get("/supervisor").get_data(as_text=True)
        temporaria = re.search(r'class="codigo-recuperacao">([A-Z2-9]{4}(?:-[A-Z2-9]{4}){2})<', painel).group(1)
        self.assertNotIn(temporaria, s.get("/supervisor").get_data(as_text=True))  # aparece só uma vez

        self.assertEqual(b.get("/").status_code, 302)  # sessão antiga caiu (a senha mudou)
        novo, r = login(b_usuario, temporaria)
        self.assertEqual(r.status_code, 302)
        r = novo.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/senha", r.headers["Location"])        # preso na troca de senha
        self.assertEqual(novo.post("/responder", json={"id": 0, "resposta": "x"}).status_code, 403)
        self.assertEqual(novo.get("/senha").status_code, 200)

        r = post_form(novo, "/senha", {"senha_atual": temporaria, "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(novo.get("/").status_code, 200)       # liberado
        self.assertEqual(login(b_usuario, temporaria)[1].status_code, 401)
        self.assertIn("redefiniu a senha", [a["acao"] for a in listar_auditoria(50)])

    def test_desativar_derruba_sessao_e_tira_do_ranking(self):
        s, _, _ = supervisor()
        b, b_id, b_usuario = cliente_logado(nome="Sera Desativado")
        completar_simulacao(b, b_id)
        b.post("/finalizar")
        self.assertIn(b_id, {i["operador_id"] for i in ranking("geral", limite=100000)})

        post_form(s, f"/supervisor/operadores/{b_id}/ativo", {"ativo": "0"})
        self.assertEqual(b.get("/").status_code, 302)  # sessão invalidada
        self.assertEqual(b.post("/responder", json={"id": 0, "resposta": "x"}).status_code, 401)
        novo, r = login(b_usuario, SENHA)
        self.assertEqual(r.status_code, 403)
        self.assertIn("desativada", r.get_data(as_text=True))
        self.assertNotIn(b_id, {i["operador_id"] for i in ranking("geral", limite=100000)})

        post_form(s, f"/supervisor/operadores/{b_id}/ativo", {"ativo": "1"})
        self.assertEqual(login(b_usuario, SENHA)[1].status_code, 302)
        self.assertIn(b_id, {i["operador_id"] for i in ranking("geral", limite=100000)})

    def test_detalhe_do_operador(self):
        s, _, _ = supervisor()
        b, b_id, _ = cliente_logado(nome="Detalhe Aqui")
        completar_simulacao(b, b_id)
        b.post("/finalizar")
        html = s.get(f"/supervisor/operadores/{b_id}").get_data(as_text=True)
        self.assertIn("Detalhe Aqui", html)
        self.assertIn("Ver atendimentos", html)


class ExportacaoCsv(unittest.TestCase):
    def test_csv_com_dados_e_protecao_contra_formulas(self):
        s, _, _ = supervisor()
        b, b_id, b_usuario = cliente_logado(nome="=HYPERLINK(\"http://x\")")
        completar_simulacao(b, b_id)
        b.post("/finalizar")

        r = s.get("/supervisor/exportar.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["Content-Type"])
        self.assertIn("attachment", r.headers["Content-Disposition"])
        texto = r.get_data(as_text=True)
        self.assertTrue(texto.startswith("\ufeff"))

        linhas = list(csv.reader(io.StringIO(texto.lstrip("\ufeff"))))
        self.assertEqual(linhas[0][:4], ["finalizada_em_utc", "usuario", "nome", "modo"])
        do_operador = [l for l in linhas[1:] if l[1] == b_usuario]
        self.assertEqual(len(do_operador), 1)
        self.assertTrue(do_operador[0][2].startswith("'="))  # nome com fórmula foi neutralizado
        self.assertIn("exportou o CSV de simulações", [a["acao"] for a in listar_auditoria(50)])


if __name__ == "__main__":
    unittest.main()
