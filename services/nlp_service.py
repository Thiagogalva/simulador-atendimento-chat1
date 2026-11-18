"""
Camada opcional de PLN (processamento de linguagem natural) local, via spaCy.

Se o spaCy e o modelo de português estiverem instalados (veja requirements-nlp.txt), o sistema ganha:
  * similaridade por vetores de palavras (reconhece sinônimos que não estão na lista: "conferir" ~ "verificar");
  * classe gramatical (substantivo/verbo/adjetivo) para escolher melhores pistas nas dicas.

Sem o spaCy tudo continua funcionando com o motor léxico (radicais + sinônimos). Roda 100% offline, sem chaves.
Para desligar mesmo com o spaCy instalado: NLP_DESATIVAR=1.
"""
import os
import threading
from functools import lru_cache

MODELO = os.environ.get("SPACY_MODELO", "pt_core_news_md")

_trava = threading.Lock()
_estado = {"nlp": None, "tentou": False}

CLASSES_DE_CONTEUDO = {"NOUN", "PROPN", "VERB", "ADJ"}

# Faixa de similaridade de vetores convertida em "crédito" (0 a 1): abaixo de BAIXO é ruído
# (palavras sem relação ficam em torno de -0,2 a 0,25); acima de ALTO é praticamente sinônimo.
BAIXO, ALTO = 0.35, 0.75
CREDITO_MAXIMO = 0.85


def _carregar():
    with _trava:
        if _estado["tentou"]:
            return _estado["nlp"]
        _estado["tentou"] = True
        if os.environ.get("NLP_DESATIVAR") == "1":
            return None
        try:
            import spacy
            _estado["nlp"] = spacy.load(MODELO, disable=["ner", "parser"])
        except Exception:  # spaCy ou modelo ausente: segue sem a camada de PLN
            _estado["nlp"] = None
        return _estado["nlp"]


def disponivel() -> bool:
    return _carregar() is not None


def reiniciar():
    """Usado nos testes para recarregar/desligar a camada."""
    with _trava:
        _estado["nlp"] = None
        _estado["tentou"] = False
    _doc.cache_clear()
    _vetor.cache_clear()


@lru_cache(maxsize=2048)
def _doc(texto: str):
    nlp = _carregar()
    return nlp(texto) if nlp is not None else None


def analisar(texto: str) -> list:
    """[(texto_minúsculo, lema_minúsculo, classe)] ou [] sem spaCy."""
    doc = _doc(texto or "")
    if doc is None:
        return []
    return [(t.text.lower(), t.lemma_.lower(), t.pos_) for t in doc if not t.is_space and not t.is_punct]


def palavras_de_conteudo(texto: str) -> list:
    """Lemas de substantivos, verbos e adjetivos, na ordem do texto (sem spaCy: lista vazia)."""
    vistos, resultado = set(), []
    for _, lema, classe in analisar(texto):
        if classe in CLASSES_DE_CONTEUDO and lema not in vistos and len(lema) > 2:
            vistos.add(lema)
            resultado.append(lema)
    return resultado


@lru_cache(maxsize=8192)
def _vetor(palavra: str):
    nlp = _carregar()
    if nlp is None:
        return None
    lexema = nlp.vocab[palavra]
    return lexema.vector if lexema.has_vector and lexema.vector_norm else None


def similaridade_palavras(a: str, b: str):
    """Cosseno entre os vetores das palavras (-1 a 1) ou None se alguma não tem vetor."""
    va, vb = _vetor(a), _vetor(b)
    if va is None or vb is None:
        return None
    import numpy as np
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-9))


def credito_vetorial(a: str, b: str) -> float:
    """Quanto vale 'b' no lugar de 'a' (0 a CREDITO_MAXIMO), a partir da similaridade de vetores."""
    if not disponivel():
        return 0.0
    sim = similaridade_palavras(a, b)
    if sim is None or sim <= BAIXO:
        return 0.0
    return min(CREDITO_MAXIMO, (sim - BAIXO) / (ALTO - BAIXO))
