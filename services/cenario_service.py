"""Validação dos cenários criados/editados pelo supervisor."""
import re

from services.conduta_service import LIMITE_MAXIMO_ESPERA, REGRAS_PADRAO
from services.texto_service import detectar_erros_linguisticos, normalizar_texto

TITULO_MIN, TITULO_MAX = 3, 80
CLIENTE_MIN, CLIENTE_MAX = 5, 400
RESPOSTA_MIN, RESPOSTA_MAX = 10, 500
MAX_PASSOS = 12
MAX_PALAVRAS_CRITICAS = 10
ORDEM_MAX = 9999


def separar_palavras_criticas(texto: str) -> list:
    """Aceita vírgula, ponto e vírgula ou quebra de linha; remove duplicadas mantendo a ordem."""
    vistas, resultado = set(), []
    for bruto in re.split(r"[,;\n]+", texto or ""):
        palavra = bruto.strip().lower()
        if palavra and palavra not in vistas:
            vistas.add(palavra)
            resultado.append(palavra)
    return resultado


def validar_cenario(titulo, ordem, palavras_texto, clientes, respostas, ordem_padrao: int = 0,
                    espera_ativa: bool = True, espera_max="2"):
    """
    Retorna (erros, avisos, dados). `dados` só é confiável quando `erros` está vazio.
    Avisos (ortografia da resposta esperada etc.) não impedem o salvamento.
    """
    erros, avisos = [], []

    titulo = (titulo or "").strip()
    if not (TITULO_MIN <= len(titulo) <= TITULO_MAX):
        erros.append(f"O título deve ter de {TITULO_MIN} a {TITULO_MAX} caracteres.")

    try:
        ordem_valor = int(str(ordem).strip()) if str(ordem or "").strip() else ordem_padrao
    except ValueError:
        ordem_valor = None
    if ordem_valor is None or not (0 <= ordem_valor <= ORDEM_MAX):
        erros.append(f"A ordem deve ser um número de 0 a {ORDEM_MAX}.")
        ordem_valor = ordem_padrao

    fluxo = []
    pares = list(zip(clientes or [], respostas or []))
    for numero, (cliente, resposta) in enumerate(pares, start=1):
        cliente, resposta = (cliente or "").strip(), (resposta or "").strip()
        if not cliente and not resposta:
            continue  # linha em branco
        if not (CLIENTE_MIN <= len(cliente) <= CLIENTE_MAX):
            erros.append(f"Passo {numero}: a fala do cliente deve ter de {CLIENTE_MIN} a {CLIENTE_MAX} caracteres.")
        if not (RESPOSTA_MIN <= len(resposta) <= RESPOSTA_MAX):
            erros.append(f"Passo {numero}: a resposta esperada deve ter de {RESPOSTA_MIN} a {RESPOSTA_MAX} caracteres.")
        fluxo.append({"cliente": cliente, "resposta_esperada": resposta})

    if not fluxo:
        erros.append("Informe pelo menos um passo (fala do cliente e resposta esperada).")
    if len(fluxo) > MAX_PASSOS:
        erros.append(f"No máximo {MAX_PASSOS} passos por cenário.")

    palavras = separar_palavras_criticas(palavras_texto)
    if len(palavras) > MAX_PALAVRAS_CRITICAS:
        erros.append(f"No máximo {MAX_PALAVRAS_CRITICAS} palavras críticas.")
    if any(not (2 <= len(p) <= 30) for p in palavras):
        erros.append("Cada palavra crítica deve ter de 2 a 30 caracteres.")

    # Avisos: não bloqueiam.
    if not erros:
        texto_esperado = normalizar_texto(" ".join(p["resposta_esperada"] for p in fluxo))
        for palavra in palavras:
            if normalizar_texto(palavra) not in texto_esperado:
                avisos.append(f'A palavra crítica "{palavra}" não aparece em nenhuma resposta esperada.')
        for numero, passo in enumerate(fluxo, start=1):
            _, problemas = detectar_erros_linguisticos(passo["resposta_esperada"])
            if problemas:
                avisos.append(f"Passo {numero} (resposta esperada): " + " ".join(problemas[:3]))

    texto_limite = str(espera_max if espera_max is not None else "").strip()
    try:
        limite_espera = int(texto_limite) if texto_limite else REGRAS_PADRAO["espera"]["max"]  # em branco: padrão
    except ValueError:
        limite_espera = None
    if limite_espera is None or not (0 <= limite_espera <= LIMITE_MAXIMO_ESPERA):
        erros.append(f"O limite de pedidos de espera deve ser um número de 0 a {LIMITE_MAXIMO_ESPERA}.")
        limite_espera = REGRAS_PADRAO["espera"]["max"]

    regras = {"espera": {"ativa": bool(espera_ativa), "max": limite_espera}}
    dados = {"titulo": titulo, "ordem": ordem_valor, "palavras_criticas": palavras, "fluxo": fluxo, "regras": regras}
    return erros, avisos, dados
