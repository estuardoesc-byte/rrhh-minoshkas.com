"""Configuración leída de variables de entorno."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(archivo: Path) -> None:
    """Lee un archivo .env sencillo (CLAVE=valor) sin pisar variables ya definidas."""
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"'))


_cargar_env(BASE_DIR / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'datos' / 'rrhh.db'}")
# Algunos proveedores entregan postgres:// y SQLAlchemy espera postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.environ.get("SECRET_KEY", "cambiar-esta-clave-en-produccion")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "datos" / "documentos"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "10"))
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
# En producción (HTTPS) la cookie de sesión solo viaja cifrada.
HTTPS_ONLY = os.environ.get("HTTPS_ONLY", "0") == "1"
DIAS_ALERTA_TARJETA_SALUD = 30
