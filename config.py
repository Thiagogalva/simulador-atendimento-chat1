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
