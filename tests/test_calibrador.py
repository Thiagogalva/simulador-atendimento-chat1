import unittest
from services.calibrador_service import (
    extrair_ancoras,
    avaliar_resposta_processo,
    simular_reacao_especialista,
)


class TestCalibradorService(unittest.TestCase):
    def test_extrair_ancoras_multiplas_respostas(self):
        respostas = [
            "Olá, compreendo a sua situação. Por segurança, confirme seu CPF e nome completo.",
            "Boa tarde, entendo a situação. Para sua segurança, me informe seu CPF e nome.",
        ]
        ancoras = extrair_ancoras(respostas)
        # Deve identificar conceitos comuns como situacao/compreensao, seguranca, cpf, nome
        self.assertTrue(len(ancoras) > 0)
        # Pelo menos radicais de seguranca ou cpf ou situacao devem estar presentes
        tem_relevante = any("segur" in a or "cpf" in a or "situac" in a or "nom" in a for a in ancoras)
        self.assertTrue(tem_relevante, f"Âncoras extraídas: {ancoras}")

    def test_avaliar_desvio_ancora_faltante(self):
        passo = {
            "cliente": "Não consigo fazer Pix.",
            "resposta_esperada": "Compreendo. Por segurança, confirme seu CPF.",
            "ancoras": ["cpf", "seguranca"],
            "desvios": [
                {
                    "id": "faltou_cpf",
                    "descricao": "Operador não solicitou CPF",
                    "gatilho": {
                        "tipo": "ancora_faltante",
                        "termos_faltantes": ["cpf"],
                    },
                    "reforco_cliente": "Mas você não vai nem confirmar meus dados antes?",
                    "reorientacao_esperada": "Peço desculpas, poderia me confirmar seu CPF?",
                }
            ],
        }

        # Operador respondeu sem pedir CPF
        resposta_incompleta = "Vou consultar o sistema agora para ver o erro."
        resultado = avaliar_resposta_processo(resposta_incompleta, passo)
        self.assertIsNotNone(resultado["desvio_disparado"])
        self.assertEqual(resultado["desvio_disparado"]["id"], "faltou_cpf")

        simulacao = simular_reacao_especialista(resposta_incompleta, passo)
        self.assertEqual(simulacao["status"], "reforco")
        self.assertIn("confirmar meus dados", simulacao["fala_cliente"])

    def test_avaliar_resposta_correta_com_ancoras(self):
        passo = {
            "cliente": "Não consigo fazer Pix.",
            "resposta_esperada": "Compreendo. Por segurança, confirme seu CPF.",
            "respostas_aceitas": [
                "Entendo a situação. Por favor, me informe seu CPF para validação de segurança."
            ],
            "ancoras": ["cpf"],
            "desvios": [],
        }

        resposta_boa = "Entendo perfeitamente o transtorno. Por segurança, me informe seu CPF por favor."
        resultado = avaliar_resposta_processo(resposta_boa, passo)
        self.assertIsNone(resultado["desvio_disparado"])
        self.assertTrue(resultado["similaridade"] >= 0.50)


if __name__ == "__main__":
    unittest.main()
