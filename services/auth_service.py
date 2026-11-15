"""Cadastro, senha e proteção contra tentativas em massa dos operadores."""
import hashlib
import re
import secrets
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

REGEX_USUARIO = re.compile(r"^[a-z0-9._-]{3,30}$")
SENHA_MINIMA = 8
SENHA_MAXIMA = 128

MAX_FALHAS = 5
JANELA_SEGUNDOS = 300

# Hash de uma senha qualquer: usado para gastar o mesmo tempo quando o usuário não existe.
_HASH_FALSO = generate_password_hash("senha-falsa-para-igualar-tempo")


def normalizar_usuario(usuario: str) -> str:
    return (usuario or "").strip().lower()


def validar_cadastro(usuario: str, nome: str, senha: str, confirmacao: str) -> list:
    erros = []

    if not REGEX_USUARIO.match(usuario):
        erros.append("Usuário deve ter de 3 a 30 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado.")

    nome = (nome or "").strip()
    if not (2 <= len(nome) <= 40):
        erros.append("O nome de exibição deve ter de 2 a 40 caracteres.")

    senha = senha or ""
    if not (SENHA_MINIMA <= len(senha) <= SENHA_MAXIMA):
        erros.append(f"A senha deve ter entre {SENHA_MINIMA} e {SENHA_MAXIMA} caracteres.")
    elif senha != confirmacao:
        erros.append("A confirmação da senha não confere.")

    return erros


def validar_nova_senha(senha: str, confirmacao: str) -> list:
    senha = senha or ""
    if not (SENHA_MINIMA <= len(senha) <= SENHA_MAXIMA):
        return [f"A senha deve ter entre {SENHA_MINIMA} e {SENHA_MAXIMA} caracteres."]
    if senha != confirmacao:
        return ["A confirmação da senha não confere."]
    return []


# Alfabeto sem caracteres ambíguos (0/O, 1/I/L): códigos fáceis de copiar à mão.
_ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def gerar_codigo_recuperacao() -> str:
    """16 caracteres (~80 bits) no formato XXXX-XXXX-XXXX-XXXX."""
    letras = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(16))
    return "-".join(letras[i:i + 4] for i in range(0, 16, 4))


def normalizar_codigo(codigo: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (codigo or "").upper())


def gerar_senha_temporaria() -> str:
    letras = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(12))
    return "-".join(letras[i:i + 4] for i in range(0, 12, 4))


def fingerprint_senha(senha_hash: str) -> str:
    """Muda sempre que a senha muda; usado para derrubar sessões antigas."""
    return hashlib.sha256((senha_hash or "").encode()).hexdigest()[:20]


def gerar_hash(senha: str) -> str:
    return generate_password_hash(senha)


def verificar_senha(hash_salvo, senha: str) -> bool:
    """Compara em tempo parecido exista ou não o usuário (hash_salvo None = não existe)."""
    if hash_salvo is None:
        check_password_hash(_HASH_FALSO, senha or "")
        return False
    return check_password_hash(hash_salvo, senha or "")


class LimitadorDeTentativas:
    """Bloqueia temporariamente após várias falhas de login (em memória, por instância)."""

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


limitador_login = LimitadorDeTentativas()


limitador_recuperacao = LimitadorDeTentativas()
