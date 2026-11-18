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

from services import nlp_service
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


def conceitos_e_lemas(texto: str) -> dict:
    """
    {conceito: lema} do texto. O lema (da forma como o spaCy o enxerga) só é usado para comparar
    vetores de palavras; sem spaCy o lema é a própria palavra normalizada.
    """
    lema_do_token = {}
    for original, lema, _ in nlp_service.analisar(texto):
        lema_do_token.setdefault(normalizar_texto(original), lema)

    resultado = {}
    for palavra in normalizar_texto(texto).split():
        if palavra in STOPWORDS or palavra in NEGACOES or len(palavra) < 2:
            continue
        radical = _radical(palavra)
        conceito = _CONCEITO_DO_RADICAL.get(radical, radical)
        resultado.setdefault(conceito, lema_do_token.get(palavra, palavra))
    return resultado


def conceitos_atendidos(esperados: dict, resposta: dict, minimo: float = 0.5) -> set:
    """Conceitos esperados atendidos pela resposta, com pareamento um-para-um (uma palavra cobre uma ideia)."""
    return {ce for (ce, _), credito in _parear(esperados, resposta).items() if credito >= minimo}


def classificar_ideias(ideias: list, texto: str, minimo_fraco: float = 0.5):
    """
    Separa as ideias em (fortes, fracas) em relação ao texto, sem reaproveitar uma palavra do texto:
      fortes - mesma ideia, sinônimo da lista ou erro de digitação (evidência segura, nunca por vetores);
      fracas - só parecem próximas por vetores de palavras (evidência incerta).
    As demais não foram encontradas. Quem fala com o usuário deve elogiar só as fortes e cobrar só as ausentes.
    """
    por_conceito, esperados, sem_conceito = {}, {}, set()
    for palavra in ideias:
        encontrados = conceitos_e_lemas(palavra)
        if not encontrados:
            sem_conceito.add(palavra)  # nada a comparar: não afirma nada
        for conceito, lema in encontrados.items():
            esperados.setdefault(conceito, lema)
            por_conceito.setdefault(conceito, []).append(palavra)

    pares = _parear(esperados, conceitos_e_lemas(texto))
    fortes_c = {ce for (ce, cr), credito in pares.items() if _mesma_ideia(ce, cr)}
    fracas_c = {ce for (ce, cr), credito in pares.items() if credito >= minimo_fraco and not _mesma_ideia(ce, cr)}

    fortes = {p for c in fortes_c for p in por_conceito[c]}
    fracas = {p for c in fracas_c for p in por_conceito[c]} - fortes
    return fortes, fracas | sem_conceito


def ideias_cobertas(ideias: list, texto: str, minimo: float = 0.5) -> set:
    """Ideias que aparecem no texto, por qualquer evidência (forte ou fraca), sem reaproveitar uma palavra."""
    fortes, fracas = classificar_ideias(ideias, texto, minimo_fraco=minimo)
    return fortes | fracas


def palavra_coberta(palavra: str, texto: str, minimo: float = 0.5) -> bool:
    """A ideia da palavra aparece no texto? (mesmo conceito ou, com spaCy, sinônimo por vetores)."""
    alvo = conceitos(palavra)
    if not alvo:
        return True
    em_texto = conceitos_e_lemas(texto)
    if alvo & set(em_texto):
        return True
    if nlp_service.disponivel():
        lemas_alvo = nlp_service.palavras_de_conteudo(palavra) or [normalizar_texto(palavra)]
        return any(nlp_service.credito_vetorial(a, b) >= minimo for a in lemas_alvo for b in em_texto.values())
    return False


def palavras_chave(texto: str, limite: int = 4) -> list:
    """
    Palavras mais características do texto (as de maior peso/raridade), na forma original
    e na ordem em que aparecem. Usado nas dicas do modo treino.
    """
    candidatas = {}  # conceito -> (peso, posição, palavra original)
    de_conteudo = set(nlp_service.palavras_de_conteudo(texto))  # vazio sem spaCy
    lema_do_token = {normalizar_texto(o): l for o, l, _ in nlp_service.analisar(texto)}
    for posicao, original in enumerate(re.findall(r"[^\W\d_]+", texto, re.UNICODE)):
        normal = normalizar_texto(original)
        if not normal or normal in STOPWORDS or normal in NEGACOES or len(normal) < 4:
            continue
        if de_conteudo and lema_do_token.get(normal) not in de_conteudo:
            continue  # com spaCy, só substantivos/verbos/adjetivos servem de pista
        radical = _radical(normal)
        conceito = _CONCEITO_DO_RADICAL.get(radical, radical)
        peso = _peso(conceito)
        if conceito not in candidatas:
            candidatas[conceito] = (peso, posicao, original.lower())

    melhores = sorted(candidatas.values(), key=lambda c: (-c[0], c[1]))[:limite]
    return [palavra for _, _, palavra in sorted(melhores, key=lambda c: c[1])]


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


def _mesma_ideia(conceito_a: str, conceito_b: str) -> bool:
    """Evidência segura: mesmo conceito (inclui sinônimos da lista) ou erro de digitação. Nunca vem de vetores."""
    if conceito_a == conceito_b:
        return True
    return (len(conceito_a) >= 5 and len(conceito_b) >= 5
            and SequenceMatcher(None, conceito_a, conceito_b).ratio() >= 0.86)


def _credito_do_par(conceito_a: str, lema_a: str, conceito_b: str, lema_b: str) -> float:
    """
    Quanto um conceito vale no lugar do outro:
      1.0 mesmo conceito; 0.8 quase igual (erro de digitação);
      até 0.85 sinônimo por vetores de palavras (só com spaCy); 0 caso contrário.
    """
    if conceito_a == conceito_b:
        return 1.0
    if (len(conceito_a) >= 5 and len(conceito_b) >= 5
            and SequenceMatcher(None, conceito_a, conceito_b).ratio() >= 0.86):
        return 0.8
    if nlp_service.disponivel():
        return nlp_service.credito_vetorial(lema_a, lema_b)
    return 0.0


def _parear(c_esp: dict, c_resp: dict) -> dict:
    """
    Pareamento um-para-um guloso entre conceitos esperados e da resposta, do melhor crédito para o pior.
    Evita que uma única palavra da resposta "cubra" vários conceitos esperados.
    Retorna {(conceito_esperado, conceito_resposta): crédito}.
    """
    candidatos = []
    for ce, le in c_esp.items():
        for cr, lr in c_resp.items():
            credito = _credito_do_par(ce, le, cr, lr)
            if credito > 0:
                # o cosseno bruto desempata créditos iguais (o teto de crédito esconde diferenças)
                cosseno = (nlp_service.similaridade_palavras(le, lr) or 0.0) if credito < 1.0 else 1.0
                candidatos.append((credito, cosseno, ce, cr))

    candidatos.sort(key=lambda t: (-t[0], -t[1], t[2], t[3]))
    usados_e, usados_r, pares = set(), set(), {}
    for credito, _, ce, cr in candidatos:
        if ce in usados_e or cr in usados_r:
            continue
        usados_e.add(ce)
        usados_r.add(cr)
        pares[(ce, cr)] = credito
    return pares


def similaridade(resposta: str, esperada: str) -> float:
    """Similaridade de significado entre a resposta do operador e a esperada (0 a 1)."""
    c_resp = conceitos_e_lemas(resposta)
    c_esp = conceitos_e_lemas(esperada)

    if not c_esp:
        return 0.0
    if not c_resp:
        return 0.0

    soma_esp = sum(_peso(c) for c in c_esp)
    soma_resp = sum(_peso(c) for c in c_resp)

    pares = _parear(c_esp, c_resp)
    cobertura = sum(_peso(ce) * credito for (ce, _), credito in pares.items()) / soma_esp
    precisao = sum(_peso(cr) * credito for (_, cr), credito in pares.items()) / soma_resp

    # A cobertura importa mais: o operador pode acrescentar detalhes, mas não omitir o essencial.
    nota = 0.75 * cobertura + 0.25 * precisao

    if tem_negacao(resposta) != tem_negacao(esperada):
        nota *= 0.65

    return max(0.0, min(1.0, nota))
