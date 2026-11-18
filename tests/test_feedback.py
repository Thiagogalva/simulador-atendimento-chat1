import unittest
from unittest import mock

from data.base_atendimentos import BASE_ATENDIMENTOS
from services import feedback_service
from tests.helpers import cliente_logado, completar_simulacao, iniciar

PASSO0 = BASE_ATENDIMENTOS[0]["fluxo"][0]
PASSO1 = BASE_ATENDIMENTOS[0]["fluxo"][1]
CRITICAS = ["análise", "prazo"]
RESPOSTA_RUIM = "Hoje o dia está bonito e vamos almoçar mais tarde, tudo bem com você."


def av(coerencia, empatia=10, erros=0, avisos=()):
    return {"coerencia": coerencia, "empatia": empatia, "erros": erros, "tempo": 20, "avisos": list(avisos)}


def detalhe(id_, titulo, nota, avisos=(), status="Finalizado"):
    return {"id": id_, "titulo": titulo, "nota": nota, "nivel": "x", "coerencia": nota, "empatia": 10.0,
            "tempo": 20.0, "erros": 0, "status": status, "avisos": list(avisos)}


def simulacao(detalhes, nota=80.0, modo="avaliacao", coerencia=80.0, empatia=12.0, tempo=16.0, erros=0):
    return {"nota_geral": nota, "nivel": "Avançado", "modo": modo, "media_coerencia": coerencia,
            "media_empatia": empatia, "media_tempo": tempo, "total_erros": erros, "detalhes": detalhes}


class FeedbackDaResposta(unittest.TestCase):
    def gerar(self, coerencia, resposta, **kw):
        return feedback_service.feedback_resposta(
            av(coerencia, **kw), resposta, PASSO0["resposta_esperada"], CRITICAS)["texto"]

    def test_resposta_perfeita(self):
        texto = self.gerar(100, PASSO0["resposta_esperada"])
        self.assertIn("Excelente", texto)
        self.assertNotIn("Faltou", texto)
        self.assertIn("acolhimento ficou bom", texto)

    def test_resposta_distante_aponta_o_que_faltou(self):
        texto = self.gerar(10, RESPOSTA_RUIM, empatia=0)
        self.assertIn("distante", texto)
        self.assertIn("Faltou mencionar", texto)
        self.assertIn("reconheça a situação", texto)   # estrutura: faltou acolher

    def test_resposta_parcial_mostra_o_que_foi_coberto_e_o_que_falta(self):
        texto = self.gerar(60, "Entendo a situação, vou verificar a análise para você.")
        self.assertIn("parcial", texto)
        self.assertIn("Você abordou", texto)
        self.assertIn("Faltou mencionar", texto)

    def test_sinonimo_conta_como_coberto(self):
        texto = self.gerar(80, "Entendo a situação. Vou verificar o período previsto e o andamento da análise.")
        faltou = texto.split("Faltou mencionar:")[1].split(".")[0] if "Faltou mencionar:" in texto else ""
        self.assertNotIn("prazo", faltou)  # "período" cobre "prazo"

    def test_nao_elogia_o_que_so_parece_parecido(self):
        texto = self.gerar(75, "Entendo seu caso. Vou conferir como anda a verificação e te informar o período estimado de retorno.")
        elogio = texto.split("Você abordou:")[1].split(".")[0] if "Você abordou:" in texto else ""
        self.assertNotIn("contestação", elogio)
        self.assertNotIn("estorno", elogio)

    def test_palavras_de_tom_nao_viram_ideias_do_conteudo(self):
        texto = self.gerar(75, "Entendo seu caso. Vou conferir como anda a verificação e te informar o período estimado de retorno.")
        for trecho in ("Você abordou:", "Faltou mencionar:"):
            if trecho in texto:
                lista = texto.split(trecho)[1].split(".")[0]
                for palavra_de_tom in ("entendo", "lamento", "obrigad"):
                    self.assertNotIn(palavra_de_tom, lista.lower())

    def test_ortografia_e_avisos(self):
        texto = self.gerar(80, "teste", erros=2, avisos=["Finalize a frase com ponto, interrogação ou exclamação."])
        self.assertIn("Revise a ortografia", texto)
        self.assertIn("Finalize a frase", texto)

    def test_e_deterministico(self):
        self.assertEqual(self.gerar(40, RESPOSTA_RUIM), self.gerar(40, RESPOSTA_RUIM))


class FeedbackFinal(unittest.TestCase):
    D = [detalhe(0, "Cartão", 90), detalhe(1, "Estorno", 55, avisos=["Resposta repetida."])]

    def texto(self, sim, anterior=None):
        return feedback_service.feedback_final(sim, anterior)["texto"]

    def test_conteudo_basico(self):
        t = self.texto(simulacao(self.D, nota=72.5))
        self.assertIn("Nota geral 72.5", t)
        self.assertIn("Melhor atendimento: Cartão", t)
        self.assertIn("Mais difícil: Estorno", t)
        self.assertIn("Aviso mais frequente: Resposta repetida.", t)
        self.assertIn("Próximo passo", t)
        self.assertIn("Refaça \"Estorno\" no modo treino", t)

    def test_comparacao_com_a_simulacao_anterior(self):
        self.assertIn("subiu 10.0 pontos", self.texto(simulacao(self.D, nota=80.0), {"nota_geral": 70.0}))
        self.assertIn("caiu 5.0 pontos", self.texto(simulacao(self.D, nota=65.0), {"nota_geral": 70.0}))
        self.assertIn("estável", self.texto(simulacao(self.D, nota=70.2), {"nota_geral": 70.0}))
        self.assertNotIn("anterior", self.texto(simulacao(self.D)))

    def test_aponta_a_dimensao_mais_fraca(self):
        fraca_em_empatia = simulacao(self.D, coerencia=95.0, empatia=2.0, tempo=19.0)
        t = self.texto(fraca_em_empatia)
        self.assertIn("o que mais pode melhorar é empatia e acolhimento", t)
        self.assertIn("reconhecendo a situação do cliente", t)

    def test_no_treino_o_tempo_nao_conta(self):
        t = self.texto(simulacao(self.D, modo="treino", coerencia=90.0, empatia=16.0, tempo=0.0))
        self.assertNotIn("rapidez", t.split("pode melhorar é")[1].split(".")[0])
        self.assertIn("faça uma avaliação", t)

    def test_cliente_que_desistiu(self):
        d = [detalhe(0, "Cartão", 20, status="Encerrado pelo cliente")]
        self.assertIn("cliente desistiu", self.texto(simulacao(d, nota=20.0)))

    def test_sem_atendimentos(self):
        self.assertIn("Não há atendimentos", self.texto(simulacao([])))


class EndpointsDeFeedback(unittest.TestCase):
    def setUp(self):
        self.c, self.operador_id, _ = cliente_logado()
        iniciar(self.c, "treino")

    def _feedback(self, id_=0):
        return self.c.post("/feedback", json={"id": id_})

    def test_exige_login_e_id_valido(self):
        import app as aplicacao
        self.assertEqual(aplicacao.app.test_client().post("/feedback", json={"id": 0}).status_code, 401)
        self.assertEqual(self.c.post("/feedback", json={}).status_code, 400)
        self.assertEqual(self.c.post("/feedback", json={"id": 99}).status_code, 400)

    def test_antes_de_responder_nao_ha_o_que_comentar(self):
        self.assertEqual(self._feedback().status_code, 409)

    def test_bloqueado_na_avaliacao(self):
        c, _, _ = cliente_logado()
        iniciar(c, "avaliacao")
        c.post("/responder", json={"id": 0, "resposta": RESPOSTA_RUIM})
        self.assertEqual(c.post("/feedback", json={"id": 0}).status_code, 403)

    def test_feedback_gerado_e_guardado_em_cache(self):
        self.c.post("/responder", json={"id": 0, "resposta": RESPOSTA_RUIM})
        with mock.patch.object(feedback_service, "feedback_resposta", wraps=feedback_service.feedback_resposta) as gerar:
            import app as aplicacao
            with mock.patch.object(aplicacao, "feedback_resposta", gerar):
                primeiro = self._feedback().get_json()
                segundo = self._feedback().get_json()
        self.assertEqual((primeiro["origem"], primeiro["em_cache"]), ("analise", False))
        self.assertIn("Faltou mencionar", primeiro["texto"])
        self.assertEqual((segundo["em_cache"], segundo["texto"]), (True, primeiro["texto"]))
        self.assertEqual(gerar.call_count, 1)  # a segunda chamada veio do cache

    def test_usa_o_passo_da_resposta_mesmo_depois_de_avancar(self):
        self.c.post("/responder", json={"id": 0, "resposta": PASSO0["resposta_esperada"]})  # avança para o passo 1
        import app as aplicacao
        with mock.patch.object(aplicacao, "feedback_resposta", wraps=feedback_service.feedback_resposta) as gerar:
            self._feedback()
        _, _, esperada, _ = gerar.call_args.args
        self.assertEqual(esperada, PASSO0["resposta_esperada"])
        self.assertNotEqual(esperada, PASSO1["resposta_esperada"])

    def test_responder_nao_gera_feedback(self):
        import app as aplicacao
        with mock.patch.object(aplicacao, "feedback_resposta") as gerar:
            self.c.post("/responder", json={"id": 0, "resposta": RESPOSTA_RUIM})
        gerar.assert_not_called()

    def test_nada_sai_para_a_internet(self):
        """O feedback roda todo dentro do sistema: nenhuma conexão HTTP é aberta."""
        self.c.post("/responder", json={"id": 0, "resposta": RESPOSTA_RUIM})
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("rede!")), \
                mock.patch("http.client.HTTPConnection.connect", side_effect=AssertionError("rede!")), \
                mock.patch("http.client.HTTPSConnection.connect", side_effect=AssertionError("rede!")):
            self.assertEqual(self._feedback().status_code, 200)
            self.assertEqual(self.c.get("/historico").status_code, 200)


class FeedbackFinalNaApi(unittest.TestCase):
    def _concluir(self, c, operador_id, modo="avaliacao"):
        completar_simulacao(c, operador_id, modo=modo)
        return c.post("/finalizar").get_json()

    def test_feedback_final_salvo_e_exibido_no_historico(self):
        c, oid, _ = cliente_logado()
        fin = self._concluir(c, oid)
        r = c.post("/feedback-final", json={"id": fin["id"]}).get_json()
        self.assertEqual((r["origem"], r["em_cache"]), ("analise", False))
        self.assertIn("Nota geral", r["texto"])
        again = c.post("/feedback-final", json={"id": fin["id"]}).get_json()
        self.assertEqual((again["em_cache"], again["texto"]), (True, r["texto"]))
        pagina = c.get("/historico").get_data(as_text=True)
        self.assertIn("Análise automática", pagina)
        self.assertIn("Nota geral", pagina)

    def test_compara_com_a_simulacao_anterior_do_mesmo_modo(self):
        c, oid, _ = cliente_logado()
        primeira = self._concluir(c, oid)
        c.post("/feedback-final", json={"id": primeira["id"]})
        segunda = self._concluir(c, oid)
        texto = c.post("/feedback-final", json={"id": segunda["id"]}).get_json()["texto"]
        self.assertIn("simulação anterior", texto)

    def test_treino_nao_e_comparado_com_avaliacao(self):
        c, oid, _ = cliente_logado()
        avaliacao = self._concluir(c, oid, "avaliacao")
        c.post("/feedback-final", json={"id": avaliacao["id"]})
        treino = self._concluir(c, oid, "treino")
        texto = c.post("/feedback-final", json={"id": treino["id"]}).get_json()["texto"]
        self.assertNotIn("simulação anterior", texto)

    def test_isolamento_e_validacao(self):
        c, oid, _ = cliente_logado()
        fin = self._concluir(c, oid)
        outro, _, _ = cliente_logado()
        self.assertEqual(outro.post("/feedback-final", json={"id": fin["id"]}).status_code, 404)
        self.assertEqual(c.post("/feedback-final", json={"id": "abc"}).status_code, 400)
        self.assertEqual(c.post("/feedback-final", json={}).status_code, 400)
        import app as aplicacao
        self.assertEqual(aplicacao.app.test_client().post("/feedback-final", json={"id": 1}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
