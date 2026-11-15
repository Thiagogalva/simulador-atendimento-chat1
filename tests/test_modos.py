import json
import re
import time
import unittest

from data.base_atendimentos import BASE_ATENDIMENTOS
from database.connection import get_connection
from repositories.simulacao_repository import ranking
from tests.helpers import (
    cliente_logado,
    completar_simulacao,
    iniciar,
    liberar_todos,
    post_form,
)

PASSO0 = BASE_ATENDIMENTOS[0]["fluxo"][0]
PASSO1 = BASE_ATENDIMENTOS[0]["fluxo"][1]
FORA = "Hoje o dia está bonito e vamos almoçar mais tarde, tudo bem com você."


def dados_da_pagina(html: str):
    return json.loads(re.search(r"let dados = (.*?);\nlet atual", html, re.S).group(1))


class EscolhaDeModo(unittest.TestCase):
    def setUp(self):
        self.c, self.operador_id, _ = cliente_logado()

    def test_tela_de_escolha_lista_os_dois_modos(self):
        html = self.c.get("/").get_data(as_text=True)
        self.assertIn("Treino", html)
        self.assertIn("Avaliação", html)

    def test_modo_invalido_e_recusado(self):
        r = post_form(self.c, "/iniciar", {"modo": "hack"})
        self.assertEqual(r.status_code, 400)

    def test_iniciar_exige_csrf(self):
        self.assertEqual(self.c.post("/iniciar", data={"modo": "treino"}).status_code, 400)

    def test_simulacao_sem_iniciar_volta_para_a_escolha(self):
        r = self.c.get("/simulacao")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/"))

    def test_recarregar_a_simulacao_nao_reinicia(self):
        iniciar(self.c, "treino")
        r = self.c.post("/responder", json={"id": 0, "resposta": PASSO0["resposta_esperada"]})
        self.assertEqual(r.status_code, 200)
        dados = dados_da_pagina(self.c.get("/simulacao").get_data(as_text=True))
        self.assertEqual(dados[0]["etapa_atual"], 1)  # F5 mantém o progresso

    def test_oferece_continuar_simulacao_em_andamento(self):
        iniciar(self.c, "avaliacao")
        self.assertIn("Continuar simulação", self.c.get("/").get_data(as_text=True))


class NadaVazaParaOCliente(unittest.TestCase):
    """No navegador nunca podem chegar o roteiro nem as respostas esperadas."""

    def _assegurar_sem_vazamento(self, modo):
        c, _, _ = cliente_logado()
        iniciar(c, modo)
        html = c.get("/simulacao").get_data(as_text=True)
        self.assertNotIn('"fluxo"', html)
        self.assertNotIn('"resposta_esperada"', html)
        for atendimento in dados_da_pagina(html):
            self.assertNotIn("fluxo", atendimento)
            self.assertNotIn("resposta_esperada", atendimento)

        r = c.post("/responder", json={"id": 0, "resposta": FORA})
        corpo = r.get_data(as_text=True)
        self.assertNotIn("sugestao", corpo)
        self.assertNotIn(PASSO0["resposta_esperada"], corpo)

    def test_avaliacao(self):
        self._assegurar_sem_vazamento("avaliacao")

    def test_treino(self):
        self._assegurar_sem_vazamento("treino")


class Treino(unittest.TestCase):
    def setUp(self):
        self.c, self.operador_id, _ = cliente_logado()
        iniciar(self.c, "treino")

    def _dica(self, **corpo):
        corpo.setdefault("id", 0)
        return self.c.post("/dica", json=corpo)

    def test_dicas_progressivas(self):
        d1 = self._dica().get_json()
        self.assertEqual(d1["nivel"], 1)
        self.assertNotIn(PASSO0["resposta_esperada"], d1["texto"])  # nível 1 não entrega a resposta
        self.assertIn("Fale sobre", d1["texto"])

        d2 = self._dica().get_json()
        self.assertEqual(d2["nivel"], 2)
        self.assertIn(PASSO0["resposta_esperada"], d2["texto"])
        self.assertTrue(d2["ultimo_nivel"])

        d3 = self._dica().get_json()  # não passa do máximo nem conta de novo
        self.assertEqual((d3["nivel"], d3["dicas_usadas"]), (2, 2))

    def test_reexibir_dica_atual_nao_consome_dica(self):
        self.assertIsNone(self._dica(atual=True).get_json()["texto"])
        self._dica()
        atual = self._dica(atual=True).get_json()
        self.assertEqual((atual["nivel"], atual["dicas_usadas"]), (1, 1))

    def test_dica_reinicia_ao_avancar_de_passo(self):
        self._dica()
        self._dica()
        r = self.c.post("/responder", json={"id": 0, "resposta": PASSO0["resposta_esperada"]}).get_json()
        self.assertEqual((r["etapa_atual"], r["dica_nivel"]), (1, 0))
        d = self._dica().get_json()
        self.assertEqual(d["nivel"], 1)
        self.assertNotIn(PASSO1["resposta_esperada"], d["texto"])

    def test_treino_nao_tem_limite_de_tempo_nem_espera_entre_chats(self):
        # sem liberar nada: o chat 2 já responde (na avaliação seria 403 "não liberado")
        r = self.c.post("/responder", json={"id": 2, "resposta": BASE_ATENDIMENTOS[2]["fluxo"][0]["resposta_esperada"]})
        self.assertEqual(r.status_code, 200, r.get_json())

        liberar_todos(self.c)
        conn = get_connection()
        conn.execute("UPDATE atendimentos SET ultimo_tempo_backend = ? WHERE usuario_uuid = ?",
                     (time.time() - 5000, f"operador-{self.operador_id}"))
        conn.commit()
        conn.close()
        r = self.c.post("/responder", json={"id": 0, "resposta": PASSO0["resposta_esperada"]})
        self.assertEqual(r.status_code, 200, r.get_json())  # turno "antigo" não expira
        self.assertEqual(r.get_json()["media_tempo"], 20)    # tempo não penaliza no treino

    def test_treino_fica_no_historico_mas_fora_do_ranking(self):
        completar_simulacao(self.c, self.operador_id, modo="treino")
        r = self.c.post("/finalizar")
        self.assertEqual(r.status_code, 200, r.get_json())
        dados = r.get_json()
        self.assertEqual(dados["modo"], "treino")
        self.assertIsNone(dados["posicao"])

        self.assertNotIn(self.operador_id, {i["operador_id"] for i in ranking("geral", limite=100000)})
        pagina = self.c.get("/historico").get_data(as_text=True)
        self.assertIn("Treino", pagina)
        self.assertIn("só fez treinos", pagina)  # sem avaliações ainda


class Avaliacao(unittest.TestCase):
    def setUp(self):
        self.c, self.operador_id, _ = cliente_logado()
        iniciar(self.c, "avaliacao")

    def test_dicas_bloqueadas_na_avaliacao(self):
        r = self.c.post("/dica", json={"id": 0})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn(PASSO0["resposta_esperada"], r.get_data(as_text=True))

    def test_dica_sem_login_retorna_401(self):
        import app as aplicacao
        self.assertEqual(aplicacao.app.test_client().post("/dica", json={"id": 0}).status_code, 401)

    def test_chats_seguintes_continuam_bloqueados_ate_a_vez_deles(self):
        r = self.c.post("/responder", json={"id": 2, "resposta": "Resposta qualquer longa o bastante."})
        self.assertEqual(r.status_code, 403)

    def test_avaliacao_entra_no_ranking(self):
        completar_simulacao(self.c, self.operador_id)
        dados = self.c.post("/finalizar").get_json()
        self.assertEqual(dados["modo"], "avaliacao")
        self.assertIsNotNone(dados["posicao"])
        self.assertIn(self.operador_id, {i["operador_id"] for i in ranking("geral", limite=100000)})


if __name__ == "__main__":
    unittest.main()
