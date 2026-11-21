import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Em produção defina a variável de ambiente SECRET_KEY.
SECRET_KEY_PADRAO = "dev-only-troque-em-producao"
SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY_PADRAO)

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

# Banco persistente (PostgreSQL). Se vazio, usa SQLite em DB_NAME.
# Ex.: postgresql://usuario:senha@host/banco?sslmode=require  (Neon, Supabase, Render, Railway...)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


# Código secreto que libera a área do supervisor (/supervisor/entrar). Sem ele a área fica desativada.
SUPERVISOR_CODIGO = os.environ.get("SUPERVISOR_CODIGO", "").strip()
SUPERVISOR_SESSAO_HORAS = float(os.environ.get("SUPERVISOR_SESSAO_HORAS", "8") or 8)

# Quantos nomes NOVOS um mesmo IP pode criar por hora (evita encher o ranking com nomes falsos).
NOMES_NOVOS_POR_HORA = int(os.environ.get("NOMES_NOVOS_POR_HORA", "30") or 30)

# Cookies de sessão: Lax contra CSRF; Secure quando servido por HTTPS (Vercel ou SESSION_COOKIE_SECURE=1).
SESSION_COOKIE_SECURE = bool(os.environ.get("VERCEL")) or os.environ.get("SESSION_COOKIE_SECURE") == "1"
