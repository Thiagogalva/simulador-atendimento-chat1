"""
Cliente mínimo (sem dependências) para APIs "chat/completions" compatíveis com a OpenAI
(Groq, Gemini, Mistral, Cerebras, OpenRouter...). Inclui limite por operador e disjuntor.

A IA NUNCA altera notas: só gera texto de feedback. Qualquer falha vira `LLMIndisponivel`
e quem chama usa o feedback local por regras.
"""
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import config


class LLMIndisponivel(Exception):
    def __init__(self, motivo: str, codigo: str = "falha"):
        super().__init__(motivo)
        self.motivo = motivo
        self.codigo = codigo  # "nao_configurado" | "limite" | "disjuntor" | "falha"


def configurado() -> bool:
    return bool(
        config.LLM_API_KEY and config.LLM_MODEL
        and config.LLM_BASE_URL.startswith(("https://", "http://"))
    )


class LimiteDeUso:
    """Janela deslizante: no máximo `maximo` usos por chave dentro de `janela` segundos."""

    def __init__(self, janela: int = 3600):
        self.janela = janela
        self._usos = {}
        self._trava = threading.Lock()

    def permitir(self, chave) -> bool:
        with self._trava:
            agora = time.time()
            recentes = [t for t in self._usos.get(chave, []) if agora - t < self.janela]
            if len(recentes) >= max(config.LLM_LIMITE_POR_HORA, 0):
                self._usos[chave] = recentes
                return False
            recentes.append(agora)
            self._usos[chave] = recentes
            return True


limite_por_operador = LimiteDeUso()

_disjuntor = {"ate": 0.0}
_trava_disjuntor = threading.Lock()


def _abrir_disjuntor(segundos: float):
    with _trava_disjuntor:
        _disjuntor["ate"] = max(_disjuntor["ate"], time.monotonic() + segundos)


def reiniciar_estado():
    """Usado nos testes."""
    with _trava_disjuntor:
        _disjuntor["ate"] = 0.0
    limite_por_operador._usos.clear()


def chat(mensagens: list, max_tokens: int = 350, temperature: float = 0.3) -> str:
    """Envia a conversa e devolve o texto da resposta. Lança LLMIndisponivel em qualquer problema."""
    if not configurado():
        raise LLMIndisponivel("IA não configurada.", "nao_configurado")

    with _trava_disjuntor:
        if time.monotonic() < _disjuntor["ate"]:
            raise LLMIndisponivel("IA temporariamente suspensa após falhas.", "disjuntor")

    corpo = json.dumps({
        "model": config.LLM_MODEL,
        "messages": mensagens,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    requisicao = urllib.request.Request(
        f"{config.LLM_BASE_URL}/chat/completions",
        data=corpo,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "User-Agent": "simulador-atendimento/1.0",
        },
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=config.LLM_TIMEOUT) as resposta:
            bruto = resposta.read(1_000_000)
    except urllib.error.HTTPError as erro:
        if erro.code in (401, 403):
            _abrir_disjuntor(600)   # chave inválida/sem permissão: não insiste
        elif erro.code == 429 or erro.code >= 500:
            _abrir_disjuntor(60)    # limite do provedor ou instabilidade
        else:
            _abrir_disjuntor(300)   # modelo/URL errados
        raise LLMIndisponivel(f"O provedor respondeu HTTP {erro.code}.") from erro
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as erro:
        _abrir_disjuntor(60)
        raise LLMIndisponivel("Não foi possível falar com o provedor de IA.") from erro

    try:
        texto = json.loads(bruto.decode("utf-8"))["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as erro:
        _abrir_disjuntor(60)
        raise LLMIndisponivel("Resposta inesperada do provedor de IA.") from erro

    if not isinstance(texto, str) or not texto.strip():
        raise LLMIndisponivel("O provedor de IA devolveu uma resposta vazia.")
    return texto
