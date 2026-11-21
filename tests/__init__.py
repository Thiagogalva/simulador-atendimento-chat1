import os
import tempfile

# Os testes criam operadores e simulações: NUNCA devem usar o banco real.
# Ignoram DATABASE_URL do ambiente; para testar em PostgreSQL use TEST_DATABASE_URL (um banco de teste!).
os.environ.pop("DATABASE_URL", None)
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

# A área do supervisor só abre com código e SECRET_KEY não padrão: valores de teste (nunca os reais).
os.environ["SUPERVISOR_CODIGO"] = "codigo-de-teste-supervisor"
os.environ.setdefault("SECRET_KEY", "chave-de-teste-nao-usar-em-producao")
os.environ["NOMES_NOVOS_POR_HORA"] = "100000"  # a suíte cria centenas de operadores a partir do mesmo IP

if "DB_NAME" not in os.environ:
    _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmp.close()
    os.environ["DB_NAME"] = _tmp.name
