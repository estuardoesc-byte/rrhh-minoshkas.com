"""Crea o actualiza un usuario administrador.

Uso:
    python -m scripts.crear_usuario "Sandra Marquez" sandra@minoshkas.com
La contraseña se pide en pantalla y no queda guardada en el historial.
"""
import getpass
import sys

from app.auth import hash_password
from app.db import SessionLocal, init_db
from app.models import Usuario


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    nombre, email = sys.argv[1], sys.argv[2].strip().lower()
    password = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
    if len(password) < 10:
        sys.exit("La contraseña debe tener al menos 10 caracteres.")
    if password != getpass.getpass("Repite la contraseña: "):
        sys.exit("Las contraseñas no coinciden.")
    init_db()
    with SessionLocal() as db:
        u = db.query(Usuario).filter(Usuario.email == email).first()
        if u:
            u.nombre, u.password_hash, u.activo = nombre, hash_password(password), True
            print(f"Usuario actualizado: {email}")
        else:
            db.add(Usuario(nombre=nombre, email=email, password_hash=hash_password(password)))
            print(f"Usuario creado: {email}")
        db.commit()


if __name__ == "__main__":
    main()
