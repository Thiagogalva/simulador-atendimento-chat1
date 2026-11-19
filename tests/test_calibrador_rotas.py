import unittest
from repositories.cenario_repository import buscar_cenario, criar_cenario, listar_cenarios
from repositories.operador_repository import definir_papel
from tests.helpers import apagar_cenario, cliente_logado, iniciar, token_csrf


class TestCalibradorRotasESimulacao(unittest.TestCase):
    def setUp(self):
        self.client, self.operador_id, self.usuario = cliente_logado(nome="Supervisor Calibrador")
        definir_papel(self.operador_id, "supervisor")

    def test_acesso_calibrador(self):
        r = self.client.get("/supervisor/calibrador")
        self.assertEqual(r.status_code, 302)  # Redireciona para o primeiro cenário

        cenarios = listar_cenarios()
        self.assertTrue(len(cenarios) > 0)
        primeiro_id = cenarios[0]["id"]

        r_cenario = self.client.get(f"/supervisor/calibrador/{primeiro_id}")
        self.assertEqual(r_cenario.status_code, 200)
        html = r_cenario.get_data(as_text=True)
        self.assertIn("Calibrador de Processos", html)
        self.assertIn("Respostas Corretas do Especialista", html)

    def test_api_extrair_ancoras(self):
        respostas = [
            "Olá! Para sua segurança, me confirme seu CPF e nome completo.",
            "Boa tarde! Por segurança, poderia me informar o seu CPF e nome?",
        ]
        csrf = token_csrf(self.client)
        r = self.client.post(
            "/supervisor/calibrador/extrair-ancoras",
            json={"respostas": respostas},
            headers={"X-CSRFToken": csrf},
        )
        self.assertEqual(r.status_code, 200)
        dados = r.get_json()
        self.assertIn("ancoras", dados)
        self.assertTrue(len(dados["ancoras"]) > 0)

    def test_api_simular_resposta(self):
        passo = {
            "cliente": "Não consigo fazer Pix.",
            "resposta_esperada": "Compreendo. Por segurança, confirme seu CPF.",
            "ancoras": ["cpf"],
            "desvios": [
                {
                    "id": "faltou_cpf",
                    "descricao": "Não pediu CPF",
                    "gatilho": {"tipo": "ancora_faltante", "termos_faltantes": ["cpf"]},
                    "reforco_cliente": "Mas você não vai nem confirmar meus dados antes?",
                    "reorientacao_esperada": "Por segurança, me confirme seu CPF.",
                }
            ],
        }
        csrf = token_csrf(self.client)
        # Resposta sem CPF dispara reforço
        r = self.client.post(
            "/supervisor/calibrador/simular-resposta",
            json={"resposta_teste": "Vou olhar o sistema agora.", "passo": passo},
            headers={"X-CSRFToken": csrf},
        )
        self.assertEqual(r.status_code, 200)
        dados = r.get_json()
        self.assertEqual(dados["status"], "reforco")
        self.assertIn("confirmar meus dados", dados["fala_cliente"])

    def test_simulacao_com_reforco_dinamico(self):
        # 1. Cria um cenário calibrado com 1 passo que exige CPF
        passo_calibrado = {
            "cliente": "Não consigo fazer transferência Pix.",
            "resposta_esperada": "Compreendo sua situação. Para sua segurança, por favor me informe o seu CPF.",
            "respostas_aceitas": [
                "Entendo perfeitamente o ocorrido. Por motivos de segurança, poderia me confirmar seu CPF?"
            ],
            "ancoras": ["cpf"],
            "desvios": [
                {
                    "id": "sem_cpf",
                    "descricao": "Esqueceu do CPF",
                    "gatilho": {"tipo": "ancora_faltante", "termos_faltantes": ["cpf"]},
                    "reforco_cliente": "Mas você não vai nem checar meu CPF ou meus dados antes?",
                    "reorientacao_esperada": "Peço desculpas, para sua segurança me confirme seu CPF.",
                    "reconhecimento_cliente": "Perfeito, agora sim. Meu CPF é 123456.",
                }
            ],
        }
        cenario_id = criar_cenario({
            "titulo": "Cenário Teste Calibrado",
            "ordem": 9999,
            "palavras_criticas": ["cpf", "segurança"],
            "fluxo": [passo_calibrado],
            "regras": {"espera": {"ativa": True, "max": 2}},
        }, criado_por=self.operador_id)
        self.addCleanup(apagar_cenario, cenario_id)

        # 2. Inicia a simulação como operador
        iniciar(self.client, modo="treino")

        from repositories.atendimento_repository import listar_atendimentos_usuario
        with self.client.session_transaction() as s:
            iniciada_em = s["simulacao_iniciada_em"]
        ats = listar_atendimentos_usuario(f"operador-{self.operador_id}", iniciada_em)
        nosso_at = next(a for a in ats if a["titulo"] == "Cenário Teste Calibrado")
        meu_id = nosso_at["id"]

        # 3. Operador envia resposta sem CPF -> deve receber a fala de reforço
        r_resp1 = self.client.post("/responder", json={
            "id": meu_id,
            "resposta": "Vou verificar o que aconteceu no sistema agora mesmo.",
        })
        self.assertEqual(r_resp1.status_code, 200)
        dados1 = r_resp1.get_json()
        ultima_msg = dados1["mensagens"][-1]
        self.assertEqual(ultima_msg["tipo"], "cliente")
        self.assertIn("checar meu CPF", ultima_msg["texto"])
        self.assertFalse(dados1["finalizado"])

        # 4. Operador agora corrige e fornece a reorientação esperada com o CPF
        r_resp2 = self.client.post("/responder", json={
            "id": meu_id,
            "resposta": "Peço desculpas pela falha. Para sua segurança, me confirme seu CPF por favor.",
        })
        self.assertEqual(r_resp2.status_code, 200)
        dados2 = r_resp2.get_json()
        ultima_msg2 = dados2["mensagens"][-1]
        self.assertEqual(ultima_msg2["tipo"], "cliente")
        self.assertIn("Perfeito, agora sim", ultima_msg2["texto"])
        # Como era o único passo, o atendimento é finalizado com sucesso
        self.assertTrue(dados2["finalizado"])


if __name__ == "__main__":
    unittest.main()
