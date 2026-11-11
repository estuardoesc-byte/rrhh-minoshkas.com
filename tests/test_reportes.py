import io
import re
from decimal import Decimal

from openpyxl import load_workbook

from app.letras import monto_en_letras
from tests.conftest import csrf, login
from app.db import SessionLocal
from app.models import Empleado, Empresa, Planilla


def test_monto_en_letras():
    assert monto_en_letras(Decimal("1941.27")) == "Un mil novecientos cuarenta y un quetzales con 27/100"
    assert monto_en_letras(Decimal("1")) == "Un quetzal con 00/100"
    assert monto_en_letras(Decimal("21")) == "Veintiún quetzales con 00/100"
    assert monto_en_letras(Decimal("100")) == "Cien quetzales con 00/100"
    assert monto_en_letras(Decimal("3816.90")) == "Tres mil ochocientos dieciséis quetzales con 90/100"
    assert monto_en_letras(Decimal("15190.20")) == "Quince mil ciento noventa quetzales con 20/100"


def _planilla(client):
    login(client)
    with SessionLocal() as db:
        emp = Empresa(razon_social="Patrono Reportes", nit="123")
        db.add(emp)
        db.flush()
        db.add(Empleado(nombres="Recibo", apellidos="Uno", empresa_id=emp.id, salario_base=Decimal("3816.90"),
                        bonificacion_incentivo=Decimal("250")))
        db.commit()
        emp_id = emp.id
    token = csrf(client, "/planillas")
    r = client.post("/planillas/nueva", data={"csrf": token, "tipo": "quincena2", "empresa_id": str(emp_id), "anio": "2026", "mes": "10"},
                    follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_recibos_excel_y_gerencial(client):
    pid = _planilla(client)
    r = client.get(f"/planillas/{pid}/recibos")
    assert r.status_code == 200
    assert "Recibo Uno" in r.text and "Un mil novecientos cuarenta y un quetzales con 27/100" in r.text

    r = client.get(f"/planillas/{pid}/excel")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.active
    valores = [c.value for fila in ws.iter_rows() for c in fila]
    assert "Recibo Uno" in valores and 1941.27 in valores

    r = client.get("/reportes/gerencial?anio=2026&mes=10")
    assert r.status_code == 200 and "Patrono Reportes" in r.text
    r = client.get("/reportes/gerencial/excel?anio=2026&mes=10")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Por sucursal", "Por patrono"]
    r = client.get("/provisiones/excel?anio=2026&mes=10")
    assert r.status_code == 200
