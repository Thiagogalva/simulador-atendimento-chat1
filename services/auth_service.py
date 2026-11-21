"""
Identificação por nome (sem login nem senha) e proteção do código de supervisor.

O sistema roda dentro de uma plataforma interna de aprendizado: o operador só informa o nome no início,
e o ranking usa esse nome. Não há autenticação; o acesso do supervisor é protegido por um código
secreto definido no servidor (SUPERVISOR_CODIGO).
"""
import re
import threading
import time

from services.texto_service import normalizar_texto

NOME_MIN, NOME_MAX = 2, 40
_NOME_VALIDO = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .'’-]*$")

MAX_FALHAS = 5
JANELA_SEGUNDOS = 300


def limpar_nome(nome: str) -> str:
    return re.sub(r"\s+", " ", nome or "").strip()


def validar_nome(nome: str):
    """Retorna (nome_limpo, erros). Só letras, espaços, apóstrofo, hífen e ponto."""
    limpo = limpar_nome(nome)
    erros = []

    if not (NOME_MIN <= len(limpo) <= NOME_MAX):
        erros.append(f"Informe o seu nome (de {NOME_MIN} a {NOME_MAX} caracteres).")
    elif not _NOME_VALIDO.match(limpo) or len(re.findall(r"[^\W\d_]", limpo)) < 2:
        erros.append("Use apenas letras, espaços, hífen, apóstrofo e ponto no nome.")

    return limpo, erros


def chave_do_nome(nome: str) -> str:
    """
    Identidade do operador: o mesmo nome escrito de formas diferentes ("João Silva", "joao  silva")
    resulta na mesma chave e, portanto, no mesmo histórico e posição no ranking.
    """
    return re.sub(r"\s+", " ", normalizar_texto(nome)).strip()


class LimitadorDeTentativas:
    """Janela deslizante em memória (por instância): bloqueia após `max_falhas` ocorrências em `janela` s."""

    def __init__(self, max_falhas=MAX_FALHAS, janela=JANELA_SEGUNDOS):
        self.max_falhas = max_falhas
        self.janela = janela
        self._falhas = {}
        self._trava = threading.Lock()

    def _recentes(self, chave, agora):
        recentes = [t for t in self._falhas.get(chave, []) if agora - t < self.janela]
        if recentes:
            self._falhas[chave] = recentes
        else:
            self._falhas.pop(chave, None)
        return recentes

    def bloqueado(self, chave: str) -> bool:
        with self._trava:
            return len(self._recentes(chave, time.time())) >= self.max_falhas

    def registrar_falha(self, chave: str):
        with self._trava:
            agora = time.time()
            self._recentes(chave, agora)
            self._falhas.setdefault(chave, []).append(agora)

    def limpar(self, chave: str):
        with self._trava:
            self._falhas.pop(chave, None)


# Tentativas erradas do código de supervisor (por IP).
limitador_supervisor = LimitadorDeTentativas()
# Criação de nomes novos (por IP): impede encher o ranking com milhares de nomes falsos.
limitador_nomes_novos = LimitadorDeTentativas(max_falhas=30, janela=3600)
