import os
import re
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/docs"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Documento, Empleado, Empresa, Parametro, Sucursal, Usuario  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture(scope="module")
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


def test_sin_sesion_redirige_a_login(client):
    r = client.get("/empleados", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_incorrecto(client):
    r = client.post("/login", data={"email": "prueba@minoshkas.com", "password": "mala", "csrf": csrf(client)})
    assert "incorrectos" in r.text


def test_formulario_sin_csrf_es_rechazado(client):
    login(client)
    r = client.post("/empleados/nuevo", data={"nombres": "X"})
    assert r.status_code == 403


def _nuevo(client, **extra):
    datos = {
        "csrf": csrf(client, "/empleados/nuevo"), "nombres": "Ana", "apellidos": "López", "dpi": "1234 56789 0101",
        "salario_base": "3816.90", "bonificacion_incentivo": "250", "estado": "activo", "tipo_contrato": "indefinido",
        "jornada": "diurna", "fecha_ingreso": "2026-10-22", "empresa_id": "1", "sucursal_id": "1",
    }
    datos.update(extra)
    return client.post("/empleados/nuevo", data=datos, follow_redirects=False)


def test_crear_editar_y_historial(client):
    login(client)
    r = _nuevo(client)
    assert r.status_code == 303
    eid = int(r.headers["location"].rsplit("/", 1)[1])
    with SessionLocal() as db:
        e = db.get(Empleado, eid)
        assert e.dpi == "1234567890101" and e.codigo == f"MK-{eid:04d}"

    # DPI duplicado
    r = _nuevo(client)
    assert "Ya existe un colaborador con ese DPI" in r.text

    form = csrf(client, f"/empleados/{eid}/editar")
    r = client.post(f"/empleados/{eid}/editar", data={
        "csrf": form, "nombres": "Ana", "apellidos": "López", "dpi": "1234567890101", "salario_base": "4000",
        "estado": "activo", "tipo_contrato": "indefinido", "jornada": "diurna", "empresa_id": "1", "sucursal_id": "1",
    }, follow_redirects=False)
    assert r.status_code == 303
    ficha = client.get(f"/empleados/{eid}").text
    assert "Salario base" in ficha and "4000.00" in ficha


def test_validaciones(client):
    login(client)
    r = _nuevo(client, dpi="123", nombres="Beto")
    assert "13 dígitos" in r.text
    r = _nuevo(client, dpi="", nombres="Beto", tipo_contrato="plazo fijo")
    assert "fecha de finalización" in r.text
    with SessionLocal() as db:
        db.get(Parametro, "salario_minimo_no_agricola_c2").valor = "3800.00"
        db.commit()
    r = _nuevo(client, dpi="", nombres="Beto", salario_base="2000")
    assert "menor al salario mínimo" in r.text


def test_subir_ver_y_eliminar_documento(client):
    login(client)
    with SessionLocal() as db:
        eid = db.query(Empleado).first().id
    token = csrf(client, f"/empleados/{eid}")
    r = client.post(f"/empleados/{eid}/documentos", data={"csrf": token, "tipo": "foto"},
                    files={"archivo": ("foto.png", PNG, "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        d = db.query(Documento).filter_by(empleado_id=eid).one()
        did = d.id
        assert (Path(os.environ["UPLOAD_DIR"]) / d.archivo).exists()
    assert client.get(f"/documentos/{did}").content == PNG

    r = client.post(f"/empleados/{eid}/documentos", data={"csrf": token, "tipo": "cv"},
                    files={"archivo": ("malo.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400

    r = client.post(f"/documentos/{did}/eliminar", data={"csrf": token}, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.get(Documento, did) is None


def test_paginas_principales(client):
    login(client)
    for url in ["/", "/empleados", "/empresas", "/sucursales", "/parametros", "/empleados/nuevo"]:
        assert client.get(url).status_code == 200, url


CSV_ERP = (
    "id,empresaId,nombre,dpi,nit,igss,tarjetaSalud,tarjetaSaludVence,puesto,sucursalId,colaboradoraId,fechaIngreso,"
    "vacPrevias,salarioBase,bonificacion,cuentaBanco,telefono,direccion,emergencia,estado,fechaBaja,motivoBaja,notas,updatedAt,deleted,_srv\n"
    "e-1,e-x,Maria  Ejemplo Uno,1111 22222 0303,,,,2027-01-31,Estilista,s-x,k-1,2026-10-22,3,\"3816,9\",250,,5555,Zona 1,,activo,,,nota uno,1,,1\n"
    "e-2,e-x,Rosa Ejemplo Dos,123,,,,,Recepcionista,s-zz,k-2,2025-01-15,0,4000,250,,,,,activo,,,,1,,1\n"
    "e-3,e-x,Borrada Ejemplo,,,,,,,s-x,,,,,,,,,,activo,,,,1,TRUE,1\n"
    "e-4,e-x,Copia DPI,1111222220303,,,,,,s-x,,,,,,,,,,activo,,,,1,,1\n"
)


def test_importar_desde_erp(client):
    login(client)
    with SessionLocal() as db:
        db.add(Empresa(razon_social="Patrono ERP", erp_id="e-x"))
        db.add(Sucursal(nombre="Sucursal ERP", erp_id="s-x"))
        db.commit()
    token = csrf(client, "/importar")
    r = client.post("/importar", data={"csrf": token}, files={"archivo": ("empleados.csv", CSV_ERP.encode(), "text/csv")})
    assert r.status_code == 200
    assert "Nuevos" in r.text
    with SessionLocal() as db:
        uno = db.query(Empleado).filter_by(erp_id="e-1").one()
        assert uno.nombres == "Maria Ejemplo Uno"
        assert uno.dpi == "1111222220303"
        assert str(uno.salario_base) == "3816.90"
        assert uno.vacaciones_previas == 3
        assert uno.empresa.erp_id == "e-x" and uno.sucursal.erp_id == "s-x"
        dos = db.query(Empleado).filter_by(erp_id="e-2").one()
        assert dos.dpi == "" and "123" in dos.notas and dos.sucursal_id is None
        assert db.query(Empleado).filter_by(erp_id="e-3").count() == 0
        assert db.query(Empleado).filter_by(erp_id="e-4").count() == 0
    assert "no tiene 13 dígitos" in r.text and "ya pertenece" in r.text and "no encontrada" in r.text

    # Reimportar no duplica ni sobrescribe
    r = client.post("/importar", data={"csrf": token}, files={"archivo": ("empleados.csv", CSV_ERP.encode(), "text/csv")})
    with SessionLocal() as db:
        assert db.query(Empleado).filter_by(erp_id="e-1").count() == 1


def test_importar_archivo_equivocado(client):
    login(client)
    token = csrf(client, "/importar")
    r = client.post("/importar", data={"csrf": token}, files={"archivo": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert "no parece ser la hoja" in r.text
