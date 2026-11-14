# Simulador de Atendimento Chat

Sistema de simulação de atendimento por chat para treinamento de operadores. Cada resposta é avaliada em:

- **Coerência** – similaridade de *significado* com a resposta esperada do passo: compara conceitos (radicais + sinônimos), pondera pela raridade do termo, detecta negação invertida e tolera erros de digitação; soma frases-chave e palavras críticas exigidas pelo passo;
- **Empatia / tom** – acolhimento, ação, cortesia e próximo passo, com avisos para tom hostil, descaso, culpa do cliente, caixa alta, gírias e respostas repetidas;
- **Tempo** – rapidez da resposta (limite por turno em `TEMPO_LIMITE_CHAT`);
- **Linguagem** – ortografia (pyspellchecker + vocabulário do domínio), abreviações proibidas, letra maiúscula inicial, pontuação final e tamanho mínimo.

## Cliente simulado reativo

Cada cliente tem um nível de irritação (0-100) e um humor (**calmo**, **impaciente**, **atritado**) exibido no painel e nas bolhas de mensagem:

- resposta **fora de contexto, seca, hostil ou gritando** → o cliente reage e **repete a pergunta** (o passo não avança);
- resposta **incompleta, com descaso, gíria ou repetida** → o cliente segue, mas comenta o problema;
- resposta **boa** → o cliente se acalma e o atendimento avança;
- irritação ≥ 85, ou 3 falhas no mesmo passo → o cliente **desiste e pede um supervisor** (atendimento encerrado, nota com penalidade).

As regras ficam em `services/cliente_service.py` (determinísticas, sem API) e as frases podem ser editadas lá.

Os atendimentos são liberados em sequência (`INTERVALO_ENTRE_CHATS`) e, ao final, é exibido o resultado geral.

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # http://127.0.0.1:5000
```

Em produção: `gunicorn app:app`.

## Contas, histórico e ranking

- Cada operador tem **usuário + senha** (senha guardada com hash). Rotas protegidas: tudo, exceto `/login` e `/registro`.
- Ao terminar uma simulação, o resultado é **salvo no histórico** (`/historico`): notas, evolução em gráfico e detalhe por atendimento. O cálculo é feito no servidor; o navegador não envia nota nenhuma.
- `/ranking` ordena os operadores pela média das notas (geral, 30 dias ou 7 dias). Só o **nome de exibição** é público.
- Proteções: bloqueio temporário após 5 logins errados, cookie de sessão `HttpOnly` + `SameSite=Lax` (+ `Secure` em HTTPS), mensagens de erro que não revelam se o usuário existe.
- Para restringir quem pode se cadastrar, defina `CODIGO_CONVITE`.

## Configuração

| Variável de ambiente | Padrão | Descrição |
| --- | --- | --- |
| `SECRET_KEY` | chave de desenvolvimento | **Defina em produção** (use um valor longo e aleatório). |
| `DATABASE_URL` | vazio (usa SQLite) | URL do PostgreSQL, ex.: `postgresql://usuario:senha@host/banco?sslmode=require`. |
| `DB_NAME` | `simulador.db` na pasta do projeto | Arquivo do SQLite (usado quando não há `DATABASE_URL`). |
| `CODIGO_CONVITE` | vazio | Se definido, o cadastro exige este código. |
| `SESSION_COOKIE_SECURE` | automático na Vercel | `1` força cookie só por HTTPS. |
| `FLASK_DEBUG` | desligado | `1` ativa o modo debug. |

`TEMPO_LIMITE_CHAT` e `INTERVALO_ENTRE_CHATS` (segundos) ficam direto em `config.py`.

## Banco de dados

- **Local:** SQLite, sem configuração. O arquivo `simulador.db` não vai para o Git.
- **Produção (persistente):** PostgreSQL via `DATABASE_URL`. Há opções gratuitas (Neon, Supabase). As tabelas são criadas e atualizadas automaticamente na inicialização.
- O mesmo código roda nos dois bancos; os testes passam em ambos.

### Publicar na Vercel (ou outro host)

1. Crie um banco PostgreSQL gratuito (ex.: Neon) e copie a connection string.
2. Na Vercel, em *Settings → Environment Variables*, defina `DATABASE_URL`, `SECRET_KEY` e (opcional) `CODIGO_CONVITE`.
3. Faça o deploy. Sem `DATABASE_URL`, o SQLite ficaria em `/tmp` e os dados se perderiam.

## Testes

```bash
python -m unittest discover -s tests -t .                       # SQLite temporário
TEST_DATABASE_URL=postgresql://... python -m unittest discover -s tests -t .   # PostgreSQL de TESTE
```

Os testes ignoram `DATABASE_URL` de propósito (criam operadores e simulações); para PostgreSQL use `TEST_DATABASE_URL` com um banco de teste, nunca o de produção.

## Estrutura

```
app.py            app Flask: simulador (/ e /responder) e proteção de login
config.py         configurações
data/             roteiros dos atendimentos (BASE_ATENDIMENTOS)
database/         conexão (SQLite ou PostgreSQL) e criação/migração das tabelas
routes/           login/cadastro (auth) e histórico, ranking e finalização (painel)
repositories/     acesso ao banco (operadores, simulações, atendimentos, mensagens, avaliações)
services/         regras: texto (ortografia), semântica, tom, cliente reativo, avaliação (notas), tempo
tests/            testes automatizados (python -m unittest discover -s tests -t .)
templates/ static/  interface do chat, login, histórico e ranking
```

Para incluir um novo atendimento, adicione um item em `data/base_atendimentos.py` (e, se quiser bônus por
palavras críticas, uma entrada em `PALAVRAS_CRITICAS` em `services/texto_service.py`).
