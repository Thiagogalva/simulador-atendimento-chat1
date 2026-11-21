import json
import re
import unittest
import uuid
from unittest import mock

import config
from data.base_atendimentos import BASE_ATENDIMENTOS
from repositories.cenario_repository import (
    buscar_cenario,
    contar_ativos,
    definir_ativo_cenario,
    listar_cenarios,
)
from repositories.operador_repository import listar_auditoria
from services.texto_service import PALAVRAS_CRITICAS
from tests.helpers import apagar_cenario, cliente_logado, iniciar, post_form, tornar_supervisor

CLIENTE_1 = "Oi, minha tokenizacao de cartao falhou no aplicativo hoje."
RESPOSTA_1 = "Entendo a situação. Vou verificar a tokenizacao do seu cartao e retorno com o prazo de solução."
CLIENTE_2 = "Certo, mas quanto tempo isso leva para ficar pronto?"
RESPOSTA_2 = "O prazo previsto para a conclusão da tokenizacao é de até dois dias úteis."


def titulo_unico():
    return "Cenário de teste " + uuid.uuid4().hex[:8]


def supervisor():
    c, oid, _ = cliente_logado(nome="Chefe Cenarios")
    tornar_supervisor(c)
    return c, oid


def dados_cenario(titulo=None, **mudancas):
    dados = {
        "titulo": titulo or titulo_unico(),
        "ordem": "9000",
        "palavras": "tokenizacao, prazo",
        "cliente": [CLIENTE_1, CLIENTE_2],
        "resposta": [RESPOSTA_1, RESPOSTA_2],
    }
    dados.update(mudancas)
    return dados


def criar_via_formulario(cliente, test, **mudancas):
    dados = dados_cenario(**mudancas)
    r = post_form(cliente, "/supervisor/cenarios/novo", dados)
    test.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:600])
    criado = next(c for c in listar_cenarios() if c["titulo"] == dados["titulo"])
    test.addCleanup(apagar_cenario, criado["id"])
    return criado


class CenariosIniciais(unittest.TestCase):
    def test_cenarios_base_foram_carregados_no_banco(self):
        base = [c for c in listar_cenarios() if c["id"] <= len(BASE_ATENDIMENTOS)]
        self.assertEqual([c["titulo"] for c in base], [b["titulo"] for b in BASE_ATENDIMENTOS])
        for cenario, original in zip(base, BASE_ATENDIMENTOS):
            self.assertEqual(cenario["fluxo"], original["fluxo"])
            self.assertEqual(cenario["palavras_criticas"], PALAVRAS_CRITICAS[original["titulo"].lower()])
            self.assertTrue(cenario["ativo"])


class Permissoes(unittest.TestCase):
    def test_operador_comum_nao_acessa(self):
        c, _, _ = cliente_logado()
        for caminho in ("/supervisor/cenarios", "/supervisor/cenarios/novo", "/supervisor/cenarios/1"):
            r = c.get(caminho)  # sem o código do supervisor: vai para a tela de entrada
            self.assertEqual(r.status_code, 302, caminho)
            self.assertIn("/supervisor/entrar", r.headers["Location"])
        self.assertEqual(post_form(c, "/supervisor/cenarios/novo", dados_cenario()).status_code, 403)
        self.assertEqual(post_form(c, "/supervisor/cenarios/1/ativo", {"ativo": "0"}).status_code, 403)
        self.assertTrue(buscar_cenario(1)["ativo"])

    def test_formulario_exige_csrf(self):
        s, _ = supervisor()
        antes = len(listar_cenarios())
        self.assertEqual(s.post("/supervisor/cenarios/novo", data=dados_cenario()).status_code, 400)
        self.assertEqual(len(listar_cenarios()), antes)

    def test_cenario_inexistente_da_404(self):
        s, _ = supervisor()
        self.assertEqual(s.get("/supervisor/cenarios/99999999").status_code, 404)
        self.assertEqual(post_form(s, "/supervisor/cenarios/99999999/ativo", {"ativo": "0"}).status_code, 404)


class CriarEEditar(unittest.TestCase):
    def setUp(self):
        self.s, self.sid = supervisor()

    def test_cenario_novo_entra_nas_proximas_simulacoes(self):
        criado = self.criar()
        self.assertTrue(criado["ativo"])
        self.assertEqual(criado["palavras_criticas"], ["tokenizacao", "prazo"])
        self.assertIn(criado["titulo"], self.s.get("/supervisor/cenarios").get_data(as_text=True))

        iniciar(self.s, "treino")
        pagina = self.s.get("/simulacao").get_data(as_text=True)
        dados = json.loads(re.search(r"let dados = (.*?);\nlet atual", pagina, re.S).group(1))
        self.assertEqual(len(dados), len(BASE_ATENDIMENTOS) + 1)
        self.assertEqual(dados[-1]["titulo"], criado["titulo"])
        self.assertEqual(dados[-1]["mensagens"][0]["texto"], CLIENTE_1)

        # responde com a resposta esperada do cenário novo: coerência máxima
        novo_id = dados[-1]["id"]
        r = self.s.post("/responder", json={"id": novo_id, "resposta": RESPOSTA_1}).get_json()
        self.assertEqual(r["media_coerencia"], 100)

    def test_vocabulario_do_cenario_nao_gera_erro_ortografico(self):
        self.criar()
        iniciar(self.s, "treino")
        # "tokenizacao" não existe no dicionário; só é aceita porque faz parte do cenário
        r = self.s.post("/responder", json={"id": len(BASE_ATENDIMENTOS), "resposta": RESPOSTA_1}).get_json()
        self.assertEqual(r["erros"], 0, r["avisos"])
        # em um cenário que não usa a palavra, ela continua sendo erro
        r = self.s.post("/responder", json={"id": 0, "resposta": "Entendo, vou verificar a tokenizacao agora."}).get_json()
        self.assertGreaterEqual(r["erros"], 1)

    def test_editar_nao_altera_simulacao_em_andamento(self):
        criado = self.criar()
        iniciar(self.s, "treino")
        novo_titulo = titulo_unico()
        r = post_form(self.s, f"/supervisor/cenarios/{criado['id']}", dados_cenario(titulo=novo_titulo))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(buscar_cenario(criado["id"])["titulo"], novo_titulo)

        em_andamento = self.s.get("/simulacao").get_data(as_text=True)
        self.assertIn(criado["titulo"], em_andamento)       # snapshot: continua o título antigo
        self.assertNotIn(novo_titulo, em_andamento)
        iniciar(self.s, "treino")                           # nova simulação já usa a edição
        self.assertIn(novo_titulo, self.s.get("/simulacao").get_data(as_text=True))

    def test_formulario_de_edicao_traz_os_dados(self):
        criado = self.criar()
        html = self.s.get(f"/supervisor/cenarios/{criado['id']}").get_data(as_text=True)
        self.assertIn(criado["titulo"], html)
        self.assertIn(CLIENTE_1, html)
        self.assertIn("tokenizacao, prazo", html)

    def test_validacoes_nao_salvam_e_preservam_o_que_foi_digitado(self):
        antes = len(listar_cenarios())
        casos = {
            "titulo vazio": dados_cenario(titulo=" "),
            "sem passos": dados_cenario(cliente=["", ""], resposta=["", ""]),
            "passo incompleto": dados_cenario(cliente=[CLIENTE_1], resposta=[""]),
            "fala curta": dados_cenario(cliente=["oi"], resposta=[RESPOSTA_1]),
            "resposta curta": dados_cenario(cliente=[CLIENTE_1], resposta=["ok"]),
            "ordem invalida": dados_cenario(ordem="abc"),
            "passos demais": dados_cenario(cliente=[CLIENTE_1] * 13, resposta=[RESPOSTA_1] * 13),
            "palavras demais": dados_cenario(palavras=",".join(f"palavra{i}" for i in range(11))),
        }
        for nome, dados in casos.items():
            r = post_form(self.s, "/supervisor/cenarios/novo", dados)
            self.assertEqual(r.status_code, 400, nome)
            self.assertIn("alerta-erro", r.get_data(as_text=True), nome)
        self.assertEqual(len(listar_cenarios()), antes)

        r = post_form(self.s, "/supervisor/cenarios/novo", dados_cenario(titulo="Meu título", ordem="abc"))
        self.assertIn("Meu título", r.get_data(as_text=True))  # o formulário mantém o que foi digitado

    def test_avisos_nao_bloqueiam(self):
        titulo = titulo_unico()
        r = post_form(self.s, "/supervisor/cenarios/novo",
                      dados_cenario(titulo=titulo, palavras="palavraausente"), follow_redirects=True)
        criado = next(c for c in listar_cenarios() if c["titulo"] == titulo)
        self.addCleanup(apagar_cenario, criado["id"])
        self.assertEqual(r.status_code, 200)
        self.assertIn("não aparece em nenhuma resposta esperada", r.get_data(as_text=True))

    def test_titulo_com_html_e_escapado(self):
        malicioso = "<script>alert(1)</script> " + uuid.uuid4().hex[:6]
        criado = self.criar(titulo=malicioso)
        lista = self.s.get("/supervisor/cenarios").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", lista)
        iniciar(self.s, "treino")
        chat = self.s.get("/simulacao").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", chat)
        self.assertIn("alert(1)", chat)  # presente apenas como dado escapado

    def test_auditoria_registra_criacao_edicao_e_arquivamento(self):
        criado = self.criar()
        post_form(self.s, f"/supervisor/cenarios/{criado['id']}", dados_cenario(titulo=criado["titulo"]))
        post_form(self.s, f"/supervisor/cenarios/{criado['id']}/ativo", {"ativo": "0"})
        acoes = " | ".join(a["acao"] for a in listar_auditoria(30))
        self.assertIn(f'criou o cenário "{criado["titulo"]}"', acoes)
        self.assertIn(f'editou o cenário "{criado["titulo"]}"', acoes)
        self.assertIn(f'arquivou o cenário "{criado["titulo"]}"', acoes)

    def criar(self, **mudancas):
        return criar_via_formulario(self.s, self, **mudancas)


class AtivacaoESorteio(unittest.TestCase):
    def setUp(self):
        self.s, self.sid = supervisor()

    def _ids_da_nova_simulacao(self):
        iniciar(self.s, "treino")
        pagina = self.s.get("/simulacao").get_data(as_text=True)
        return [d["titulo"] for d in json.loads(re.search(r"let dados = (.*?);\nlet atual", pagina, re.S).group(1))]

    def test_arquivado_sai_das_simulacoes_e_volta_ao_reativar(self):
        criado = criar_via_formulario(self.s, self)
        self.assertIn(criado["titulo"], self._ids_da_nova_simulacao())

        post_form(self.s, f"/supervisor/cenarios/{criado['id']}/ativo", {"ativo": "0"})
        self.assertNotIn(criado["titulo"], self._ids_da_nova_simulacao())

        post_form(self.s, f"/supervisor/cenarios/{criado['id']}/ativo", {"ativo": "1"})
        self.assertIn(criado["titulo"], self._ids_da_nova_simulacao())

    def test_nao_permite_arquivar_o_ultimo_ativo(self):
        ativos = [c["id"] for c in listar_cenarios(apenas_ativos=True)]
        try:
            for cid in ativos[:-1]:
                definir_ativo_cenario(cid, False)
            self.assertEqual(contar_ativos(), 1)
            r = post_form(self.s, f"/supervisor/cenarios/{ativos[-1]}/ativo", {"ativo": "0"}, follow_redirects=True)
            self.assertIn("pelo menos um cenário ativo", r.get_data(as_text=True))
            self.assertEqual(contar_ativos(), 1)
        finally:
            for cid in ativos:
                definir_ativo_cenario(cid, True)

    def test_sem_cenarios_ativos_nao_inicia_simulacao(self):
        ativos = [c["id"] for c in listar_cenarios(apenas_ativos=True)]
        try:
            for cid in ativos:
                definir_ativo_cenario(cid, False)
            c, _, _ = cliente_logado()
            r = post_form(c, "/iniciar", {"modo": "treino"})
            self.assertEqual(r.status_code, 503)
            self.assertIn("Não há cenários ativos", r.get_data(as_text=True))
            self.assertEqual(c.get("/simulacao").status_code, 302)
        finally:
            for cid in ativos:
                definir_ativo_cenario(cid, True)

    def test_sorteio_limita_a_quantidade_e_mantem_a_ordem(self):
        with mock.patch.object(config, "CENARIOS_POR_SIMULACAO", 2):
            for _ in range(5):
                titulos = self._ids_da_nova_simulacao()
                self.assertEqual(len(titulos), 2)
                ordem = {c["titulo"]: (c["ordem"], c["id"]) for c in listar_cenarios()}
                self.assertEqual(titulos, sorted(titulos, key=lambda t: ordem[t]))

    def test_sorteio_maior_que_o_total_usa_todos(self):
        with mock.patch.object(config, "CENARIOS_POR_SIMULACAO", 50):
            self.assertEqual(len(self._ids_da_nova_simulacao()), len(listar_cenarios(apenas_ativos=True)))


if __name__ == "__main__":
    unittest.main()
