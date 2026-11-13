# Simulador de Atendimento Chat

Sistema de simulação de atendimento por chat para treinamento de operadores. Cada resposta é avaliada em:

- **Coerência** – similaridade de *significado* com a resposta esperada do passo: compara conceitos (radicais + sinônimos), pondera pela raridade do termo, detecta negação invertida e tolera erros de digitação; soma frases-chave e palavras críticas exigidas pelo passo;
- **Empatia / tom** – acolhimento, ação, cortesia e próximo passo, com avisos para tom hostil, descaso, culpa do cliente, caixa alta, gírias e respostas repetidas;
- **Tempo** – rapidez da resposta (limite por turno em `TEMPO_LIMITE_CHAT`);
- **Linguagem** – ortografia (pyspellchecker + vocabulário do domínio), abreviações proibidas, letra maiúscula inicial, pontuação final e tamanho mínimo.

Os atendimentos são liberados em sequência (`INTERVALO_ENTRE_CHATS`) e, ao final, é exibido o resultado geral.

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # http://127.0.0.1:5000
```

Em produção: `gunicorn app:app`.

## Configuração (`config.py`)

| Variável de ambiente | Padrão | Descrição |
| --- | --- | --- |
| `SECRET_KEY` | chave de desenvolvimento | **Defina em produção.** |
| `DB_NAME` | `simulador.db` na pasta do projeto (`/tmp/simulador.db` na Vercel) | Caminho do SQLite. |
| `FLASK_DEBUG` | desligado | `1` ativa o modo debug. |

`TEMPO_LIMITE_CHAT` e `INTERVALO_ENTRE_CHATS` (segundos) ficam direto em `config.py`.

> **Hospedagem:** o SQLite grava em arquivo local. Em plataformas serverless (Vercel) o disco é temporário e
> não é compartilhado entre instâncias, então o estado da simulação pode se perder. Prefira um host com disco
> persistente (Render, Railway, PythonAnywhere...) ou troque o SQLite por um banco externo.

## Estrutura

```
app.py            rotas Flask (/ e /responder)
config.py         configurações
data/             roteiros dos atendimentos (BASE_ATENDIMENTOS)
database/         conexão e criação das tabelas
repositories/     acesso ao banco (usuários, atendimentos, mensagens, avaliações)
services/         regras: texto (ortografia), semântica, tom, avaliação (notas), tempo
tests/            testes automatizados (python -m unittest discover -s tests -t .)
templates/ static/  interface do chat
```

Para incluir um novo atendimento, adicione um item em `data/base_atendimentos.py` (e, se quiser bônus por
palavras críticas, uma entrada em `PALAVRAS_CRITICAS` em `services/texto_service.py`).
