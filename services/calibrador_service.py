"""
Serviço de calibração de processos e desvios de atendimento (Modo Especialista).

Permite que um especialista envie exemplos de respostas corretas (padrão ouro e variações),
extrai automaticamente as âncoras conceituais do procedimento e gerencia desvios comuns
com falas de reforço do cliente simulado.
"""
import re
from difflib import SequenceMatcher
from services.semantica_service import conceitos, similaridade, _radical, STOPWORDS
from services.texto_service import normalizar_texto


def extrair_ancoras(respostas: list) -> list:
    """
    Recebe uma ou mais respostas de referência fornecidas pelo especialista
    e extrai os conceitos/radicais essenciais (âncoras do procedimento).
    
    Se houver 2 ou mais respostas, prioriza os conceitos comuns entre elas
    (a essência do que não pode faltar, independentemente da redação).
    """
    if not respostas:
        return []

    listas_de_conceitos = []
    for r in respostas:
        c = conceitos(r)
        if c:
            listas_de_conceitos.append(c)

    if not listas_de_conceitos:
        return []

    if len(listas_de_conceitos) == 1:
        # Quando há apenas uma resposta, retorna os conceitos mais longos/significativos
        ordenados = sorted(listas_de_conceitos[0], key=lambda x: len(x), reverse=True)
        return ordenados[:8]

    # Interseção: conceitos presentes na maioria das respostas aceitas
    contagem = {}
    total_respostas = len(listas_de_conceitos)
    for grupo in listas_de_conceitos:
        for conc in grupo:
            contagem[conc] = contagem.get(conc, 0) + 1

    # Conceitos presentes em pelo menos metade das respostas do especialista
    limiar = max(2, total_respostas // 2) if total_respostas > 2 else 2
    ancoras = [conc for conc, freq in contagem.items() if freq >= limiar]

    if not ancoras:
        # Fallback: os mais frequentes
        ancoras = sorted(contagem.keys(), key=lambda k: contagem[k], reverse=True)[:6]

    return sorted(ancoras)


def avaliar_resposta_processo(resposta_operador: str, passo: dict) -> dict:
    """
    Avalia a resposta do operador contra as regras de processo do passo:
      - Verifica se cumpre as âncoras obrigatórias
      - Compara similaridade com as respostas aceitas / resposta esperada
      - Detecta se algum desvio mapeado foi disparado
    """
    conceitos_op = conceitos(resposta_operador)
    texto_norm = normalizar_texto(resposta_operador)

    # 1. Similaridade máxima considerando a esperada e todas as aceitas
    candidatas = [passo.get("resposta_esperada", "")] + passo.get("respostas_aceitas", [])
    candidatas = [c for c in candidatas if c]
    
    sim_max = 0.0
    for cand in candidatas:
        s = similaridade(resposta_operador, cand)
        if s > sim_max:
            sim_max = s

    # 2. Checagem de Âncoras
    ancoras = passo.get("ancoras", [])
    ancoras_atendidas = []
    ancoras_faltantes = []

    for anc in ancoras:
        radical_anc = _radical(normalizar_texto(anc))
        if radical_anc in conceitos_op or any(radical_anc in c for c in conceitos_op):
            ancoras_atendidas.append(anc)
        else:
            ancoras_faltantes.append(anc)

    # 3. Detecção de Desvios configurados
    desvios = passo.get("desvios", [])
    desvio_disparado = None

    for d in desvios:
        gatilho = d.get("gatilho", {})
        tipo_gatilho = gatilho.get("tipo", "ancora_faltante")

        # Gatilho por âncora faltante
        if tipo_gatilho == "ancora_faltante":
            termos_necessarios = gatilho.get("termos_faltantes", [])
            # Se qualquer um dos termos necessários estiver ausente na resposta
            faltando = False
            for termo in termos_necessarios:
                rad = _radical(normalizar_texto(termo))
                if rad not in conceitos_op and not any(rad in c for c in conceitos_op):
                    faltando = True
                    break
            if faltando:
                desvio_disparado = d
                break

        # Gatilho por termos proibidos / palavras evasivas
        elif tipo_gatilho == "termos_proibidos":
            proibidos = gatilho.get("termos", [])
            for p in proibidos:
                if normalizar_texto(p) in texto_norm:
                    desvio_disparado = d
                    break
            if desvio_disparado:
                break

        # Gatilho por similaridade com exemplo ruim prévio
        elif tipo_gatilho == "exemplo_ruim":
            exemplo = gatilho.get("exemplo", "")
            if exemplo and similaridade(resposta_operador, exemplo) >= 0.70:
                desvio_disparado = d
                break

    return {
        "similaridade": round(sim_max, 2),
        "ancoras_atendidas": ancoras_atendidas,
        "ancoras_faltantes": ancoras_faltantes,
        "desvio_disparado": desvio_disparado,
        "processo_ok": (len(ancoras_faltantes) == 0 and desvio_disparado is None and sim_max >= 0.50),
    }


def simular_reacao_especialista(resposta_teste: str, passo: dict) -> dict:
    """
    Função utilitária para a interface de calibração: permite que o especialista
    digite uma resposta e veja instantaneamente como o cliente reagiria.
    """
    avaliacao = avaliar_resposta_processo(resposta_teste, passo)
    
    if avaliacao["desvio_disparado"]:
        desvio = avaliacao["desvio_disparado"]
        return {
            "status": "reforco",
            "fala_cliente": desvio.get("reforco_cliente", "Poderia esclarecer melhor?"),
            "motivo": desvio.get("descricao", "Desvio de procedimento detectado."),
            "proxima_esperada": desvio.get("reorientacao_esperada", passo.get("resposta_esperada")),
            "detalhes": avaliacao,
        }
    
    if avaliacao["similaridade"] >= 0.60:
        return {
            "status": "avancar",
            "fala_cliente": "Entendi perfeitamente. Vamos prosseguir.",
            "motivo": "Resposta coerente e dentro do processo.",
            "detalhes": avaliacao,
        }

    return {
        "status": "repetir",
        "fala_cliente": "Desculpe, não entendi como isso responde ao que eu perguntei.",
        "motivo": "Resposta abaixo da coerência mínima esperada.",
        "detalhes": avaliacao,
    }
