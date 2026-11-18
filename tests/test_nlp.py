import os
import unittest

from services import nlp_service
from services.avaliacao_service import fracao_palavras_criticas
from services.semantica_service import (
    classificar_ideias,
    conceitos_e_lemas,
    ideias_cobertas,
    palavra_coberta,
    palavras_chave,
    similaridade,
)

E1 = "Entendo a sua situação. Vou te explicar como está o andamento da análise e o prazo previsto para retorno."


@unittest.skipUnless(nlp_service.disponivel(), "spaCy/modelo pt_core_news_md não instalados (requirements-nlp.txt)")
class CamadaSpacy(unittest.TestCase):
    def test_creditos_de_vetores(self):
        self.assertGreaterEqual(nlp_service.credito_vetorial("conferir", "verificar"), 0.5)
        self.assertGreaterEqual(nlp_service.credito_vetorial("estorno", "devolução"), 0.5)
        self.assertEqual(nlp_service.credito_vetorial("almoçar", "análise"), 0.0)
        self.assertEqual(nlp_service.credito_vetorial("futebol", "estorno"), 0.0)
        self.assertEqual(nlp_service.credito_vetorial("xqzwk", "prazo"), 0.0)  # sem vetor

    def test_sinonimos_fora_da_lista_sao_reconhecidos(self):
        resposta = "Entendo seu caso. Vou conferir como anda a verificação e te informar o prazo de retorno."
        self.assertGreaterEqual(similaridade(resposta, E1), 0.75)

    def test_resposta_parcial_nao_e_inflada(self):
        self.assertLess(similaridade("Entendo a situação, vou verificar para você.", E1), 0.6)

    def test_fora_de_contexto_continua_baixo(self):
        self.assertLess(similaridade("Hoje o dia está bonito e vamos almoçar mais tarde, tudo bem com você.", E1), 0.1)

    def test_uma_palavra_nao_cobre_varios_conceitos(self):
        # "verificar" é próximo de "análise", "andamento"... mas só pode cobrir um deles
        com_spacy = similaridade("verificar verificar verificar verificar", E1)
        self.assertLess(com_spacy, 0.4)
        os.environ["NLP_DESATIVAR"] = "1"
        nlp_service.reiniciar()
        try:
            sem_spacy = similaridade("verificar verificar verificar verificar", E1)
        finally:
            os.environ.pop("NLP_DESATIVAR", None)
            nlp_service.reiniciar()
        self.assertAlmostEqual(com_spacy, sem_spacy, delta=0.05)  # os vetores não inflaram o resultado

    def test_palavra_coberta_por_sinonimo(self):
        self.assertTrue(palavra_coberta("verificar", "Vou conferir o seu pedido agora"))
        self.assertFalse(palavra_coberta("prazo", "Hoje o dia está bonito"))

    def test_palavras_chave_sao_substantivos_verbos_e_adjetivos(self):
        pistas = palavras_chave("Vou verificar as informações no sistema para te orientar da forma mais clara.", 6)
        self.assertTrue(pistas)
        conteudo = set(nlp_service.palavras_de_conteudo(
            "Vou verificar as informações no sistema para te orientar da forma mais clara."))
        lema = {o: l for o, l, _ in nlp_service.analisar("Vou verificar as informações no sistema para te orientar da forma mais clara.")}
        self.assertTrue(all(lema.get(p) in conteudo for p in pistas), pistas)

    def test_uma_palavra_nao_cumpre_duas_ideias(self):
        # "verificação" é próxima de "análise" e de "contestação", mas só pode cobrir uma delas
        cobertas = ideias_cobertas(["análise", "contestação"], "Vou fazer a verificação agora.")
        self.assertEqual(len(cobertas), 1)

    def test_evidencia_fraca_nao_vira_elogio(self):
        resposta = "Entendo seu caso. Vou conferir como anda a verificação e te informar o período estimado de retorno."
        fortes, fracas = classificar_ideias(["análise", "prazo", "contestação", "estorno"], resposta)
        self.assertIn("análise", fortes)          # "conferir" é sinônimo da lista
        self.assertNotIn("contestação", fortes)   # só parece próxima de "verificação" por vetores
        self.assertNotIn("estorno", fortes | fracas)

    def test_palavras_criticas_aceitam_sinonimo(self):
        esperados = conceitos_e_lemas("O prazo previsto para a análise é de dois dias.")
        com_sinonimo = conceitos_e_lemas("O período estimado para a verificação é de dois dias.")
        sem_relacao = conceitos_e_lemas("Hoje o dia está bonito para almoçar na praia.")
        self.assertEqual(fracao_palavras_criticas(com_sinonimo, esperados, ["prazo", "análise"]), 1.0)
        self.assertEqual(fracao_palavras_criticas(sem_relacao, esperados, ["prazo", "análise"]), 0.0)


class SemSpacy(unittest.TestCase):
    """O motor léxico continua funcionando (e dando o mesmo resultado) com a camada desligada."""

    def setUp(self):
        self._antigo = os.environ.get("NLP_DESATIVAR")
        os.environ["NLP_DESATIVAR"] = "1"
        nlp_service.reiniciar()
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        if self._antigo is None:
            os.environ.pop("NLP_DESATIVAR", None)
        else:
            os.environ["NLP_DESATIVAR"] = self._antigo
        nlp_service.reiniciar()

    def test_desativado(self):
        self.assertFalse(nlp_service.disponivel())
        self.assertEqual(nlp_service.analisar("Vou verificar"), [])
        self.assertEqual(nlp_service.credito_vetorial("conferir", "verificar"), 0.0)

    def test_uma_palavra_nao_cumpre_duas_ideias_no_motor_lexico(self):
        self.assertLessEqual(len(ideias_cobertas(["análise", "contestação"], "Vou fazer a verificação agora.")), 1)

    def test_motor_lexico_segue_funcionando(self):
        self.assertEqual(similaridade(E1, E1), 1.0)
        self.assertLess(similaridade("Hoje o dia está bonito e vamos almoçar mais tarde.", E1), 0.1)
        self.assertGreaterEqual(similaridade("Entendi a situação, estou explicando o andamento da análise "
                                             "e o prazo previsto de retorno.", E1), 0.85)
        self.assertTrue(palavra_coberta("verificar", "Vou conferir o seu pedido"))  # via lista de sinônimos
        self.assertTrue(palavras_chave("Vou verificar as informações no sistema.", 4))


if __name__ == "__main__":
    unittest.main()
