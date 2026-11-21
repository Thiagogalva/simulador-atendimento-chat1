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

## Identificação e supervisor (sem login)

O sistema roda dentro de uma plataforma interna de aprendizado, então **não há login nem senha**: o operador só informa o **nome** no início (`/identificar`). O nome é usado no histórico e no ranking.

- O mesmo nome, escrito de formas diferentes ("João Silva", "joao  SILVA"), é a mesma pessoa. Use sempre o mesmo nome para manter histórico e posição.
- "Trocar nome" (no topo e no chat) encerra a identificação, útil em computador compartilhado.
- Como não há autenticação, **qualquer pessoa pode digitar o nome de outra**. Em ambiente interno isso costuma ser aceitável; se o ranking precisar ser à prova de fraude, o ideal é a plataforma enviar a identidade já autenticada.
- Limite de **nomes novos por IP por hora** (`NOMES_NOVOS_POR_HORA`, padrão 30) evita encher o ranking com nomes falsos.

### Como acessar a área do supervisor

A área do supervisor (`/supervisor`) é protegida por um **código secreto definido no servidor**, não por conta:

1. Quem administra o sistema define duas variáveis de ambiente e reinicia a aplicação:
   - `SUPERVISOR_CODIGO` = o código secreto (à sua escolha);
   - `SECRET_KEY` = um texto longo e aleatório (sem ela a área fica desativada por segurança).
2. O supervisor informa o nome normalmente, clica em **"Área do supervisor"** no topo e digita o código (`/supervisor/entrar`).
3. A liberação dura `SUPERVISOR_SESSAO_HORAS` (padrão 8) e some ao trocar de nome ou clicar em "Sair do modo supervisor".

Sem `SUPERVISOR_CODIGO` a área fica desativada. O código errado bloqueia temporariamente após 5 tentativas.

No painel o supervisor vê operadores com média, avaliações e treinos; **bloqueia/desbloqueia um nome** (sai do ranking e perde a sessão); exporta CSV (com proteção contra injeção de fórmulas); gerencia cenários; e tem uma trilha de auditoria das ações.

## Cenários editáveis

Os cenários ficam no banco e são gerenciados em `/supervisor/cenarios`: título, ordem, palavras críticas e os passos (fala do cliente + resposta esperada). Na primeira execução eles são carregados de `data/base_atendimentos.py`.

- Editar **não** afeta simulações em andamento (cada atendimento guarda uma cópia do roteiro).
- Cenários arquivados saem das próximas simulações; nunca é possível arquivar o último ativo.
- **Regras de conduta por cenário:** no formulário do cenário o supervisor liga o controle de **pedidos de espera** ("um momento", "só um instante", "já retorno") e define quantos o cliente tolera (padrão 2). Até o limite o cliente aceita ("Tudo bem, aguardo"); a partir do seguinte reclama, depois fica atritado e, se o operador insistir, desiste. Pedir espera não conta como resposta (não gera nota nem faz o cliente repetir a pergunta). O limite é uma regra escondida: só aparece no treino, nunca na avaliação. Os pedidos entram no histórico e no feedback final.
- `CENARIOS_POR_SIMULACAO=N` sorteia N cenários por simulação (padrão 0 = todos). Atenção: sorteio torna o ranking menos comparável, pois cada operador recebe cenários diferentes.

## Inteligência local (sem IA paga, sem chaves)

Tudo é processado dentro do sistema; nenhuma chamada de rede é feita para avaliar, reagir ou gerar feedback.

- **Compreensão do texto:** radicais (snowball), grupos de sinônimos, peso por raridade do termo, negação invertida e tolerância a erro de digitação.
- **Tom e cliente reativo:** acolhimento, ação, cortesia, descaso, caixa alta etc.; o cliente se irrita, repete a pergunta ou desiste.
- **Feedback em texto** (botão no treino; análise final no histórico): mostra ideias que o operador cobriu e as que faltaram, a estrutura da resposta (acolher, agir, informar prazo, cortesia) e, no final, a evolução em relação à simulação anterior e o ponto mais fraco. É gerado por regras, então é determinístico e fica em cache. Só elogia com evidência segura e só cobra o que realmente não aparece.

### Camada opcional de PLN (spaCy)

Para reconhecer sinônimos que não estão na lista (ex.: "conferir" ≈ "verificar") e escolher melhores pistas, instale a camada opcional:

```bash
pip install -r requirements-nlp.txt     # spaCy + modelo pt_core_news_md (roda offline)
```

| | Sem spaCy (padrão) | Com spaCy |
| --- | --- | --- |
| Instalação | só `requirements.txt` | + `requirements-nlp.txt` (~380 MB de disco) |
| Memória | leve | +~320 MB de RAM (carrega em ~1,5 s) |
| Sinônimos | lista de sinônimos | lista + vetores de palavras |
| Onde roda bem | qualquer host, inclusive Vercel | servidores com folga de memória/disco |

Os vetores só ajudam na **nota** (crédito parcial, com pareamento um-para-um para uma palavra não valer duas ideias). Eles são estáticos e podem aproximar palavras raras parecidas na forma; por isso o feedback não afirma nada com base só neles. `NLP_DESATIVAR=1` desliga a camada mesmo instalada.

## Histórico e ranking

- Ao terminar uma simulação, o resultado é **salvo no histórico** (`/historico`): notas, evolução em gráfico e detalhe por atendimento. O cálculo é feito no servidor; o navegador não envia nota nenhuma.
- `/ranking` ordena os operadores pela média das notas das **avaliações** (geral, 30 dias ou 7 dias). Só o nome de exibição aparece.
- Proteções: cookie de sessão `HttpOnly` + `SameSite=Lax` (+ `Secure` em HTTPS) e proteção CSRF nos formulários.

## Configuração

| Variável de ambiente | Padrão | Descrição |
| --- | --- | --- |
| `SECRET_KEY` | chave de desenvolvimento | **Defina em produção** (valor longo e aleatório). Sem ela a área do supervisor fica desativada. |
| `SUPERVISOR_CODIGO` | vazio | Código secreto que libera a área do supervisor. Sem ele a área fica desativada. |
| `SUPERVISOR_SESSAO_HORAS` | `8` | Duração da liberação do supervisor. |
| `NOMES_NOVOS_POR_HORA` | `30` | Nomes novos que um mesmo IP pode criar por hora. |
| `DATABASE_URL` | vazio (usa SQLite) | URL do PostgreSQL, ex.: `postgresql://usuario:senha@host/banco?sslmode=require`. |
| `DB_NAME` | `simulador.db` na pasta do projeto | Arquivo do SQLite (usado quando não há `DATABASE_URL`). |
| `CENARIOS_POR_SIMULACAO` | `0` (todos) | Sorteia N cenários ativos por simulação. |
| `NLP_DESATIVAR` | vazio | `1` desliga a camada opcional de spaCy. |
| `SPACY_MODELO` | `pt_core_news_md` | Modelo spaCy a carregar (se instalado). |
| `SESSION_COOKIE_SECURE` | automático na Vercel | `1` força cookie só por HTTPS. |
| `FLASK_DEBUG` | desligado | `1` ativa o modo debug. |

`TEMPO_LIMITE_CHAT` e `INTERVALO_ENTRE_CHATS` (segundos) ficam direto em `config.py`.

## Banco de dados

- **Local:** SQLite, sem configuração. O arquivo `simulador.db` não vai para o Git.
- **Produção (persistente):** PostgreSQL via `DATABASE_URL`. Há opções gratuitas (Neon, Supabase). As tabelas são criadas e atualizadas automaticamente na inicialização.
- O mesmo código roda nos dois bancos; os testes passam em ambos.

### Publicar na Vercel (ou outro host)

1. Crie um banco PostgreSQL gratuito (ex.: Neon) e copie a connection string.
3. Faça o deploy. Sem `DATABASE_URL`, o SQLite ficaria em `/tmp` e os dados se perderiam.

## Testes

```bash
python -m unittest discover -s tests -t .                       # SQLite temporário
TEST_DATABASE_URL=postgresql://... python -m unittest discover -s tests -t .   # PostgreSQL de TESTE
NLP_DESATIVAR=1 python -m unittest discover -s tests -t .       # sem a camada spaCy (testes dela são pulados)
```

Os testes ignoram `DATABASE_URL` de propósito (criam operadores e simulações); para PostgreSQL use `TEST_DATABASE_URL` com um banco de teste, nunca o de produção.

## Estrutura

```
app.py            app Flask: simulador (/ e /responder) e exigência do nome
config.py         configurações
data/             cenários iniciais (carregados no banco na primeira execução)
database/         conexão (SQLite ou PostgreSQL) e criação/migração das tabelas
routes/           identificação por nome (auth), histórico/ranking/finalização (painel) e supervisor
repositories/     acesso ao banco (operadores, simulações, atendimentos, mensagens, avaliações)
services/         regras: texto, semântica, PLN opcional (spaCy), tom, cliente reativo, avaliação, tempo, dicas, cenários e feedback
tests/            testes automatizados (python -m unittest discover -s tests -t .)
templates/ static/  interface do chat, identificação, histórico e ranking
```

Para criar ou editar atendimentos use o painel do supervisor (`/supervisor/cenarios`).
