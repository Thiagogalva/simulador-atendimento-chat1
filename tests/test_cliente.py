import sqlite3
import unittest

from data.base_atendimentos import BASE_ATENDIMENTOS
from database.init_db import garantir_colunas
from services.cliente_service import (
    LIMITE_ENCERRAMENTO,
    decidir_reacao,
    humor_da_irritacao,
)

FORA_1 = "Hoje o dia está bonito e vamos almoçar mais tarde, tudo bem com você."
FORA_2 = "O jogo de futebol começa às oito horas da noite no estádio da cidade."
FORA_3 = "Amanhã vou viajar para a praia com a minha família durante o feriado."
HOSTIL = "Isso não é problema meu, já falei que não tem como resolver isso agora."

PASSO0 = BASE_ATENDIMENTOS[0]["fluxo"][0]
PASSO1 = BASE_ATENDIMENTOS[0]["fluxo"][1]


def decidir(**kw):
    base = dict(coerencia=90, sinais=set(), qtd_erros=0, tempo_nota=20, palavras=12,
                irritacao=0, tentativas_etapa=0, ultima_etapa=False)
    base.update(kw)
    return decidir_reacao(**base)


class RegrasDoCliente(unittest.TestCase):
    def test_humor_por_faixa(self):
        self.assertEqual(humor_da_irritacao(0), "calmo")
        self.assertEqual(humor_da_irritacao(29), "calmo")
        self.assertEqual(humor_da_irritacao(30), "impaciente")
        self.assertEqual(humor_da_irritacao(60), "atritado")

    def test_resposta_boa_avanca_e_acalma(self):
        d = decidir(irritacao=40)
        self.assertEqual(d["acao"], "avancar")
        self.assertEqual(d["categoria"], "recuperacao")
        self.assertEqual(d["irritacao"], 28)

    def test_fora_de_contexto_repete(self):
        d = decidir(coerencia=10)
        self.assertEqual((d["acao"], d["categoria"], d["irritacao"]), ("repetir", "fora", 25))

    def test_resposta_seca(self):
        self.assertEqual(decidir(coerencia=0, palavras=1)["categoria"], "seca")

    def test_incompleta_avanca_com_comentario(self):
        d = decidir(coerencia=40)
        self.assertEqual((d["acao"], d["categoria"]), ("avancar", "incompleta"))

    def test_tom_hostil_repete_com_irritacao_alta(self):
        d = decidir(sinais={"hostil"})
        self.assertEqual((d["acao"], d["categoria"]), ("repetir", "hostil"))
        self.assertGreaterEqual(d["irritacao"], 30 - 12)

    def test_descaso_avanca_mas_irrita(self):
        d = decidir(sinais={"descaso"})
        self.assertEqual((d["acao"], d["categoria"]), ("avancar", "descaso"))
        self.assertEqual(d["irritacao"], 3)

    def test_encerra_ao_atingir_limite(self):
        d = decidir(coerencia=10, irritacao=LIMITE_ENCERRAMENTO - 10)
        self.assertEqual((d["acao"], d["humor"]), ("encerrar", "encerrado"))

    def test_encerra_apos_tentativas_esgotadas(self):
        self.assertEqual(decidir(coerencia=10, tentativas_etapa=2)["acao"], "encerrar")
        self.assertEqual(decidir(coerencia=10, tentativas_etapa=1)["acao"], "repetir")

    def test_na_despedida_nao_repete(self):
        d = decidir(coerencia=10, ultima_etapa=True)
        self.assertEqual(d["acao"], "avancar")

    def test_irritacao_nunca_sai_de_0_a_100(self):
        self.assertEqual(decidir(irritacao=0)["irritacao"], 0)
        self.assertLessEqual(decidir(coerencia=0, sinais={"hostil", "gritando"}, irritacao=99)["irritacao"], 100)

    def test_primeira_ofensa_nao_encerra_mas_reincidencia_sim(self):
        pior = {"hostil", "cobranca", "descaso", "gritando"}
        primeira = decidir(coerencia=0, sinais=pior, irritacao=0)
        self.assertEqual((primeira["acao"], primeira["irritacao"]), ("repetir", 40))
        self.assertEqual(decidir(coerencia=0, sinais=pior, irritacao=50)["acao"], "encerrar")

    def test_determinismo(self):
        self.assertEqual(decidir(coerencia=10), decidir(coerencia=10))


class MigracaoDeBanco(unittest.TestCase):
    def test_adiciona_colunas_em_banco_antigo(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("CREATE TABLE atendimentos (id INTEGER PRIMARY KEY, etapa_atual INTEGER)")
        cur.execute("CREATE TABLE mensagens (id INTEGER PRIMARY KEY, texto TEXT)")
        garantir_colunas(cur)
        garantir_colunas(cur)  # idempotente
        atendimentos = {r["name"] for r in cur.execute("PRAGMA table_info(atendimentos)")}
        mensagens = {r["name"] for r in cur.execute("PRAGMA table_info(mensagens)")}
        self.assertTrue({"irritacao", "tentativas_etapa", "encerrado_por_cliente"} <= atendimentos)
        self.assertIn("humor", mensagens)


class ClienteReativoNaApi(unittest.TestCase):
    def setUp(self):
        import app as aplicacao
        self.client = aplicacao.app.test_client()
        self.client.get("/")

    def _post(self, texto, i=0):
        r = self.client.post("/responder", json={"id": i, "resposta": texto})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def _ultima_do_cliente(self, dados):
        return [m for m in dados["mensagens"] if m["tipo"] == "cliente"][-1]

    def test_fora_de_contexto_cliente_reage_e_repete_a_pergunta(self):
        d = self._post(FORA_1)
        ultima = self._ultima_do_cliente(d)
        self.assertIn(PASSO0["cliente"], ultima["texto"])      # repete o que perguntou
        self.assertNotEqual(ultima["texto"], PASSO0["cliente"])  # mas reagindo
        self.assertEqual(d["sugestao"], PASSO0["resposta_esperada"])  # continua no mesmo passo
        self.assertEqual(d["irritacao"], 25)
        self.assertFalse(d["finalizado"])
        self.assertEqual(len(d["mensagens"]), 3)

    def test_falhas_seguidas_fazem_o_cliente_desistir(self):
        self._post(FORA_1)
        d = self._post(FORA_2)
        self.assertEqual(d["humor"], "impaciente")
        d = self._post(FORA_3)
        self.assertTrue(d["finalizado"])
        self.assertTrue(d["encerrado_por_cliente"])
        self.assertEqual(d["humor"], "encerrado")
        ultima = self._ultima_do_cliente(d)
        self.assertEqual(ultima["humor"], "encerrado")
        self.assertIn("supervisor", ultima["texto"] + " supervisor")  # mensagem de desistência presente
        self.assertLess(d["nota"], 40)

    def test_tom_hostil_deixa_o_cliente_atritado(self):
        d = self._post(HOSTIL)
        ultima = self._ultima_do_cliente(d)
        self.assertGreaterEqual(d["irritacao"], 30)
        self.assertIn(d["humor"], ("impaciente", "atritado"))
        self.assertIn(PASSO0["cliente"], ultima["texto"])
        self.assertEqual(ultima["humor"], d["humor"])

    def test_resposta_certa_mantem_o_cliente_calmo(self):
        d = self._post(PASSO0["resposta_esperada"])
        ultima = self._ultima_do_cliente(d)
        self.assertEqual(ultima["texto"], PASSO1["cliente"])  # fala do roteiro, sem comentário
        self.assertIsNone(ultima["humor"])
        self.assertEqual((d["irritacao"], d["humor"]), (0, "calmo"))

    def test_cliente_se_acalma_depois_de_resposta_correta(self):
        self._post(FORA_1)
        d = self._post(FORA_2)
        self.assertEqual(d["irritacao"], 50)
        d = self._post(PASSO0["resposta_esperada"])
        ultima = self._ultima_do_cliente(d)
        self.assertEqual(d["irritacao"], 38)
        self.assertTrue(ultima["texto"].endswith(PASSO1["cliente"]))
        self.assertGreater(len(ultima["texto"]), len(PASSO1["cliente"]))  # comentário de alívio
        self.assertEqual(d["sugestao"], PASSO1["resposta_esperada"])  # avançou de etapa


if __name__ == "__main__":
    unittest.main()
