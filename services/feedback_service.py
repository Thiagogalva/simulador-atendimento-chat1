"""
Feedback em texto para o operador, gerado 100% localmente (sem IA externa, sem chaves).

A análise reaproveita o que o sistema já calcula (coerência, empatia, avisos) e acrescenta:
  * ideias do roteiro que foram cobertas ou ficaram faltando (reconhecendo sinônimos);
  * estrutura da resposta (acolher, agir, informar o próximo passo, ser cortês);
  * no feedback final, comparação com a simulação anterior e o ponto mais fraco.

O texto é montado por regras, então é determinístico e pode ser guardado em cache.
"""
from services.dica_service import e_de_tom_ou_generica
from services.semantica_service import classificar_ideias, palavras_chave
from services.texto_service import normalizar_texto
from services.tom_service import componentes_de_acolhimento

ORIGEM = "analise"

_ORIENTACAO_DE_ESTRUTURA = {
    "acolhimento": "reconheça a situação do cliente logo no começo",
    "acao": "diga claramente o que você vai fazer",
    "proximo_passo": "informe o prazo ou o próximo passo",
    "cortesia": "encerre com cortesia",
}
_ORDEM_ESTRUTURA = ("acolhimento", "acao", "proximo_passo", "cortesia")


def _lista(itens: list) -> str:
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _ideias(esperada: str, palavras_criticas) -> list:
    """Palavras que representam o conteúdo da resposta esperada (críticas primeiro)."""
    ideias = []
    for palavra in list(palavras_criticas or []) + palavras_chave(esperada, limite=8):
        # palavras de tom ("entendo", "lamento"...) e genéricas ("forma", "possível") não são ideias do conteúdo
        if len(normalizar_texto(palavra)) >= 4 and not e_de_tom_ou_generica(palavra) and palavra.lower() not in ideias:
            ideias.append(palavra.lower())
    return ideias[:5]


def feedback_resposta(av: dict, resposta: str, esperada: str, palavras_criticas) -> dict:
    coerencia = av["coerencia"]
    partes = []

    if coerencia >= 95:
        partes.append("Excelente: sua resposta cobre tudo o que o cliente precisava.")
    elif coerencia >= 75:
        partes.append("Boa resposta: você cobriu o essencial, com pequenos ajustes possíveis.")
    elif coerencia >= 55:
        partes.append("Resposta parcial: você acertou parte do esperado, mas ainda falta completar.")
    else:
        partes.append("Sua resposta ficou distante do que o cliente pediu. Releia a mensagem dele e responda direto ao ponto.")

    ideias = _ideias(esperada, palavras_criticas)
    # Conservador: só elogia com evidência forte e só cobra o que não tem nem evidência fraca.
    fortes, fracas = classificar_ideias(ideias, resposta)
    cobertas = [i for i in ideias if i in fortes]
    faltando = [i for i in ideias if i not in fortes and i not in fracas]
    if cobertas and coerencia >= 55:
        partes.append("Você abordou: " + _lista(cobertas[:3]) + ".")
    if faltando and coerencia < 95:
        partes.append("Faltou mencionar: " + _lista(faltando[:3]) + ".")

    esperados = componentes_de_acolhimento(esperada)
    presentes = componentes_de_acolhimento(resposta)
    ausentes = [c for c in _ORDEM_ESTRUTURA if c in esperados and c not in presentes]
    if ausentes:
        partes.append("Na estrutura da resposta, " + _lista([_ORIENTACAO_DE_ESTRUTURA[c] for c in ausentes[:2]]) + ".")
    elif "acolhimento" in presentes and coerencia >= 55:
        partes.append("O acolhimento ficou bom.")

    if av["erros"]:
        partes.append("Revise a ortografia antes de enviar.")
    outros = [a for a in av["avisos"] if "ortograf" not in a.lower()][:1]
    for aviso in outros:
        partes.append(aviso if aviso.endswith(".") else aviso + ".")

    return {"texto": " ".join(partes), "origem": ORIGEM}


def _mais_fraca_e_dica(media_coerencia, media_empatia, media_tempo, modo):
    notas = {
        "coerencia": media_coerencia,
        "empatia": media_empatia * 5,   # empatia e tempo vão de 0 a 20; aqui tudo em 0-100
        "tempo": media_tempo * 5,
    }
    if modo == "treino":
        notas.pop("tempo")  # no treino o tempo não conta
    fraca = min(notas, key=notas.get)
    forte = max(notas, key=notas.get)
    return fraca, forte


_NOME_DIMENSAO = {"coerencia": "coerência com o que o cliente pediu", "empatia": "empatia e acolhimento",
                  "tempo": "rapidez nas respostas"}
_PROXIMO_PASSO = {
    "coerencia": "releia a pergunta do cliente antes de responder e confira se cada ponto foi tratado",
    "empatia": "comece cada resposta reconhecendo a situação do cliente antes de explicar",
    "tempo": "pratique respostas mais diretas para responder dentro do tempo",
}


def feedback_final(simulacao: dict, anterior: dict = None) -> dict:
    detalhes = simulacao["detalhes"]
    if not detalhes:
        return {"texto": "Não há atendimentos para analisar nesta simulação.", "origem": ORIGEM}

    modo = simulacao.get("modo", "avaliacao")
    fraca, forte = _mais_fraca_e_dica(simulacao["media_coerencia"], simulacao["media_empatia"],
                                      simulacao["media_tempo"], modo)
    melhor = max(detalhes, key=lambda d: d["nota"])
    pior = min(detalhes, key=lambda d: d["nota"])

    partes = [f"Nota geral {simulacao['nota_geral']} ({simulacao['nivel']})."]

    if anterior is not None:
        diferenca = round(simulacao["nota_geral"] - anterior["nota_geral"], 1)
        if diferenca > 0.5:
            partes.append(f"Você subiu {diferenca} pontos em relação à simulação anterior ({anterior['nota_geral']}).")
        elif diferenca < -0.5:
            partes.append(f"Você caiu {abs(diferenca)} pontos em relação à simulação anterior ({anterior['nota_geral']}); vale revisar os avisos abaixo.")
        else:
            partes.append(f"Seu resultado ficou estável em relação à simulação anterior ({anterior['nota_geral']}).")

    partes.append(f"Seu ponto mais forte foi {_NOME_DIMENSAO[forte]}; o que mais pode melhorar é {_NOME_DIMENSAO[fraca]}.")

    if melhor["id"] != pior["id"]:
        partes.append(f"Melhor atendimento: {melhor['titulo']} ({melhor['nota']}). Mais difícil: {pior['titulo']} ({pior['nota']}).")

    contagem = {}
    for d in detalhes:
        for aviso in d.get("avisos", []):
            contagem[aviso] = contagem.get(aviso, 0) + 1
    if contagem:
        recorrente = max(contagem.items(), key=lambda item: item[1])[0]
        partes.append("Aviso mais frequente: " + (recorrente if recorrente.endswith(".") else recorrente + "."))

    for d in detalhes:
        limite = d.get("limite_espera")
        if limite is not None and d.get("pedidos_espera", 0) > limite:
            partes.append(
                f"Em \"{d['titulo']}\" você pediu espera {d['pedidos_espera']} vezes (o cliente tolera até {limite}); "
                "prefira dar uma posição parcial ao cliente antes de pedir outro momento."
            )
            break
    if simulacao["total_erros"]:
        partes.append(f"Foram {simulacao['total_erros']} erro(s) de português; revise antes de enviar.")
    if any(d.get("status") == "Encerrado pelo cliente" for d in detalhes):
        partes.append("Algum cliente desistiu: responda sempre ao que foi perguntado e mantenha um tom respeitoso.")

    partes.append("Próximo passo: " + _PROXIMO_PASSO[fraca] + ".")
    if modo == "treino":
        partes.append("Quando se sentir seguro, faça uma avaliação para entrar no ranking.")
    else:
        partes.append(f"Refaça \"{pior['titulo']}\" no modo treino e use as dicas.")

    return {"texto": " ".join(partes), "origem": ORIGEM}
