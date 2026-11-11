"""Respaldo de la base de datos y los documentos.

Uso:
    python -m scripts.respaldar "C:\\Users\\Oficina\\Mi unidad\\Respaldos RRHH"
Crea un .zip con fecha y conserva los últimos 30. Pensado para una carpeta de
Google Drive para escritorio, así el respaldo sale de la oficina automáticamente.
"""
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app import config

CONSERVAR = 30


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    destino = Path(sys.argv[1])
    destino.mkdir(parents=True, exist_ok=True)
    if not config.DATABASE_URL.startswith("sqlite"):
        sys.exit("Este respaldo es para SQLite. Con PostgreSQL usa las copias del proveedor.")
    db_path = Path(config.DATABASE_URL.replace("sqlite:///", ""))
    nombre = destino / f"rrhh-minoshkas-{datetime.now():%Y-%m-%d_%H%M}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "rrhh.db"
        # Copia consistente aunque la aplicación esté abierta.
        with sqlite3.connect(db_path) as origen, sqlite3.connect(copia) as dest:
            origen.backup(dest)
        with zipfile.ZipFile(nombre, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copia, "rrhh.db")
            if config.UPLOAD_DIR.exists():
                for f in config.UPLOAD_DIR.rglob("*"):
                    if f.is_file():
                        z.write(f, Path("documentos") / f.relative_to(config.UPLOAD_DIR))
    viejos = sorted(destino.glob("rrhh-minoshkas-*.zip"))[:-CONSERVAR]
    for v in viejos:
        v.unlink()
    print(f"Respaldo creado: {nombre}")


if __name__ == "__main__":
    main()
