import re
import unicodedata
from spellchecker import SpellChecker

PALAVRAS_PERMITIDAS = {
    "pix", "bradesco", "app", "ddd", "email", "e-mail",
    "estorno", "extrato", "agência", "agencia", "conta",
    "cesta", "serviços", "servicos", "bloqueio", "cliente",
    "atendimento", "saldo", "transferência", "transferencia",
    "banco", "análise", "analise", "prazo", "contato",
    "setor", "responsável", "responsavel", "horário", "horario", "extorno", "ok",
}

ABREVIACOES_PROIBIDAS = {
    "vc": "você",
    "vcs": "vocês",
    "tb": "também",
    "pq": "porque",
    "blz": "beleza",
    "mha": "minha",
    "fasso": "faço",
    "nao": "não",
    "to": "estou",
    "vo": "vou"
}

SINONIMOS = {
    "verificar": ["analisar", "checar", "consultar", "conferir"],
    "analisar": ["verificar", "checar", "consultar", "conferir"],
    "orientar": ["explicar", "informar", "esclarecer"],
    "explicar": ["orientar", "informar", "esclarecer"],
    "ajudar": ["auxiliar", "apoiar"],
    "resolver": ["solucionar", "regularizar"],
    "problema": ["erro", "falha", "ocorrência", "ocorrencia"],
    "bloqueio": ["restrição", "restricao", "impedimento"],
    "prazo": ["tempo", "período", "periodo"],
    "contato": ["retorno", "atendimento"],
    "solicitação": ["pedido", "demanda", "solicitacao"],
    "cancelamento": ["cancelar"],
    "estorno": ["devolução", "devolucao", "reembolso"],
    "urgência": ["urgencia", "prioridade"],
    "informações": ["informacoes", "dados", "detalhes"]
}

FRASES_CHAVE = [
    ["entendo sua situação", "compreendo sua situação", "entendo a sua situação"],
    ["vou verificar", "vou analisar", "vou consultar", "vou checar"],
    ["posso te ajudar", "posso ajudar", "vou te ajudar"],
    ["prazo previsto", "prazo para retorno", "prazo informado"],
    ["setor responsável", "time especializado", "área responsável", "area responsavel"],
    ["peço um momento", "peço só um momento", "aguarde um momento", "por gentileza aguarde"],
    ["está dentro do prazo", "esta dentro do prazo"],
    ["vou te orientar", "vou explicar", "vou informar"]
]

PALAVRAS_CRITICAS = {
    "tarifa / estorno": ["análise", "prazo", "estorno", "contestação"],
    "pix com bloqueio cautelar": ["bloqueio", "análise", "segurança", "prazo"],
    "conta bloqueada / pix indisponível": ["bloqueio", "setor", "solicitação", "contato"]
}

PALAVRAS_EMPATICAS = [
    "entendo", "compreendo", "lamento", "sinto muito",
    "posso te ajudar", "vou verificar", "por gentileza",
    "agradeço", "obrigada", "obrigado"
]

spell = SpellChecker(language="pt")
spell.word_frequency.load_words(PALAVRAS_PERMITIDAS)

def remover_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

def tokenizar_palavras(texto: str):
    return list(re.finditer(r"\b[^\W\d_]+\b", texto, re.UNICODE))

def normalizar_texto(texto: str) -> str:
    texto = texto.lower().strip()
    texto = remover_acentos(texto)
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto

def expandir_com_sinonimos(palavras: set) -> set:
    expandidas = set(palavras)

    for palavra in list(palavras):
        if palavra in SINONIMOS:
            for sinonimo in SINONIMOS[palavra]:
                expandidas.add(normalizar_texto(sinonimo))

        for chave, sinonimos in SINONIMOS.items():
            sinonimos_normalizados = {normalizar_texto(s) for s in sinonimos}
            if palavra in sinonimos_normalizados:
                expandidas.add(normalizar_texto(chave))
                expandidas.update(sinonimos_normalizados)

    return expandidas

def detectar_erros_linguisticos(texto: str):
    erros = []
    avisos = []

    encontrados = tokenizar_palavras(texto)

    for match in encontrados:
        palavra_original = match.group(0)
        palavra = palavra_original.lower()

        if len(palavra) <= 1:
            continue

        if palavra in PALAVRAS_PERMITIDAS:
            continue

        if palavra in ABREVIACOES_PROIBIDAS:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(
                f'A palavra "{palavra_original}" parece abreviação. Prefira "{ABREVIACOES_PROIBIDAS[palavra]}".'
            )
            continue

        if spell.known([palavra]):
            continue

        sugestao = spell.correction(palavra)

        if not sugestao:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(f'A palavra "{palavra_original}" não foi reconhecida no português.')
            continue

        if remover_acentos(sugestao) == remover_acentos(palavra) and sugestao != palavra:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(
                f'A palavra "{palavra_original}" parece estar sem acento. Sugestão: "{sugestao}".'
            )
        elif sugestao != palavra:
            erros.append({
                "offset": match.start(),
                "length": len(palavra_original)
            })
            avisos.append(
                f'A palavra "{palavra_original}" pode estar incorreta. Sugestão: "{sugestao}".'
            )

    return erros, avisos

def validar_pontuacao_final(texto: str) -> bool:
    texto = texto.strip()
    if not texto:
        return False
    return texto[-1] in [".", "?", "!"]

def validar_primeira_letra_maiuscula(texto: str) -> bool:
    texto = texto.strip()
    for char in texto:
        if char.isalpha():
            return char.isupper()
    return False

def validar_tamanho_minimo(resposta: str, resposta_esperada: str):
    resposta = resposta.strip()
    resposta_esperada = resposta_esperada.strip()

    tamanho_esperado = len(resposta_esperada)
    tamanho_resposta = len(resposta)

    minimo = max(25, int(tamanho_esperado * 0.6))
    return tamanho_resposta >= minimo, minimo