import time
import unittest

from data.base_atendimentos import BASE_ATENDIMENTOS
from services.avaliacao_service import calcular_coerencia
from services.semantica_service import similaridade
from services.texto_service import detectar_erros_linguisticos
from services.tom_service import avaliar_tom

E1 = BASE_ATENDIMENTOS[0]["fluxo"][0]["resposta_esperada"]
E_NEG = BASE_ATENDIMENTOS[1]["fluxo"][3]["resposta_esperada"]


class SimilaridadeSemantica(unittest.TestCase):
    def test_resposta_exata_vale_1(self):
        self.assertEqual(similaridade(E1, E1), 1.0)

    def test_conjugacao_diferente_e_reconhecida(self):
        resp = "Entendi a situação, estou explicando o andamento da análise e o prazo previsto de retorno."
        self.assertGreaterEqual(similaridade(resp, E1), 0.85)

    def test_parafrase_com_sinonimos(self):
        resp = "Compreendo a situação da senhora. Irei esclarecer o andamento da análise e o prazo previsto para o retorno."
        self.assertGreaterEqual(similaridade(resp, E1), 0.7)

    def test_fora_de_contexto_e_baixa(self):
        resp = "Hoje o dia está bonito e vamos almoçar mais tarde, tudo bem com você."
        self.assertLess(similaridade(resp, E1), 0.1)

    def test_parcial_fica_entre_fora_de_contexto_e_exata(self):
        parcial = similaridade("Entendo a situação, vou verificar para você.", E1)
        self.assertTrue(0.2 < parcial < 0.8, parcial)

    def test_negacao_invertida_e_penalizada(self):
        invertida = "Consigo fazer essa liberação manualmente por aqui, a devolução do valor ocorre agora."
        sem_penalidade = "Consigo fazer a liberação manualmente por aqui, a devolução do valor ocorre após a conclusão da análise."
        self.assertLess(similaridade(invertida, E_NEG), 0.6)
        self.assertLess(similaridade(sem_penalidade, E_NEG), 0.75)

    def test_negacao_de_cortesia_nao_penaliza(self):
        a = similaridade("Não se preocupe. " + E1, E1)
        self.assertGreaterEqual(a, 0.9)

    def test_erro_de_digitacao_nao_derruba_nota(self):
        esperada = BASE_ATENDIMENTOS[1]["fluxo"][2]["resposta_esperada"]
        resp = esperada.replace("situação", "situçao")
        self.assertGreaterEqual(similaridade(resp, esperada), 0.9)


class Coerencia(unittest.TestCase):
    def test_resposta_sugerida_vale_100_em_todos_os_passos(self):
        for at in BASE_ATENDIMENTOS:
            for passo in at["fluxo"]:
                nota = calcular_coerencia(
                    passo["resposta_esperada"],
                    {"titulo": at["titulo"], "resposta_esperada": passo["resposta_esperada"]},
                )
                self.assertEqual(nota, 100, passo["resposta_esperada"])

    def test_resposta_ruim_fica_baixa(self):
        at = {"titulo": BASE_ATENDIMENTOS[0]["titulo"], "resposta_esperada": E1}
        self.assertLess(calcular_coerencia("Ok.", at), 20)
        self.assertLess(calcular_coerencia("Hoje o dia está bonito e vamos almoçar mais tarde.", at), 20)


class Tom(unittest.TestCase):
    def test_respostas_esperadas_nao_geram_avisos(self):
        for at in BASE_ATENDIMENTOS:
            for passo in at["fluxo"]:
                _, avisos = avaliar_tom(passo["resposta_esperada"])
                self.assertEqual(avisos, [], passo["resposta_esperada"])

    def test_respostas_esperadas_nao_tem_erros_ortograficos(self):
        for at in BASE_ATENDIMENTOS:
            for passo in at["fluxo"]:
                erros, avisos = detectar_erros_linguisticos(passo["resposta_esperada"])
                self.assertEqual(erros, [], avisos)

    def test_resposta_acolhedora_pontua_alto(self):
        emp, avisos = avaliar_tom(
            "Entendo a sua situação e lamento o transtorno. Vou verificar agora e retorno em até 72 horas, "
            "por gentileza aguarde."
        )
        self.assertEqual(emp, 20)
        self.assertEqual(avisos, [])

    def test_tom_hostil_zera_e_avisa(self):
        emp, avisos = avaliar_tom("Isso não é problema meu, já falei que não tem como.")
        self.assertEqual(emp, 0)
        self.assertGreaterEqual(len(avisos), 2)

    def test_caixa_alta_giria_e_repeticao(self):
        self.assertTrue(avaliar_tom("VOCÊ PRECISA AGUARDAR A ANÁLISE DO BLOQUEIO")[1])
        self.assertTrue(avaliar_tom("Opa, vlw por esperar kkk, vou ver aqui.")[1])
        _, avisos = avaliar_tom("Entendo a sua situação.", ["Entendo a sua situação."])
        self.assertTrue(any("repetida" in a.lower() for a in avisos))

    def test_nao_confunde_substantivo_analise_com_acao(self):
        emp, _ = avaliar_tom("O bloqueio depende de análise.")
        self.assertEqual(emp, 0)


class FluxoCompleto(unittest.TestCase):
    def setUp(self):
        import app as aplicacao
        self.app = aplicacao.app
        self.client = self.app.test_client()
        self.client.get("/")

    def _post(self, i, texto):
        r = self.client.post("/responder", json={"id": i, "resposta": texto})
        return r.status_code, r.get_json()

    def test_fluxo_com_respostas_sugeridas_termina_com_nota_maxima(self):
        with self.client.session_transaction() as s:
            s["simulacao_iniciada_em"] = time.time() - 1000
        from database.connection import get_connection
        conn = get_connection()
        conn.execute("UPDATE atendimentos SET ultimo_tempo_backend=? WHERE id_publico=0", (time.time(),))
        conn.commit()
        conn.close()

        for passo in BASE_ATENDIMENTOS[0]["fluxo"]:
            status, dados = self._post(0, passo["resposta_esperada"])
            self.assertEqual(status, 200, dados)
            self.assertEqual(dados["erros"], 0)
        self.assertTrue(dados["finalizado"])
        self.assertEqual(dados["nota"], 100)

    def test_tom_hostil_aparece_nos_avisos_da_api(self):
        status, dados = self._post(0, "Isso não é problema meu, já falei que não tem como resolver isso.")
        self.assertEqual(status, 200)
        self.assertTrue(any("descaso" in a or "não sei" in a.lower() for a in dados["avisos"]), dados["avisos"])
        self.assertLess(dados["media_empatia"], 5)

    def test_sessao_expirada_retorna_409(self):
        status = self.app.test_client().post(
            "/responder", json={"id": 0, "resposta": "Texto longo o bastante para a validação."}
        ).status_code
        self.assertEqual(status, 409)


if __name__ == "__main__":
    unittest.main()
