"""
Regras de conduta do operador, configuráveis por cenário (sem IA, determinísticas).

Primeira regra: pedidos de espera ("um momento", "só um instante", "já retorno"...).
O operador pode pedir algumas vezes; passando do limite o cliente reclama e, se insistir, desiste.
"""
import copy
import re
import unicodedata

LIMITE_MAXIMO_ESPERA = 10

REGRAS_PADRAO = {"espera": {"ativa": True, "max": 2}}

_TEMPO = r"(?:momento|momentinho|instante|instantinho|minuto|minutinho|segundo|segundinho)s?"
_PADROES_ESPERA = [
    # "Um momento", "Só um instante": no começo da frase, depois de pontuação, ou com "só/apenas" antes.
    re.compile(rf"(?:^|[.!?;,:]\s*)(?:(?:so|apenas|somente)\s+)?(?:um|uns)\s+{_TEMPO}\b"),
    re.compile(rf"\b(?:so|apenas|somente)\s+(?:um|uns)\s+{_TEMPO}\b"),
    # "Aguarde um momento", "aguardar alguns minutos"
    re.compile(rf"\baguard\w*\s+(?:so\s+|apenas\s+)?(?:um|uns|alguns)\s+{_TEMPO}\b"),
    # "Já retorno", "já volto"
    re.compile(r"\bja(?:\s+ja)?\s+(?:te\s+|lhe\s+|o\s+|a\s+)?(?:retorno|volto|respondo|falo)\b"),
    re.compile(r"\bretorno\s+(?:em\s+)?(?:instantes|breve|seguida)\b"),
]


def _para_busca(texto: str) -> str:
    """Minúsculas e sem acentos, mas mantém a pontuação (ela delimita o início das frases)."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def pedido_de_espera(texto: str) -> bool:
    """O texto pede ao cliente que aguarde ("um momento", "só um instante", "já retorno")?"""
    limpo = _para_busca(texto)
    return any(p.search(limpo) for p in _PADROES_ESPERA)


def regras_efetivas(regras) -> dict:
    """Mescla as regras salvas com o padrão e garante tipos/limites válidos."""
    efetivas = copy.deepcopy(REGRAS_PADRAO)
    espera = (regras or {}).get("espera") if isinstance(regras, dict) else None
    if isinstance(espera, dict):
        if "ativa" in espera:
            efetivas["espera"]["ativa"] = bool(espera["ativa"])
        if "max" in espera:
            try:
                valor = int(espera["max"])
            except (TypeError, ValueError):
                valor = REGRAS_PADRAO["espera"]["max"]
            efetivas["espera"]["max"] = max(0, min(LIMITE_MAXIMO_ESPERA, valor))
    return efetivas
