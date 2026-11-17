import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Em produção defina a variável de ambiente SECRET_KEY.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-troque-em-producao")

# Em ambientes serverless (Vercel) apenas /tmp é gravável.
_DB_PADRAO = "/tmp/simulador.db" if os.environ.get("VERCEL") else os.path.join(_BASE_DIR, "simulador.db")
DB_NAME = os.environ.get("DB_NAME", _DB_PADRAO)

TEMPO_LIMITE_CHAT = 50
INTERVALO_ENTRE_CHATS = 50

# Debug só quando FLASK_DEBUG=1 (o debugger do Werkzeug não deve ficar exposto em 0.0.0.0).
DEBUG = os.environ.get("FLASK_DEBUG") == "1"

# Quantos cenários cada simulação sorteia entre os ativos (0 = todos, na ordem definida).
# Atenção: sortear faz operadores diferentes receberem cenários diferentes, o que torna o ranking menos comparável.
CENARIOS_POR_SIMULACAO = int(os.environ.get("CENARIOS_POR_SIMULACAO", "0") or 0)

# ---- Feedback por IA (opcional). Qualquer API compatível com "chat/completions" da OpenAI.
# Provedores com plano gratuito: groq, gemini, mistral, cerebras, openrouter (limites e modelos mudam; confira no provedor).
# ATENÇÃO: o texto das respostas dos operadores é enviado ao provedor; alguns planos gratuitos usam os dados para treino.
_PROVEDORES_LLM = {
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "mistral": "https://api.mistral.ai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
LLM_PROVEDOR = os.environ.get("LLM_PROVEDOR", "").strip().lower()
LLM_BASE_URL = (os.environ.get("LLM_BASE_URL", "").strip() or _PROVEDORES_LLM.get(LLM_PROVEDOR, "")).rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "").strip()
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "12") or 12)
LLM_LIMITE_POR_HORA = int(os.environ.get("LLM_LIMITE_POR_HORA", "30") or 30)

# Banco persistente (PostgreSQL). Se vazio, usa SQLite em DB_NAME.
# Ex.: postgresql://usuario:senha@host/banco?sslmode=require  (Neon, Supabase, Render, Railway...)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Se definido, o cadastro de operadores exige este código de convite.
CODIGO_CONVITE = os.environ.get("CODIGO_CONVITE", "").strip()

# Usuários (logins) que são sempre supervisores, separados por vírgula. Serve para criar o primeiro supervisor.
SUPERVISORES = frozenset(
    u.strip().lower() for u in os.environ.get("SUPERVISORES", "").split(",") if u.strip()
)

# Cookies de sessão: Lax contra CSRF; Secure quando servido por HTTPS (Vercel ou SESSION_COOKIE_SECURE=1).
SESSION_COOKIE_SECURE = bool(os.environ.get("VERCEL")) or os.environ.get("SESSION_COOKIE_SECURE") == "1"
