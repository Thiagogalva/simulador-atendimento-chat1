import os
import tempfile

# Banco temporário compartilhado pelos testes (precisa ser definido antes de importar config/app).
if "DB_NAME" not in os.environ:
    _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmp.close()
    os.environ["DB_NAME"] = _tmp.name
