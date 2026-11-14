"""Planillas como las maneja Minoshkas: anticipo, fin de mes, administrativa y conciliación."""
import io
import json
import sqlite3
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from app.db import SessionLocal
from app.models import Conciliacion, Empleado, Empresa, Planilla, PlanillaLinea, Sucursal
from tests.conftest import csrf, login

D = Decimal


def _base():
    with SessionLocal() as db:
        isc = Empresa(razon_social="Inversiones Flex, S.A.", nit="111")
        girl = Empresa(razon_social="Minoshkas Flex Girl")
        suc = Sucursal(nombre="Chimaltenango Flex")
        db.add_all([isc, girl, suc])
        db.flush()
        libni = Empleado(nombres="Libni", apellidos="Mux", empresa_id=isc.id, sucursal_id=suc.id, salario_base=D("3816.90"),
                         bonificacion_incentivo=D("250"), salario_real=D("3500"), fecha_ingreso=date(2025, 1, 1))
        vanessa = Empleado(nombres="Vanessa", apellidos="Hernández", empresa_id=girl.id, sucursal_id=suc.id, salario_base=D("3000"),
                           bonificacion_incentivo=D("250"), tiempo="parcial", fecha_ingreso=date(2026, 11, 2))
        suspendida = Empleado(nombres="María", apellidos="Suspendida", empresa_id=isc.id, salario_base=D("3816.90"),
                              bonificacion_incentivo=D("250"), estado="suspendido")
        db.add_all([libni, vanessa, suspendida])
        db.commit()
        return isc.id, girl.id, libni.id, vanessa.id, suspendida.id


def _crear(client, tipo, empresas, anio=2026, mes=11, **extra):
    token = csrf(client, "/planillas")
    datos = {"csrf": token, "tipo": tipo, "empresa_id": [str(x) for x in empresas], "anio": str(anio), "mes": str(mes), **extra}
    r = client.post("/planillas/nueva", data=datos, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def _linea(pid, eid):
    with SessionLocal() as db:
        return db.query(PlanillaLinea).filter_by(planilla_id=pid, empleado_id=eid).one_or_none()


def test_mes_completo_como_el_archivo_v4(client):
    login(client)
    isc, girl, libni, vanessa, susp = _base()

    ant = _crear(client, "anticipo", [isc])
    l = _linea(ant, libni)
    assert l.dias == 15 and l.salario == D("1750.00") and l.igss == 0 and l.liquido == D("1750.00")
    assert _linea(ant, susp) is None  # suspendida por el IGSS no sale por omisión

    fin = _crear(client, "fin_mes", [isc])
    l = _linea(fin, libni)
    assert (l.salario, l.bonificacion, l.igss, l.anticipo, l.liquido) == (D("3816.90"), D("250.00"), D("184.36"), D("1750.00"), D("2132.54"))

    # La administrativa junta a los dos patronos en una sola planilla
    a1 = _crear(client, "admin1", [isc, girl])
    a2 = _crear(client, "admin2", [isc, girl])
    with SessionLocal() as db:
        p = db.get(Planilla, a1)
        assert p.empresa_id is None and {l.nombre_patrono for l in p.lineas} == {"Inversiones Flex, S.A.", "Minoshkas Flex Girl"}
    assert _linea(a1, libni).liquido == D("1750.00")
    # Vanessa entró el 2 de noviembre: 14 días en la 1ra quincena
    assert _linea(a1, vanessa).dias == 14 and _linea(a1, vanessa).liquido == D("1400.00")

    r = client.get("/conciliacion?anio=2026&mes=11")
    assert r.status_code == 200 and "-Q382.54" in r.text
    token = csrf(client, "/conciliacion?anio=2026&mes=11")
    client.post("/conciliacion", data={"csrf": token, "anio": "2026", "mes": "11", f"motivo_{libni}": "Salario reportado distinto al real",
                                       f"explicacion_{libni}": "IGSS con el mínimo"})
    with SessionLocal() as db:
        c = db.query(Conciliacion).filter_by(anio=2026, mes=11, empleado_id=libni).one()
        assert c.motivo == "Salario reportado distinto al real"
    r = client.get("/conciliacion/excel?anio=2026&mes=11")
    valores = [c.value for fila in load_workbook(io.BytesIO(r.content)).active.iter_rows() for c in fila]
    assert -382.54 in valores and "IGSS con el mínimo" in valores

    # Recibos de la administrativa con el patrono de cada persona; filtro por patrono
    r = client.get(f"/planillas/{a1}/recibos?patrono={girl}")
    assert "Minoshkas Flex Girl" in r.text and "Libni" not in r.text


def test_escribir_encima_dias_y_restablecer(client):
    login(client)
    isc, girl, libni, vanessa, susp = _base()
    pid = _crear(client, "admin2", [isc], mes=12)
    l = _linea(pid, libni)
    token = csrf(client, f"/planillas/{pid}")
    # Pagó doble el 1 de noviembre: 16 días, y Q75 de comisiones
    client.post(f"/planillas/{pid}/guardar", data={"csrf": token, f"linea_{l.id}": "1", f"dias_{l.id}": "16", f"salario_{l.id}": str(l.salario),
                                                  f"liquido_{l.id}": str(l.liquido), f"comisiones_{l.id}": "75"})
    l = _linea(pid, libni)
    assert l.dias == 16 and l.salario == D("1866.67") and l.liquido == D("1941.67")
    assert json.loads(l.manual) == {"dias": "16"}

    # Escribe encima del pago; el líquido se recalcula solo
    client.post(f"/planillas/{pid}/guardar", data={"csrf": token, f"linea_{l.id}": "1", f"salario_{l.id}": "1900", f"comisiones_{l.id}": "75"})
    l = _linea(pid, libni)
    assert l.salario == D("1900.00") and l.liquido == D("1975.00")

    # Cambiar la ficha y recalcular respeta lo escrito a mano
    with SessionLocal() as db:
        db.get(Empleado, libni).salario_real = D("4000")
        db.commit()
    client.post(f"/planillas/{pid}/recalcular", data={"csrf": token})
    assert _linea(pid, libni).salario == D("1900.00")

    # Restablecer vuelve al cálculo con la ficha nueva
    client.post(f"/planillas/{pid}/guardar", data={"csrf": token, f"linea_{l.id}": "1", f"reset_{l.id}": "1", f"comisiones_{l.id}": "0"})
    l = _linea(pid, libni)
    assert l.manual == "" and l.dias == 15 and l.salario == D("2000.00") and l.liquido == D("2000.00")

    # Recibo cuadra aunque el líquido se escriba a mano
    client.post(f"/planillas/{pid}/guardar", data={"csrf": token, f"linea_{l.id}": "1", f"liquido_{l.id}": "1950"})
    r = client.get(f"/planillas/{pid}/recibos?linea={l.id}")
    assert "Ajuste" in r.text and "Un mil novecientos cincuenta quetzales" in r.text


def test_agregar_quitar_vacia_reabrir(client):
    login(client)
    isc, girl, libni, vanessa, susp = _base()
    pid = _crear(client, "anticipo", [isc], mes=10, vacia="1")
    with SessionLocal() as db:
        assert db.get(Planilla, pid).lineas == []
    token = csrf(client, f"/planillas/{pid}")
    # Agrega a una de otro patrono y a la suspendida
    client.post(f"/planillas/{pid}/agregar", data={"csrf": token, "empleado_id": [str(vanessa), str(susp)]})
    assert _linea(pid, susp).liquido == D("1908.45")
    # Vanessa todavía no trabajaba en octubre: se agrega con 15 días para que el usuario decida
    assert _linea(pid, vanessa).dias == 15
    lid = _linea(pid, vanessa).id
    client.post(f"/planillas/{pid}/lineas/{lid}/quitar", data={"csrf": token})
    assert _linea(pid, vanessa) is None

    with SessionLocal() as db:
        for l in db.get(Planilla, pid).lineas:
            l.firmado = True
        db.commit()
    client.post(f"/planillas/{pid}/cerrar", data={"csrf": token})
    assert client.post(f"/planillas/{pid}/agregar", data={"csrf": token, "empleado_id": str(libni)}).status_code == 400
    r = client.post(f"/planillas/{pid}/reabrir", data={"csrf": token, "motivo": ""}, follow_redirects=False)
    assert "motivo" in r.headers["location"]
    client.post(f"/planillas/{pid}/reabrir", data={"csrf": token, "motivo": "faltó Libni"})
    with SessionLocal() as db:
        p = db.get(Planilla, pid)
        assert p.estado == "borrador" and "faltó Libni" in p.notas
    assert client.get(f"/planillas/{pid}").status_code == 200
    assert client.get(f"/planillas/{pid}/excel").status_code == 200


def test_migra_base_de_la_version_anterior(tmp_path):
    """Una base creada con la versión del 10 de noviembre se pone al día sin perder planillas."""
    import importlib
    import sqlalchemy

    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE empresas (id INTEGER PRIMARY KEY, razon_social VARCHAR(200), nombre_comercial VARCHAR(200), nit VARCHAR(20),
            numero_patronal_igss VARCHAR(30), erp_id VARCHAR(40), activa BOOLEAN);
        CREATE TABLE empleados (id INTEGER PRIMARY KEY, nombres VARCHAR(120) NOT NULL, salario_base NUMERIC(12,2));
        CREATE TABLE planillas (id INTEGER PRIMARY KEY, tipo VARCHAR(20) NOT NULL, empresa_id INTEGER NOT NULL REFERENCES empresas(id),
            desde DATE NOT NULL, hasta DATE NOT NULL, fecha_pago DATE NOT NULL, estado VARCHAR(20) NOT NULL, notas TEXT NOT NULL,
            creada_por VARCHAR(120) NOT NULL, creada DATETIME NOT NULL, cerrada DATETIME);
        CREATE TABLE planilla_lineas (id INTEGER PRIMARY KEY, planilla_id INTEGER REFERENCES planillas(id), empleado_id INTEGER,
            liquido NUMERIC(12,2));
        INSERT INTO empresas (id, razon_social) VALUES (1, 'ISC');
        INSERT INTO empleados (id, nombres, salario_base) VALUES (1, 'Ana', 3000);
        INSERT INTO planillas VALUES (1, 'quincena1', 1, '2026-11-01', '2026-11-15', '2026-11-15', 'cerrada', '', 'E', '2026-11-15 10:00:00', NULL);
        INSERT INTO planilla_lineas VALUES (1, 1, 1, 1500);
    """)
    con.commit()
    con.close()

    from app import db as modulo_db
    motor = sqlalchemy.create_engine(f"sqlite:///{ruta}")
    original = modulo_db.engine
    modulo_db.engine = motor
    try:
        modulo_db.Base.metadata.create_all(motor)
        modulo_db.migrar()
    finally:
        modulo_db.engine = original
    con = sqlite3.connect(ruta)
    cols = {r[1]: r for r in con.execute("PRAGMA table_info(planillas)")}
    assert cols["empresa_id"][3] == 0  # ya acepta vacío
    assert con.execute("SELECT tipo, estado FROM planillas").fetchall() == [("quincena1", "cerrada")]
    lcols = {r[1] for r in con.execute("PRAGMA table_info(planilla_lineas)")}
    assert {"manual", "anticipo", "comisiones", "empresa_id"} <= lcols
    assert "salario_real" in {r[1] for r in con.execute("PRAGMA table_info(empleados)")}
    fk = con.execute("PRAGMA foreign_key_list(planilla_lineas)").fetchall()
    assert fk[0][2] == "planillas"
    con.close()


def test_ingreso_rapido_y_fin_de_mes_con_dia_doble(client):
    login(client)
    isc, girl, libni, vanessa, susp = _base()
    r = client.get("/empleados/rapido")
    assert r.status_code == 200 and "Salario IGSS" in r.text
    token = csrf(client, "/empleados/rapido")
    with SessionLocal() as db:
        todos = db.query(Empleado).filter(Empleado.estado != "inactivo").all()
        datos = {"csrf": token}
        for e in todos:
            datos.update({f"nombres_{e.id}": e.nombres, f"apellidos_{e.id}": e.apellidos, f"dpi_{e.id}": e.dpi,
                          f"empresa_id_{e.id}": str(e.empresa_id or ""), f"sucursal_id_{e.id}": str(e.sucursal_id or ""),
                          f"puesto_{e.id}": e.puesto, f"tiempo_{e.id}": e.tiempo or "completo",
                          f"fecha_ingreso_{e.id}": e.fecha_ingreso.isoformat() if e.fecha_ingreso else "",
                          f"salario_base_{e.id}": str(e.salario_base), f"bonificacion_incentivo_{e.id}": str(e.bonificacion_incentivo),
                          f"salario_real_{e.id}": str(e.salario_real or ""), f"anticipo_fijo_{e.id}": str(e.anticipo_fijo or ""),
                          f"estado_{e.id}": e.estado})
    datos[f"salario_base_{vanessa}"] = "2400.87"  # tiempo parcial bajo el mínimo
    datos.update({"nombres_n1": "Gressy", "apellidos_n1": "Velazquez", "empresa_id_n1": str(girl), "salario_base_n1": "2000",
                  "bonificacion_incentivo_n1": "139.58", "tiempo_n1": "completo", "estado_n1": "activo"})
    r = client.post("/empleados/rapido", data=datos, follow_redirects=False)
    assert "1+colaborador" in r.headers["location"] or "1 colaborador" in r.headers["location"].replace("+", " ")
    with SessionLocal() as db:
        assert db.get(Empleado, vanessa).salario_base == D("2400.87")
        g = db.query(Empleado).filter_by(nombres="Gressy").one()
        assert g.empresa_id == girl and g.codigo.startswith("MK-")

    pid = _crear(client, "fin_mes", [isc], mes=9)
    l = _linea(pid, libni)
    token = csrf(client, f"/planillas/{pid}")
    client.post(f"/planillas/{pid}/guardar", data={"csrf": token, f"linea_{l.id}": "1", f"dia_doble_{l.id}": "127.23", f"otros_descuentos_{l.id}": "50",
                                                  f"concepto_descuentos_{l.id}": "Pasajes"})
    l = _linea(pid, libni)
    # IGSS sobre salario + día doble; sin anticipo ese mes
    assert l.igss == D("190.50") and l.liquido == D("3816.90") + D("250") + D("127.23") - D("190.50") - D("50")
    r = client.get(f"/planillas/{pid}/recibos?linea={l.id}")
    assert "Día doble" in r.text and "Pasajes" in r.text


def test_montos_con_formato_guatemalteco_y_filtro(client):
    login(client)
    isc, girl, libni, vanessa, susp = _base()
    pid = _crear(client, "admin1", [isc, girl], mes=12)
    l = _linea(pid, vanessa)
    token = csrf(client, f"/planillas/{pid}")
    client.post(f"/planillas/{pid}/guardar", data={"csrf": token, f"linea_{l.id}": "1", f"salario_{l.id}": "Q 1.500,00",
                                                  f"otros_descuentos_{l.id}": "25,50", f"firmado_{l.id}": "1"})
    l = _linea(pid, vanessa)
    assert l.salario == D("1500.00") and l.otros_descuentos == D("25.50") and l.firmado
    # Guardar con filtro por patrono no toca a los del otro patrono
    r = client.get(f"/planillas/{pid}?patrono={isc}")
    assert f'href="/empleados/{libni}"' in r.text and f'href="/empleados/{vanessa}"' not in r.text
    otra = _linea(pid, libni)
    client.post(f"/planillas/{pid}/guardar", data={"csrf": token, f"linea_{otra.id}": "1", f"salario_{otra.id}": str(otra.salario),
                                                  "volver_patrono": str(isc)})
    assert _linea(pid, vanessa).firmado and _linea(pid, vanessa).salario == D("1500.00")
    r = client.get(f"/planillas?patrono={girl}")
    assert f"/planillas/{pid}" in r.text
    r = client.get(f"/empleados/rapido?patrono={girl}")
    assert f'href="/empleados/{vanessa}"' in r.text and f'href="/empleados/{libni}"' not in r.text

    # La ficha acepta "3.000,00" y avisa quién tiene el DPI repetido
    with SessionLocal() as db:
        db.get(Empleado, libni).dpi = "3904306680101"
        db.commit()
    token = csrf(client, f"/empleados/{vanessa}/editar")
    r = client.post(f"/empleados/{vanessa}/editar", data={"csrf": token, "nombres": "Vanessa", "dpi": "3904306680101", "salario_base": "3.000,00",
                                                         "estado": "activo", "tipo_contrato": "indefinido", "jornada": "diurna", "tiempo": "parcial"})
    assert "Libni Mux" in r.text
    r = client.post(f"/empleados/{vanessa}/editar", data={"csrf": token, "nombres": "Vanessa", "dpi": "", "salario_base": "3.000,00",
                                                         "estado": "activo", "tipo_contrato": "indefinido", "jornada": "diurna", "tiempo": "parcial"},
                    follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.get(Empleado, vanessa).salario_base == D("3000.00")
