"""
Similaridade semântica local (sem API, sem modelo para baixar).

Em vez de comparar palavras exatas, compara *conceitos*:
  1. normaliza (minúsculas, sem acentos, sem pontuação) e remove palavras vazias;
  2. reduz cada palavra ao radical ("verificarei", "verificando" -> "verific");
  3. agrupa radicais sinônimos em um mesmo conceito (lista SINONIMOS);
  4. pondera cada conceito pela raridade no conjunto de roteiros (conceito raro vale mais);
  5. penaliza respostas que invertem a negação ("não consigo" x "consigo").

A interface `similaridade(resposta, esperada)` devolve um número de 0 a 1. Para usar embeddings
neurais no futuro basta substituir esta função, mantendo a mesma assinatura.
"""
import math
import re
from difflib import SequenceMatcher
from functools import lru_cache

import snowballstemmer

from services.texto_service import SINONIMOS, normalizar_texto

_stemmer = snowballstemmer.stemmer("portuguese")

NEGACOES = {"nao", "nunca", "jamais", "nenhum", "nenhuma", "impossivel"}

_STOPWORDS_BRUTAS = """
a o as os um uma uns umas de do da dos das em no na nos nas num numa por para pra com sem sobre
ao aos e ou mas que se como mais ja ainda tambem te lhe me vos seu sua seus suas meu minha meus
minhas isso isto esse essa esses essas este esta estes estas aquele aquela eu voce voces ele ela
eles elas vou vai irei ira posso pode podem foi ser sera era sao esta estou estamos estao la aqui
so ate pelo pela pelos pelas dele dela deles delas nesse nessa neste nesta desse dessa deste desta
tem ter ha muito muita
""".split()
STOPWORDS = {normalizar_texto(p) for p in _STOPWORDS_BRUTAS}


@lru_cache(maxsize=4096)
def _radical(palavra: str) -> str:
    return _stemmer.stemWord(palavra)


def _montar_conceitos() -> dict:
    """Une, via union-find, todos os radicais que são sinônimos entre si."""
    pai = {}

    def achar(x):
        pai.setdefault(x, x)
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def unir(a, b):
        ra, rb = achar(a), achar(b)
        if ra != rb:
            pai[max(ra, rb)] = min(ra, rb)  # representante determinístico

    for chave, sinonimos in SINONIMOS.items():
        base = _radical(normalizar_texto(chave))
        achar(base)
        for sinonimo in sinonimos:
            unir(base, _radical(normalizar_texto(sinonimo)))

    return {radical: achar(radical) for radical in list(pai)}


_CONCEITO_DO_RADICAL = _montar_conceitos()


def conceitos(texto: str) -> set:
    """Conjunto de conceitos (radicais agrupados por sinônimo) do texto, sem palavras vazias."""
    resultado = set()
    for palavra in normalizar_texto(texto).split():
        if palavra in STOPWORDS or palavra in NEGACOES or len(palavra) < 2:
            continue
        radical = _radical(palavra)
        resultado.add(_CONCEITO_DO_RADICAL.get(radical, radical))
    return resultado


# Negações de cortesia que não invertem o sentido ("não se preocupe", "não hesite").
_NEGACAO_CORTES = re.compile(r"\bnao (se preocup\w*|hesit\w*|ha de que|tem de que)\b")


def tem_negacao(texto: str) -> bool:
    limpo = _NEGACAO_CORTES.sub(" ", normalizar_texto(texto))
    return any(p in NEGACOES for p in limpo.split())


def _construir_idf() -> tuple:
    """IDF calculado sobre os próprios roteiros (cliente + resposta esperada)."""
    from data.base_atendimentos import BASE_ATENDIMENTOS

    documentos = []
    for item in BASE_ATENDIMENTOS:
        for passo in item["fluxo"]:
            documentos.append(conceitos(passo["cliente"]))
            documentos.append(conceitos(passo["resposta_esperada"]))

    total = len(documentos)
    frequencia = {}
    for doc in documentos:
        for c in doc:
            frequencia[c] = frequencia.get(c, 0) + 1

    idf = {c: math.log((total + 1) / (f + 1)) + 1 for c, f in frequencia.items()}
    idf_desconhecido = math.log(total + 1) + 1
    return idf, idf_desconhecido


_IDF, _IDF_DESCONHECIDO = _construir_idf()


def _peso(conceito: str) -> float:
    return _IDF.get(conceito, _IDF_DESCONHECIDO)


def _correspondencia(conceito: str, outro: set) -> float:
    """1.0 se o conceito existe no outro conjunto; 0.8 se há um quase-igual (erro de digitação)."""
    if conceito in outro:
        return 1.0
    if len(conceito) >= 5:
        for candidato in outro:
            if len(candidato) >= 5 and SequenceMatcher(None, conceito, candidato).ratio() >= 0.86:
                return 0.8
    return 0.0


def similaridade(resposta: str, esperada: str) -> float:
    """Similaridade de significado entre a resposta do operador e a esperada (0 a 1)."""
    c_resp = conceitos(resposta)
    c_esp = conceitos(esperada)

    if not c_esp:
        return 0.0
    if not c_resp:
        return 0.0

    soma_esp = sum(_peso(c) for c in c_esp)
    soma_resp = sum(_peso(c) for c in c_resp)

    cobertura = sum(_peso(c) * _correspondencia(c, c_resp) for c in c_esp) / soma_esp
    precisao = sum(_peso(c) * _correspondencia(c, c_esp) for c in c_resp) / soma_resp

    # A cobertura importa mais: o operador pode acrescentar detalhes, mas não omitir o essencial.
    nota = 0.75 * cobertura + 0.25 * precisao

    if tem_negacao(resposta) != tem_negacao(esperada):
        nota *= 0.65

    return max(0.0, min(1.0, nota))
