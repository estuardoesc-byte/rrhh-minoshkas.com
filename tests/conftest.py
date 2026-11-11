import os
import re
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/docs"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Empresa, Sucursal, Usuario  # noqa: E402


@pytest.fixture(scope="session")
def client():
    init_db()
    with SessionLocal() as db:
        db.add(Usuario(nombre="Prueba", email="prueba@minoshkas.com", password_hash=hash_password("clave-segura-1")))
        db.add(Empresa(razon_social="Patrono Prueba"))
        db.add(Sucursal(nombre="7ma"))
        db.commit()
    with TestClient(app) as c:
        yield c


def csrf(c, url="/login"):
    return re.search(r'name="csrf" value="([^"]+)"', c.get(url).text).group(1)


def login(c):
    r = c.post("/login", data={"email": "prueba@minoshkas.com", "password": "clave-segura-1", "csrf": csrf(c)}, follow_redirects=False)
    assert r.status_code == 303
