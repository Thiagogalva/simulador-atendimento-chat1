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

## Modos: treino e avaliação

Ao iniciar, o operador escolhe o modo (`POST /iniciar`); recarregar a página **não** reinicia a simulação.

| | Treino | Avaliação |
| --- | --- | --- |
| Tempo limite por resposta | não | sim |
| Atendimentos | todos liberados | liberados em sequência |
| Dicas | 2 níveis (pontos a cobrir; resposta sugerida) | não |
| Feedback por resposta | sim (botão) | só ao final |
| Entra no ranking | não | sim |

O navegador **nunca** recebe o roteiro nem as respostas esperadas; dicas e feedback são pedidos ao servidor, que só os entrega no treino.

## Supervisores

Defina os primeiros supervisores em `SUPERVISORES=maria,joao` (logins). Depois eles podem promover outros em `/supervisor`:

- lista de operadores com média, avaliações e treinos; detalhe por operador;
- redefinir senha (gera senha **temporária**, mostrada uma vez; o operador é obrigado a trocá-la);
- desativar/reativar contas (perdem a sessão e saem do ranking) e promover/rebaixar;
- exportar todas as simulações em CSV (com proteção contra injeção de fórmulas);
- trilha de auditoria das ações do painel.

**Esqueci a senha:** no cadastro o operador recebe um **código de recuperação** (mostrado uma vez, só o hash é guardado) e usa `/recuperar` sem precisar de e-mail. Também pode gerar outro em *Conta*. Trocar ou redefinir a senha derruba as outras sessões.

## Cenários editáveis

Os cenários ficam no banco e são gerenciados em `/supervisor/cenarios`: título, ordem, palavras críticas e os passos (fala do cliente + resposta esperada). Na primeira execução eles são carregados de `data/base_atendimentos.py`.

- Editar **não** afeta simulações em andamento (cada atendimento guarda uma cópia do roteiro).
- Cenários arquivados saem das próximas simulações; nunca é possível arquivar o último ativo.
- `CENARIOS_POR_SIMULACAO=N` sorteia N cenários por simulação (padrão 0 = todos). Atenção: sorteio torna o ranking menos comparável, pois cada operador recebe cenários diferentes.

## Feedback por IA (opcional)

Sem configuração, o sistema usa um **feedback local por regras** (notas, palavras que faltaram, tom). Com uma API "compatível com OpenAI" ele passa a gerar um texto de instrutor virtual, com fallback automático para as regras se a IA falhar.

```bash
LLM_PROVEDOR=groq            # groq | gemini | mistral | cerebras | openrouter (ou use LLM_BASE_URL)
LLM_API_KEY=...              # chave do provedor
LLM_MODEL=...                # nome do modelo (confira no provedor: mudam com frequência)
```

- A IA **nunca altera notas**: só escreve o feedback. O `/responder` não chama a IA.
- Há limite por operador (`LLM_LIMITE_POR_HORA`, padrão 30), tempo máximo (`LLM_TIMEOUT`, padrão 12 s) e um disjuntor que pausa as chamadas após falhas (429/5xx/chave inválida).
- Textos de operador, cliente e cenário vão delimitados no prompt como dados não confiáveis (mitigação de injeção de prompt) e a saída é limpa e limitada.
- **Privacidade:** o texto das respostas é enviado ao provedor (nunca nome ou usuário do operador). Alguns planos gratuitos usam os dados para melhorar modelos; use apenas cenários fictícios.

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
| `SUPERVISORES` | vazio | Logins (separados por vírgula) que são sempre supervisores. |
| `CENARIOS_POR_SIMULACAO` | `0` (todos) | Sorteia N cenários ativos por simulação. |
| `LLM_PROVEDOR` / `LLM_BASE_URL` | vazio | Provedor de IA (preset) ou URL base de uma API compatível com OpenAI. |
| `LLM_API_KEY` / `LLM_MODEL` | vazio | Chave e modelo. Sem eles, o feedback é por regras. |
| `LLM_TIMEOUT` / `LLM_LIMITE_POR_HORA` | `12` / `30` | Tempo máximo (s) e feedbacks de IA por operador por hora. |
| `SESSION_COOKIE_SECURE` | automático na Vercel | `1` força cookie só por HTTPS. |
| `FLASK_DEBUG` | desligado | `1` ativa o modo debug. |

`TEMPO_LIMITE_CHAT` e `INTERVALO_ENTRE_CHATS` (segundos) ficam direto em `config.py`.

## Banco de dados

- **Local:** SQLite, sem configuração. O arquivo `simulador.db` não vai para o Git.
- **Produção (persistente):** PostgreSQL via `DATABASE_URL`. Há opções gratuitas (Neon, Supabase). As tabelas são criadas e atualizadas automaticamente na inicialização.
- O mesmo código roda nos dois bancos; os testes passam em ambos.

### Publicar na Vercel (ou outro host)

1. Crie um banco PostgreSQL gratuito (ex.: Neon) e copie a connection string.
2. Na Vercel, em *Settings → Environment Variables*, defina `DATABASE_URL`, `SECRET_KEY`, `SUPERVISORES` e, se quiser, `CODIGO_CONVITE` e as variáveis `LLM_*`.
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
data/             cenários iniciais (carregados no banco na primeira execução)
database/         conexão (SQLite ou PostgreSQL) e criação/migração das tabelas
routes/           login/recuperação (auth), conta, histórico/ranking/finalização (painel) e supervisor
repositories/     acesso ao banco (operadores, simulações, atendimentos, mensagens, avaliações)
services/         regras: texto, semântica, tom, cliente reativo, avaliação, tempo, dicas, cenários, feedback e LLM
tests/            testes automatizados (python -m unittest discover -s tests -t .)
templates/ static/  interface do chat, login, histórico e ranking
```

Para criar ou editar atendimentos use o painel do supervisor (`/supervisor/cenarios`).
