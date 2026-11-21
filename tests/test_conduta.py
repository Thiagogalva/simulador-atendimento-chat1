import json
import re
import unittest

from data.base_atendimentos import BASE_ATENDIMENTOS
from repositories.cenario_repository import buscar_cenario
from services.cliente_service import LIMITE_ENCERRAMENTO, decidir_espera
from services.conduta_service import pedido_de_espera, regras_efetivas
from tests.helpers import cliente_logado, iniciar, post_form, tornar_supervisor
from tests.test_cenarios import criar_via_formulario

PASSO0 = BASE_ATENDIMENTOS[0]["fluxo"][0]
MOMENTO = "Um momento, por favor."
N_SEEDS = len(BASE_ATENDIMENTOS)


class Deteccao(unittest.TestCase):
    def test_pedidos_de_espera(self):
        for texto in ["Um momento, por favor.", "Só um instante, já retorno com a informação.",
                      "Aguarde um minuto, vou verificar.", "Vou verificar. Já te retorno.",
                      "Aguarde só um momentinho!", "Peço que aguarde um instante.", "Retorno em instantes.",
                      "um segundo", "Por favor, um momento.", "Entendo, vou conferir. Um momento!"]:
            self.assertTrue(pedido_de_espera(texto), texto)

    def test_frases_que_nao_sao_pedidos(self):
        for texto in ["No momento o sistema está estável.", "O prazo é de dois dias, aguarde o retorno por e-mail.",
                      "Entendo a sua situação e vou verificar a análise.", "Você tem um minuto de tolerância para pagar?",
                      "Obrigado, aguardo o seu contato.", "Peço que aguarde a conclusão da análise.",
                      "O processo leva um momento de análise interna.", "Preciso de um segundo documento para continuar."]:
            self.assertFalse(pedido_de_espera(texto), texto)

    def test_regras_efetivas(self):
        self.assertEqual(regras_efetivas(None), {"espera": {"ativa": True, "max": 2}})
        self.assertEqual(regras_efetivas({"espera": {"ativa": False, "max": 99}}), {"espera": {"ativa": False, "max": 10}})
        self.assertEqual(regras_efetivas({"espera": {"max": "x"}})["espera"]["max"], 2)
        self.assertEqual(regras_efetivas({"espera": {"max": -3}})["espera"]["max"], 0)
        self.assertEqual(regras_efetivas("lixo"), {"espera": {"ativa": True, "max": 2}})


class ReacaoDoCliente(unittest.TestCase):
    def test_progressao_com_limite_2(self):
        r1 = decidir_espera(1, 2, 0)
        r2 = decidir_espera(2, 2, 0)
        self.assertEqual((r1["acao"], r1["irritacao"]), ("aguardar", 0))
        self.assertEqual((r2["acao"], r2["irritacao"]), ("aguardar", 0))
        self.assertIn("aguard", r1["mensagem"].lower())

        r3 = decidir_espera(3, 2, 0)
        self.assertEqual((r3["acao"], r3["irritacao"]), ("reclamar", 20))
        self.assertIn("3ª vez", r3["mensagem"])

        r4 = decidir_espera(4, 2, r3["irritacao"])
        self.assertEqual((r4["acao"], r4["irritacao"]), ("reclamar", 45))
        self.assertEqual(r4["humor"], "impaciente")

        r5 = decidir_espera(5, 2, r4["irritacao"])
        self.assertEqual((r5["acao"], r5["humor"]), ("encerrar", "encerrado"))
        self.assertGreaterEqual(r5["irritacao"], LIMITE_ENCERRAMENTO)

    def test_limite_zero_reclama_ja_no_primeiro(self):
        self.assertEqual(decidir_espera(1, 0, 0)["acao"], "reclamar")

    def test_cliente_ja_irritado_desiste_antes(self):
        self.assertEqual(decidir_espera(3, 2, 70)["acao"], "encerrar")

    def test_aceitar_espera_nao_muda_a_irritacao(self):
        self.assertEqual(decidir_espera(1, 2, 40)["irritacao"], 40)


class EsperaNaApi(unittest.TestCase):
    def setUp(self):
        self.c, self.oid, _ = cliente_logado()
        iniciar(self.c, "treino")

    def _esperar(self, texto=MOMENTO, i=0):
        r = self.c.post("/responder", json={"id": i, "resposta": texto})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def _ultima_do_cliente(self, d):
        return [m for m in d["mensagens"] if m["tipo"] == "cliente"][-1]

    def test_ate_o_limite_o_cliente_aceita_sem_penalizar(self):
        for n in (1, 2):
            d = self._esperar()
            self.assertEqual((d["pedidos_espera"], d["irritacao"], d["etapa_atual"]), (n, 0, 0))
            self.assertIn("aguard", self._ultima_do_cliente(d)["texto"].lower())
            self.assertNotIn("Não entendi", self._ultima_do_cliente(d)["texto"])  # não é "fora de contexto"
        self.assertEqual(d["media_coerencia"], 0)  # nenhuma avaliação foi criada

    def test_espera_nao_entra_na_nota_e_a_resposta_seguinte_avanca(self):
        self._esperar()
        self._esperar()
        d = self.c.post("/responder", json={"id": 0, "resposta": PASSO0["resposta_esperada"]}).get_json()
        self.assertEqual((d["etapa_atual"], d["media_coerencia"]), (1, 100))  # média só considera respostas reais

    def test_passando_do_limite_o_cliente_reclama_e_depois_desiste(self):
        self._esperar()
        self._esperar()
        d = self._esperar()
        self.assertIn("3ª vez", self._ultima_do_cliente(d)["texto"])
        self.assertEqual(d["irritacao"], 20)
        self.assertEqual(d["etapa_atual"], 0)  # continua esperando uma resposta de verdade

        d = self._esperar()
        self.assertEqual((d["irritacao"], d["humor"]), (45, "impaciente"))
        d = self._esperar()
        self.assertTrue(d["finalizado"] and d["encerrado_por_cliente"])
        self.assertEqual(self._ultima_do_cliente(d)["humor"], "encerrado")

    def test_texto_curto_nao_e_recusado(self):
        self.assertEqual(self._esperar("Um momento.")["pedidos_espera"], 1)
        self.assertEqual(self._esperar("um segundo")["pedidos_espera"], 2)

    def test_resposta_boa_com_pedido_de_espera_e_tratada_como_resposta(self):
        d = self._esperar(PASSO0["resposta_esperada"] + " Só um momento enquanto confirmo.")
        self.assertEqual((d["pedidos_espera"], d["etapa_atual"]), (0, 1))  # resposta real: avançou, não contou

    def test_limite_aparece_no_treino_mas_nao_na_avaliacao(self):
        d = self._esperar()
        self.assertEqual(d["limite_espera"], 2)
        pagina = self.c.get("/simulacao").get_data(as_text=True)
        self.assertEqual(json.loads(re.search(r"let dados = (.*?);\nlet atual", pagina, re.S).group(1))[0]["limite_espera"], 2)

        c, _, _ = cliente_logado()
        iniciar(c, "avaliacao")
        d = c.post("/responder", json={"id": 0, "resposta": MOMENTO}).get_json()
        self.assertEqual(d["pedidos_espera"], 1)
        self.assertNotIn("limite_espera", d)
        pagina = c.get("/simulacao").get_data(as_text=True)
        dados_da_pagina = json.loads(re.search(r"let dados = (.*?);\nlet atual", pagina, re.S).group(1))
        for atendimento in dados_da_pagina:  # os DADOS enviados não carregam o limite nem as regras
            self.assertNotIn("limite_espera", atendimento)
            self.assertNotIn("regras", atendimento)
        self.assertEqual(dados_da_pagina[0]["pedidos_espera"], 1)

    def test_avaliacao_tambem_penaliza_excesso(self):
        c, _, _ = cliente_logado()
        iniciar(c, "avaliacao")
        for _ in range(5):
            d = c.post("/responder", json={"id": 0, "resposta": MOMENTO}).get_json()
        self.assertTrue(d["encerrado_por_cliente"])

    def test_isolado_por_atendimento(self):
        self._esperar(i=0)
        self._esperar(i=0)
        self._esperar(i=0)  # estoura no atendimento 0
        d = self._esperar(i=1)  # no atendimento 1 a contagem é outra
        self.assertEqual((d["pedidos_espera"], d["irritacao"]), (1, 0))


class RegraPorCenario(unittest.TestCase):
    def setUp(self):
        self.s, self.sid, _ = cliente_logado(nome="Chefe Conduta")
        tornar_supervisor(self.s)

    def _novo(self, **mudancas):
        return criar_via_formulario(self.s, self, **mudancas)

    def _esperar(self, texto=MOMENTO):
        r = self.s.post("/responder", json={"id": N_SEEDS, "resposta": texto})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def test_limite_configurado_no_formulario(self):
        criado = self._novo(espera_ativa="1", espera_max="1")
        self.assertEqual(buscar_cenario(criado["id"])["regras"], {"espera": {"ativa": True, "max": 1}})
        iniciar(self.s, "treino")
        self.assertEqual(self._esperar()["irritacao"], 0)       # 1º pedido: aceita
        d = self._esperar()
        self.assertEqual(d["irritacao"], 20)                    # 2º já passa do limite de 1
        self.assertEqual(d["limite_espera"], 1)

    def test_regra_desativada_mantem_o_comportamento_antigo(self):
        self._novo()  # checkbox ausente = regra desligada
        iniciar(self.s, "treino")
        d = self._esperar()
        self.assertEqual(d["pedidos_espera"], 0)
        self.assertEqual(d["irritacao"], 25)                    # tratado como resposta fora de contexto
        self.assertNotIn("limite_espera", d)

    def test_valores_invalidos_sao_recusados_e_branco_usa_o_padrao(self):
        for ruim in ("abc", "11", "-1"):
            r = post_form(self.s, "/supervisor/cenarios/novo", {
                "titulo": "Teste regra inválida", "ordem": "9100", "palavras": "",
                "cliente": ["Olá, preciso de ajuda com a minha conta."], "resposta": ["Claro, vou verificar a sua conta agora."],
                "espera_ativa": "1", "espera_max": ruim})
            self.assertEqual(r.status_code, 400, ruim)
        criado = self._novo(espera_ativa="1", espera_max="")
        self.assertEqual(buscar_cenario(criado["id"])["regras"]["espera"]["max"], 2)

    def test_formulario_de_edicao_mostra_a_regra(self):
        criado = self._novo(espera_ativa="1", espera_max="4")
        html = self.s.get(f"/supervisor/cenarios/{criado['id']}").get_data(as_text=True)
        self.assertRegex(html, r'name="espera_max"[^>]*value="4"')
        self.assertRegex(html, r'name="espera_ativa" value="1" checked')

    def test_editar_nao_muda_simulacao_em_andamento(self):
        criado = self._novo(espera_ativa="1", espera_max="1")
        iniciar(self.s, "treino")
        from tests.test_cenarios import dados_cenario
        post_form(self.s, f"/supervisor/cenarios/{criado['id']}",
                  dados_cenario(titulo=criado["titulo"], espera_ativa="1", espera_max="9"))
        self.assertEqual(buscar_cenario(criado["id"])["regras"]["espera"]["max"], 9)
        self._esperar()
        self.assertEqual(self._esperar()["irritacao"], 20)      # a simulação em andamento ainda usa o limite 1


class ResumoEFeedback(unittest.TestCase):
    def test_excesso_de_espera_aparece_no_historico_e_no_feedback(self):
        c, oid, _ = cliente_logado()
        iniciar(c, "treino")
        for _ in range(3):
            c.post("/responder", json={"id": 0, "resposta": MOMENTO})
        for at in BASE_ATENDIMENTOS:
            for passo in at["fluxo"]:
                r = c.post("/responder", json={"id": at["id"], "resposta": passo["resposta_esperada"]})
                self.assertEqual(r.status_code, 200)
                if r.get_json()["finalizado"]:
                    break
        fin = c.post("/finalizar").get_json()
        texto = c.post("/feedback-final", json={"id": fin["id"]}).get_json()["texto"]
        self.assertIn("pediu espera 3 vezes", texto)
        self.assertIn("tolera até 2", texto)
        self.assertIn("pedidos de espera 3", c.get("/historico").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
