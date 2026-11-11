"""Aplicación web del sistema de RRHH de Minoshkas."""
import mimetypes
from contextlib import asynccontextmanager
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .auth import LoginRequired, autenticar, csrf_token, usuario_actual, verificar_csrf
from .db import get_db, init_db
from .models import (
    ESTADOS_CIVILES,
    ESTADOS_EMPLEADO,
    JORNADAS,
    NOMBRES_DOCUMENTO,
    PARAMETROS_INICIALES,
    TIPOS_CONTRATO,
    TIPOS_DOCUMENTO,
    Documento,
    Empleado,
    ErpExcluido,
    Empresa,
    HistorialEmpleado,
    Parametro,
    Sucursal,
    Usuario,
)

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app):
    _startup()
    yield


app = FastAPI(title="RRHH Minoshkas", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="rrhh_sesion",
    max_age=60 * 60 * 10,
    same_site="lax",
    https_only=config.HTTPS_ONLY,
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


def quetzales(valor) -> str:
    try:
        v = Decimal(valor)
        return f"-Q{-v:,.2f}" if v < 0 else f"Q{v:,.2f}"
    except (InvalidOperation, TypeError):
        return "Q0.00"


def fecha_gt(valor) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""


templates.env.filters["q"] = quetzales
templates.env.filters["fecha"] = fecha_gt


def _startup():
    init_db()
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    from .db import SessionLocal

    with SessionLocal() as db:
        for clave, (valor, desc) in PARAMETROS_INICIALES.items():
            if not db.get(Parametro, clave):
                db.add(Parametro(clave=clave, valor=valor, descripcion=desc))
        db.commit()


@app.exception_handler(LoginRequired)
def _login_required(request: Request, exc: LoginRequired):
    return RedirectResponse("/login", status_code=303)


def render(request: Request, nombre: str, user: Usuario | None = None, **ctx):
    ctx.update(request=request, user=user, csrf=csrf_token(request), hoy=date.today())
    return templates.TemplateResponse(request, nombre, ctx)


def requiere_usuario(request: Request, db: Session = Depends(get_db)) -> Usuario:
    return usuario_actual(request, db)


async def form_con_csrf(request: Request) -> dict:
    form = await request.form()
    verificar_csrf(request, form.get("csrf"))
    return form


def parametro(db: Session, clave: str) -> Decimal:
    p = db.get(Parametro, clave)
    try:
        return Decimal(p.valor) if p else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


# ---------------------------------------------------------------- acceso


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return render(request, "login.html")


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    verificar_csrf(request, csrf)
    user = autenticar(db, email, password)
    if not user:
        return render(request, "login.html", error="Correo o contraseña incorrectos.", email=email)
    request.session.clear()
    request.session["uid"] = user.id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: str = Form("")):
    verificar_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------- inicio


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    hoy = date.today()
    limite = hoy + timedelta(days=config.DIAS_ALERTA_TARJETA_SALUD)
    activos = db.query(Empleado).filter(Empleado.estado == "activo")

    por_sucursal = (
        db.query(Sucursal.nombre, func.count(Empleado.id))
        .outerjoin(Empleado, (Empleado.sucursal_id == Sucursal.id) & (Empleado.estado == "activo"))
        .group_by(Sucursal.id)
        .order_by(Sucursal.nombre)
        .all()
    )
    por_empresa = (
        db.query(Empresa.razon_social, func.count(Empleado.id))
        .outerjoin(Empleado, (Empleado.empresa_id == Empresa.id) & (Empleado.estado == "activo"))
        .group_by(Empresa.id)
        .order_by(Empresa.razon_social)
        .all()
    )

    tarjetas = (
        activos.filter(or_(Empleado.tarjeta_salud_vence.is_(None), Empleado.tarjeta_salud_vence <= limite))
        .order_by(Empleado.tarjeta_salud_vence)
        .all()
    )
    contratos = (
        activos.filter(
            Empleado.tipo_contrato != "indefinido",
            Empleado.fecha_fin_contrato.is_not(None),
            Empleado.fecha_fin_contrato <= limite,
        )
        .order_by(Empleado.fecha_fin_contrato)
        .all()
    )
    minimo = parametro(db, "salario_minimo_no_agricola_c2")
    bajo_minimo = activos.filter(Empleado.salario_base < minimo).all() if minimo > 0 else []
    sin_patrono = activos.filter(Empleado.empresa_id.is_(None)).all()

    tipos_clave = {"foto", "dpi_frente", "contrato", "tarjeta_salud"}
    incompletos = []
    for e in activos.all():
        faltan = tipos_clave - {d.tipo for d in e.documentos}
        if faltan:
            incompletos.append((e, sorted(NOMBRES_DOCUMENTO[t] for t in faltan)))

    return render(
        request,
        "inicio.html",
        user,
        total_activos=activos.count(),
        por_sucursal=por_sucursal,
        por_empresa=por_empresa,
        tarjetas=tarjetas,
        contratos=contratos,
        bajo_minimo=bajo_minimo,
        minimo=minimo,
        sin_patrono=sin_patrono,
        incompletos=incompletos,
    )


# ---------------------------------------------------------------- empleados

CAMPOS_TEXTO = [
    "codigo", "nombres", "apellidos", "dpi", "nit", "afiliacion_igss", "sexo", "estado_civil",
    "nacionalidad", "direccion", "telefono", "email", "nivel_academico", "puesto", "tipo_contrato",
    "jornada", "estado", "motivo_baja", "emergencia_nombre", "emergencia_parentesco",
    "emergencia_telefono", "beneficiarios", "tarjeta_salud_numero", "notas",
]
CAMPOS_FECHA = ["fecha_nacimiento", "fecha_ingreso", "fecha_fin_contrato", "fecha_baja", "tarjeta_salud_vence"]
CAMPOS_DINERO = ["salario_base", "bonificacion_incentivo"]
CAMPOS_ENTERO = ["numero_hijos", "vacaciones_previas"]
CAMPOS_FK = ["empresa_id", "sucursal_id"]
CAMPOS_HISTORIAL = {
    "salario_base": "Salario base",
    "bonificacion_incentivo": "Bonificación incentivo",
    "puesto": "Puesto",
    "sucursal_id": "Sucursal",
    "empresa_id": "Patrono",
    "estado": "Estado",
}


def _leer_empleado(form, db: Session) -> tuple[dict, list[str]]:
    datos, errores = {}, []
    for c in CAMPOS_TEXTO:
        datos[c] = (form.get(c) or "").strip()
    for c in CAMPOS_FECHA:
        v = (form.get(c) or "").strip()
        try:
            datos[c] = date.fromisoformat(v) if v else None
        except ValueError:
            errores.append(f"Fecha inválida en {c.replace('_', ' ')}.")
            datos[c] = None
    for c in CAMPOS_DINERO:
        v = (form.get(c) or "0").replace(",", "").replace("Q", "").strip() or "0"
        try:
            datos[c] = Decimal(v).quantize(Decimal("0.01"))
            if datos[c] < 0:
                raise InvalidOperation
        except InvalidOperation:
            errores.append(f"Monto inválido en {c.replace('_', ' ')}.")
            datos[c] = Decimal("0")
    for c in CAMPOS_ENTERO:
        v = (form.get(c) or "0").strip() or "0"
        datos[c] = int(v) if v.isdigit() else 0
    for c in CAMPOS_FK:
        v = (form.get(c) or "").strip()
        datos[c] = int(v) if v.isdigit() else None

    if not datos["nombres"]:
        errores.append("El nombre es obligatorio.")
    dpi = datos["dpi"].replace(" ", "")
    if dpi and (not dpi.isdigit() or len(dpi) != 13):
        errores.append("El DPI debe tener 13 dígitos.")
    datos["dpi"] = dpi
    if datos["estado"] not in ESTADOS_EMPLEADO:
        datos["estado"] = "activo"
    if datos["estado"] == "retirado" and not datos["fecha_baja"]:
        errores.append("Indica la fecha de baja del colaborador retirado.")
    if datos["tipo_contrato"] != "indefinido" and not datos["fecha_fin_contrato"]:
        errores.append("Un contrato a plazo fijo u obra determinada necesita fecha de finalización.")
    minimo = parametro(db, "salario_minimo_no_agricola_c2")
    if minimo > 0 and datos["salario_base"] < minimo and datos["jornada"] == "diurna":
        errores.append(f"El salario base es menor al salario mínimo vigente ({quetzales(minimo)}).")
    return datos, errores


def _opciones(db: Session) -> dict:
    return dict(
        empresas=db.query(Empresa).filter(Empresa.activa).order_by(Empresa.razon_social).all(),
        sucursales=db.query(Sucursal).filter(Sucursal.activa).order_by(Sucursal.nombre).all(),
        estados=ESTADOS_EMPLEADO,
        contratos=TIPOS_CONTRATO,
        jornadas=JORNADAS,
        estados_civiles=ESTADOS_CIVILES,
    )


def _texto_campo(db: Session, campo: str, valor) -> str:
    if valor is None:
        return ""
    if campo == "sucursal_id":
        s = db.get(Sucursal, valor)
        return s.nombre if s else ""
    if campo == "empresa_id":
        e = db.get(Empresa, valor)
        return e.razon_social if e else ""
    return str(valor)


@app.get("/empleados", response_class=HTMLResponse)
def empleados(
    request: Request,
    q: str = "",
    sucursal: str = "",
    empresa: str = "",
    estado: str = "activo",
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_usuario),
):
    consulta = db.query(Empleado)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(
            or_(Empleado.nombres.ilike(patron), Empleado.apellidos.ilike(patron), Empleado.dpi.ilike(patron), Empleado.codigo.ilike(patron))
        )
    if sucursal.isdigit():
        consulta = consulta.filter(Empleado.sucursal_id == int(sucursal))
    if empresa.isdigit():
        consulta = consulta.filter(Empleado.empresa_id == int(empresa))
    if estado in ESTADOS_EMPLEADO:
        consulta = consulta.filter(Empleado.estado == estado)
    lista = consulta.order_by(Empleado.nombres, Empleado.apellidos).all()
    return render(
        request, "empleados.html", user, lista=lista, q=q, f_sucursal=sucursal, f_empresa=empresa, f_estado=estado, **_opciones(db)
    )


@app.get("/empleados/nuevo", response_class=HTMLResponse)
def empleado_nuevo(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    e = Empleado(
        nombres="", estado="activo", tipo_contrato="indefinido", jornada="diurna",
        bonificacion_incentivo=parametro(db, "bonificacion_incentivo"), nacionalidad="guatemalteca",
    )
    return render(request, "empleado_form.html", user, e=e, nuevo=True, errores=[], **_opciones(db))


@app.post("/empleados/nuevo")
async def empleado_crear(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    form = await form_con_csrf(request)
    datos, errores = _leer_empleado(form, db)
    if datos["dpi"] and db.query(Empleado).filter(Empleado.dpi == datos["dpi"]).first():
        errores.append("Ya existe un colaborador con ese DPI.")
    if errores:
        return render(request, "empleado_form.html", user, e=Empleado(**datos), nuevo=True, errores=errores, **_opciones(db))
    e = Empleado(**datos)
    db.add(e)
    db.flush()
    if not e.codigo:
        e.codigo = f"MK-{e.id:04d}"
    db.add(HistorialEmpleado(empleado_id=e.id, campo="Alta", valor_nuevo=f"Ingreso {fecha_gt(e.fecha_ingreso)}", usuario=user.nombre))
    db.commit()
    return RedirectResponse(f"/empleados/{e.id}", status_code=303)


def _empleado_o_404(db: Session, eid: int) -> Empleado:
    e = db.get(Empleado, eid)
    if not e:
        raise HTTPException(404, "Colaborador no encontrado")
    return e


@app.get("/empleados/{eid}", response_class=HTMLResponse)
def empleado_ficha(eid: int, request: Request, aviso: str = "", db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    e = _empleado_o_404(db, eid)
    return render(request, "empleado_ficha.html", user, e=e, tipos=TIPOS_DOCUMENTO, nombres_doc=NOMBRES_DOCUMENTO,
                  max_mb=config.MAX_UPLOAD_MB, aviso=aviso)


@app.get("/empleados/{eid}/editar", response_class=HTMLResponse)
def empleado_editar_form(eid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    e = _empleado_o_404(db, eid)
    return render(request, "empleado_form.html", user, e=e, nuevo=False, errores=[], **_opciones(db))


@app.post("/empleados/{eid}/editar")
async def empleado_editar(eid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    e = _empleado_o_404(db, eid)
    form = await form_con_csrf(request)
    datos, errores = _leer_empleado(form, db)
    if datos["dpi"] and db.query(Empleado).filter(Empleado.dpi == datos["dpi"], Empleado.id != e.id).first():
        errores.append("Ya existe otro colaborador con ese DPI.")
    if errores:
        borrador = Empleado(**datos)
        borrador.id = e.id
        return render(request, "empleado_form.html", user, e=borrador, nuevo=False, errores=errores, **_opciones(db))
    for campo, etiqueta in CAMPOS_HISTORIAL.items():
        antes, despues = getattr(e, campo), datos[campo]
        if str(antes or "") != str(despues or ""):
            db.add(HistorialEmpleado(
                empleado_id=e.id, campo=etiqueta,
                valor_anterior=_texto_campo(db, campo, antes), valor_nuevo=_texto_campo(db, campo, despues),
                usuario=user.nombre,
            ))
    for k, v in datos.items():
        setattr(e, k, v)
    if not e.codigo:
        e.codigo = f"MK-{e.id:04d}"
    db.commit()
    return RedirectResponse(f"/empleados/{e.id}", status_code=303)


@app.post("/empleados/{eid}/estado")
async def empleado_activar(eid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    """Desactiva (deja de aparecer en listas y planillas, conserva todo) o vuelve a activar."""
    await form_con_csrf(request)
    e = _empleado_o_404(db, eid)
    nuevo = "activo" if e.estado == "inactivo" else "inactivo"
    db.add(HistorialEmpleado(empleado_id=e.id, campo="Estado", valor_anterior=e.estado, valor_nuevo=nuevo, usuario=user.nombre))
    e.estado = nuevo
    db.commit()
    return RedirectResponse(f"/empleados/{e.id}", status_code=303)


@app.post("/empleados/{eid}/eliminar")
async def empleado_eliminar(eid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    """Borra un registro equivocado o duplicado. Si ya tiene planillas, solo se puede desactivar."""
    await form_con_csrf(request)
    e = _empleado_o_404(db, eid)
    if db.query(PlanillaLinea).filter(PlanillaLinea.empleado_id == e.id).first():
        return RedirectResponse(f"/empleados/{e.id}?aviso=con_planillas", status_code=303)
    for d in list(e.documentos):
        _borrar_archivo(d)
        db.delete(d)
    db.query(HistorialEmpleado).filter(HistorialEmpleado.empleado_id == e.id).delete()
    if e.erp_id and not db.get(ErpExcluido, e.erp_id):
        db.add(ErpExcluido(erp_id=e.erp_id, nombre=e.nombre_completo, eliminado_por=user.nombre))
    db.delete(e)
    db.commit()
    return RedirectResponse("/empleados", status_code=303)


# ---------------------------------------------------------------- documentos


@app.post("/empleados/{eid}/documentos")
async def documento_subir(
    eid: int,
    request: Request,
    tipo: str = Form(...),
    descripcion: str = Form(""),
    csrf: str = Form(""),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_usuario),
):
    verificar_csrf(request, csrf)
    e = _empleado_o_404(db, eid)
    if tipo not in TIPOS_DOCUMENTO:
        raise HTTPException(400, "Tipo de documento inválido")
    ext = Path(archivo.filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Solo se aceptan archivos PDF, JPG o PNG.")
    if tipo == "foto" and ext == ".pdf":
        raise HTTPException(400, "La foto del colaborador debe ser JPG o PNG.")
    contenido = await archivo.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(contenido) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"El archivo supera {config.MAX_UPLOAD_MB} MB.")
    if not contenido:
        raise HTTPException(400, "El archivo está vacío.")
    carpeta = config.UPLOAD_DIR / str(e.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{tipo}-{uuid.uuid4().hex}{ext}"
    (carpeta / nombre).write_bytes(contenido)
    if tipo == "foto":
        # Solo una foto vigente por colaborador.
        for viejo in [d for d in e.documentos if d.tipo == "foto"]:
            _borrar_archivo(viejo)
            db.delete(viejo)
    db.add(Documento(
        empleado_id=e.id, tipo=tipo, descripcion=descripcion.strip()[:200],
        nombre_original=(archivo.filename or nombre)[:250], archivo=f"{e.id}/{nombre}",
        mime=mimetypes.guess_type(nombre)[0] or "application/octet-stream", tamano=len(contenido),
        subido_por=user.nombre,
    ))
    db.commit()
    return RedirectResponse(f"/empleados/{e.id}#documentos", status_code=303)


def _ruta_documento(d: Documento) -> Path:
    ruta = (config.UPLOAD_DIR / d.archivo).resolve()
    if config.UPLOAD_DIR.resolve() not in ruta.parents:
        raise HTTPException(404)
    return ruta


def _borrar_archivo(d: Documento) -> None:
    try:
        _ruta_documento(d).unlink(missing_ok=True)
    except HTTPException:
        pass


@app.get("/documentos/{did}")
def documento_ver(did: int, descargar: int = 0, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    d = db.get(Documento, did)
    if not d:
        raise HTTPException(404)
    ruta = _ruta_documento(d)
    if not ruta.exists():
        raise HTTPException(404, "El archivo ya no existe en el servidor")
    return FileResponse(
        ruta, media_type=d.mime, filename=d.nombre_original,
        content_disposition_type="attachment" if descargar else "inline",
    )


@app.post("/documentos/{did}/eliminar")
async def documento_eliminar(did: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    await form_con_csrf(request)
    d = db.get(Documento, did)
    if not d:
        raise HTTPException(404)
    eid = d.empleado_id
    db.add(HistorialEmpleado(empleado_id=eid, campo="Documento eliminado", valor_anterior=f"{d.nombre_tipo}: {d.nombre_original}", usuario=user.nombre))
    _borrar_archivo(d)
    db.delete(d)
    db.commit()
    return RedirectResponse(f"/empleados/{eid}#documentos", status_code=303)


# ---------------------------------------------------------------- patronos y sucursales


@app.get("/empresas", response_class=HTMLResponse)
def empresas(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    lista = db.query(Empresa).order_by(Empresa.razon_social).all()
    return render(request, "empresas.html", user, lista=lista)


@app.post("/empresas")
async def empresa_guardar(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    form = await form_con_csrf(request)
    eid = (form.get("id") or "").strip()
    emp = db.get(Empresa, int(eid)) if eid.isdigit() else Empresa()
    if emp is None:
        raise HTTPException(404)
    emp.razon_social = (form.get("razon_social") or "").strip()
    if not emp.razon_social:
        raise HTTPException(400, "La razón social es obligatoria")
    emp.nombre_comercial = (form.get("nombre_comercial") or "").strip()
    emp.nit = (form.get("nit") or "").strip()
    emp.numero_patronal_igss = (form.get("numero_patronal_igss") or "").strip()
    emp.activa = form.get("activa") == "1"
    db.add(emp)
    db.commit()
    return RedirectResponse("/empresas", status_code=303)


@app.get("/sucursales", response_class=HTMLResponse)
def sucursales(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    lista = db.query(Sucursal).order_by(Sucursal.nombre).all()
    return render(request, "sucursales.html", user, lista=lista)


@app.post("/sucursales")
async def sucursal_guardar(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    form = await form_con_csrf(request)
    sid = (form.get("id") or "").strip()
    s = db.get(Sucursal, int(sid)) if sid.isdigit() else Sucursal()
    if s is None:
        raise HTTPException(404)
    s.nombre = (form.get("nombre") or "").strip()
    if not s.nombre:
        raise HTTPException(400, "El nombre es obligatorio")
    for c in ("codigo", "direccion", "municipio", "departamento"):
        setattr(s, c, (form.get(c) or "").strip())
    s.activa = form.get("activa") == "1"
    db.add(s)
    db.commit()
    return RedirectResponse("/sucursales", status_code=303)


# ---------------------------------------------------------------- parámetros legales


@app.get("/parametros", response_class=HTMLResponse)
def parametros(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    lista = db.query(Parametro).order_by(Parametro.clave).all()
    return render(request, "parametros.html", user, lista=lista)


@app.post("/parametros")
async def parametros_guardar(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    form = await form_con_csrf(request)
    for p in db.query(Parametro).all():
        v = (form.get(p.clave) or "").replace(",", "").strip()
        if not v:
            continue
        try:
            Decimal(v)
        except InvalidOperation:
            raise HTTPException(400, f"Valor inválido para {p.descripcion}")
        p.valor = v
    db.commit()
    return RedirectResponse("/parametros", status_code=303)


# ---------------------------------------------------------------- importación desde el ERP


@app.get("/importar", response_class=HTMLResponse)
def importar_form(request: Request, user: Usuario = Depends(requiere_usuario)):
    return render(request, "importar.html", user, resultado=None, error=None)


@app.post("/importar", response_class=HTMLResponse)
async def importar(
    request: Request,
    csrf: str = Form(""),
    actualizar: str = Form(""),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_usuario),
):
    verificar_csrf(request, csrf)
    from .importar import importar_csv

    contenido = await archivo.read(5 * 1024 * 1024 + 1)
    if len(contenido) > 5 * 1024 * 1024:
        return render(request, "importar.html", user, resultado=None, error="El archivo supera 5 MB.")
    try:
        resultado = importar_csv(db, contenido, user.nombre, actualizar=actualizar == "1")
    except ValueError as exc:
        db.rollback()
        return render(request, "importar.html", user, resultado=None, error=str(exc))
    return render(request, "importar.html", user, resultado=resultado, error=None)


# ---------------------------------------------------------------- planillas (paso 3)

import json  # noqa: E402
from calendar import monthrange  # noqa: E402

from . import calculos  # noqa: E402
from .models import TIPOS_PLANILLA, Planilla, PlanillaLinea  # noqa: E402

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def tasas_vigentes(db: Session) -> calculos.Tasas:
    return calculos.Tasas(
        igss_laboral=parametro(db, "igss_laboral_pct"),
        igss_patronal=parametro(db, "igss_patronal_pct"),
        irtra=parametro(db, "irtra_pct"),
        intecap=parametro(db, "intecap_pct"),
    )


def _decimal(valor, defecto=Decimal("0")) -> Decimal:
    try:
        return Decimal(str(valor or "0").replace(",", "").replace("Q", "").strip() or "0")
    except InvalidOperation:
        return defecto


def _entero_form(valor) -> int:
    v = str(valor or "0").strip()
    return int(v) if v.isdigit() else 0


def empleados_del_periodo(db: Session, empresa_id: int, desde: date, hasta: date) -> list[Empleado]:
    lista = db.query(Empleado).filter(Empleado.empresa_id == empresa_id).order_by(Empleado.nombres).all()
    return [
        e for e in lista
        if e.estado != "inactivo"
        and (e.fecha_ingreso is None or e.fecha_ingreso <= hasta)
        and (e.estado != "retirado" or (e.fecha_baja and e.fecha_baja >= desde))
    ]


def calcular_linea(linea: PlanillaLinea, planilla: Planilla, e: Empleado, tasas: calculos.Tasas) -> None:
    linea.salario_base = e.salario_base
    linea.sucursal_nombre = e.sucursal.nombre if e.sucursal else ""
    baja = e.fecha_baja if e.estado == "retirado" else None
    if planilla.tipo in ("quincena1", "quincena2"):
        trabajados = calculos.dias_laborados(e.fecha_ingreso, baja, planilla.desde, planilla.hasta)
        fuera = calculos.dias_inclusivos(planilla.desde, planilla.hasta) - trabajados
        q = calculos.calcular_quincena(
            e.salario_base, e.bonificacion_incentivo, tasas,
            dias_no_laborados=linea.dias_no_laborados or 0, dias_fuera_de_contrato=fuera,
            otros_ingresos=linea.otros_ingresos or Decimal("0"), otros_descuentos=linea.otros_descuentos or Decimal("0"),
        )
        linea.dias = max(trabajados - (linea.dias_no_laborados or 0), 0)
        linea.salario, linea.bonificacion, linea.igss, linea.isr = q.salario, q.bonificacion, q.igss, q.isr
        linea.liquido = q.liquido
        linea.patronal = calculos.cuota_patronal(q.salario + q.otros_ingresos, tasas)
    else:  # bono 14 o aguinaldo: exentos de IGSS e ISR
        dias, monto = calculos.prestacion_anual(e.salario_base, e.fecha_ingreso, baja, planilla.desde, planilla.hasta)
        linea.dias, linea.salario, linea.bonificacion = dias, monto, Decimal("0")
        linea.igss = linea.isr = linea.patronal = Decimal("0")
        linea.liquido = monto + (linea.otros_ingresos or 0) - (linea.otros_descuentos or 0)


@app.get("/planillas", response_class=HTMLResponse)
def planillas(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    lista = db.query(Planilla).order_by(Planilla.fecha_pago.desc(), Planilla.id.desc()).limit(200).all()
    hoy = date.today()
    return render(
        request, "planillas.html", user, lista=lista, tipos={k: v for k, v in TIPOS_PLANILLA.items() if k != "liquidacion"},
        empresas=db.query(Empresa).filter(Empresa.activa).order_by(Empresa.razon_social).all(),
        meses=MESES, anio=hoy.year, mes=hoy.month, error=request.query_params.get("error"),
    )


@app.post("/planillas/nueva")
async def planilla_crear(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    form = await form_con_csrf(request)
    tipo = form.get("tipo")
    empresa_ids = [int(x) for x in form.getlist("empresa_id") if str(x).isdigit()]
    anio, mes = _entero_form(form.get("anio")), _entero_form(form.get("mes"))
    if tipo not in TIPOS_PLANILLA or tipo == "liquidacion" or not empresa_ids or not (2000 <= anio <= 2100) or not (1 <= mes <= 12):
        return RedirectResponse("/planillas?error=Revisa+el+tipo,+el+patrono+y+el+período", status_code=303)
    if tipo == "quincena1":
        desde, hasta = calculos.periodo_quincena(anio, mes, 1)
        pago = hasta
    elif tipo == "quincena2":
        desde, hasta = calculos.periodo_quincena(anio, mes, 2)
        pago = hasta
    elif tipo == "bono14":
        pago = date(anio, 7, 15)
        desde, hasta = calculos.periodo_bono14(pago)
    else:
        pago = date(anio, 12, 15)
        desde, hasta = calculos.periodo_aguinaldo(pago)
    tasas = tasas_vigentes(db)
    creada = None
    for empresa_id in empresa_ids:
        if db.query(Planilla).filter_by(tipo=tipo, empresa_id=empresa_id, desde=desde, hasta=hasta).first():
            continue
        p = Planilla(tipo=tipo, empresa_id=empresa_id, desde=desde, hasta=hasta, fecha_pago=pago, creada_por=user.nombre)
        for e in empleados_del_periodo(db, empresa_id, desde, hasta):
            linea = PlanillaLinea(empleado=e)
            calcular_linea(linea, p, e, tasas)
            if linea.dias > 0:
                p.lineas.append(linea)
        if not p.lineas:
            continue  # patrono sin colaboradores en el período
        db.add(p)
        db.flush()
        creada = creada or p
    db.commit()
    if not creada:
        return RedirectResponse("/planillas?error=Esa+planilla+ya+existe+o+el+patrono+no+tiene+colaboradores+en+el+período", status_code=303)
    return RedirectResponse(f"/planillas/{creada.id}" if len(empresa_ids) == 1 else "/planillas", status_code=303)


def _planilla_o_404(db: Session, pid: int) -> Planilla:
    p = db.get(Planilla, pid)
    if not p:
        raise HTTPException(404, "Planilla no encontrada")
    return p


@app.get("/planillas/{pid}", response_class=HTMLResponse)
def planilla_ver(pid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    p = _planilla_o_404(db, pid)
    conceptos = {l.id: json.loads(l.detalle) for l in p.lineas if l.detalle}
    return render(request, "planilla.html", user, p=p, conceptos=conceptos, error=request.query_params.get("error"))


@app.post("/planillas/{pid}/guardar")
async def planilla_guardar(pid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    form = await form_con_csrf(request)
    p = _planilla_o_404(db, pid)
    if p.estado == "cerrada":
        raise HTTPException(400, "La planilla está cerrada y no se puede modificar.")
    tasas = tasas_vigentes(db)
    for linea in p.lineas:
        if p.tipo != "liquidacion":
            linea.dias_no_laborados = _entero_form(form.get(f"dnl_{linea.id}"))
            linea.otros_ingresos = _decimal(form.get(f"oi_{linea.id}"))
            linea.otros_descuentos = _decimal(form.get(f"od_{linea.id}"))
            calcular_linea(linea, p, linea.empleado, tasas)
        linea.firmado = form.get(f"firmado_{linea.id}") == "1"
    p.notas = (form.get("notas") or "").strip()
    db.commit()
    return RedirectResponse(f"/planillas/{p.id}", status_code=303)


@app.post("/planillas/{pid}/cerrar")
async def planilla_cerrar(pid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    await form_con_csrf(request)
    p = _planilla_o_404(db, pid)
    pendientes = [l for l in p.lineas if not l.firmado]
    if pendientes:
        return RedirectResponse(f"/planillas/{p.id}?error=Faltan+{len(pendientes)}+recibos+por+firmar", status_code=303)
    p.estado, p.cerrada = "cerrada", datetime.now()
    db.commit()
    return RedirectResponse(f"/planillas/{p.id}", status_code=303)


@app.post("/planillas/{pid}/eliminar")
async def planilla_eliminar(pid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    await form_con_csrf(request)
    p = _planilla_o_404(db, pid)
    if p.estado == "cerrada":
        raise HTTPException(400, "Una planilla cerrada no se puede eliminar.")
    db.delete(p)
    db.commit()
    return RedirectResponse("/planillas", status_code=303)


# ---------------------------------------------------------------- liquidaciones


def _form_liquidacion(form, e: Empleado) -> dict:
    baja = None
    try:
        baja = date.fromisoformat(form.get("fecha_baja") or "")
    except ValueError:
        pass
    baja = baja or date.today()
    pagados_hasta = None
    try:
        pagados_hasta = date.fromisoformat(form.get("pagado_hasta") or "")
    except ValueError:
        pass
    if pagados_hasta is None:
        inicio_q = date(baja.year, baja.month, 1 if baja.day <= 15 else 16)
        pagados_hasta = inicio_q - timedelta(days=1)
    dias_pend = max((baja - pagados_hasta).days, 0)
    ingreso = e.fecha_ingreso or baja
    vac_def = calculos.vacaciones_proporcionales(ingreso, baja) + Decimal(e.vacaciones_previas or 0)
    return dict(
        tipo=form.get("tipo") if form.get("tipo") in calculos.TIPOS_TERMINACION else "renuncia",
        fecha_baja=baja,
        pagado_hasta=pagados_hasta,
        dias_pendientes=dias_pend,
        salario_promedio=_decimal(form.get("salario_promedio"), e.salario_base) if form.get("salario_promedio") else e.salario_base,
        dias_vacaciones=_decimal(form.get("dias_vacaciones")) if form.get("dias_vacaciones") else vac_def,
        otros_descuentos=_decimal(form.get("otros_descuentos")),
        monto_pactado=_decimal(form.get("monto_pactado")),
        motivo=(form.get("motivo") or "").strip(),
    )


def _calcular_liq(db: Session, e: Empleado, d: dict) -> calculos.Liquidacion:
    return calculos.calcular_liquidacion(
        tipo=d["tipo"], ingreso=e.fecha_ingreso or d["fecha_baja"], baja=d["fecha_baja"],
        salario_base=e.salario_base, bonificacion=e.bonificacion_incentivo, salario_promedio=d["salario_promedio"],
        tasas=tasas_vigentes(db), dias_salario_pendiente=d["dias_pendientes"],
        dias_vacaciones_pendientes=d["dias_vacaciones"], otros_descuentos=d["otros_descuentos"],
        monto_pactado=d["monto_pactado"],
    )


@app.get("/empleados/{eid}/liquidacion", response_class=HTMLResponse)
def liquidacion_form(eid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    e = _empleado_o_404(db, eid)
    d = _form_liquidacion(request.query_params, e)
    liq = _calcular_liq(db, e, d) if e.fecha_ingreso else None
    return render(request, "liquidacion.html", user, e=e, d=d, liq=liq, tipos=calculos.TIPOS_TERMINACION)


@app.post("/empleados/{eid}/liquidacion")
async def liquidacion_guardar(eid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    form = await form_con_csrf(request)
    e = _empleado_o_404(db, eid)
    if not e.fecha_ingreso or not e.empresa_id:
        raise HTTPException(400, "El colaborador necesita fecha de ingreso y patrono para liquidarlo.")
    d = _form_liquidacion(form, e)
    liq = _calcular_liq(db, e, d)
    p = Planilla(
        tipo="liquidacion", empresa_id=e.empresa_id, desde=e.fecha_ingreso, hasta=d["fecha_baja"],
        fecha_pago=date.today(), creada_por=user.nombre,
        notas=f"{calculos.TIPOS_TERMINACION[d['tipo']]}. {d['motivo']}".strip(),
    )
    linea = PlanillaLinea(
        empleado_id=e.id, salario_base=e.salario_base, sucursal_nombre=e.sucursal.nombre if e.sucursal else "",
        dias=calculos.dias_inclusivos(e.fecha_ingreso, d["fecha_baja"]), salario=liq.total, liquido=liq.total,
        detalle=json.dumps([[n, str(v)] for n, v in liq.conceptos], ensure_ascii=False),
    )
    p.lineas.append(linea)
    db.add(p)
    for campo, valor in (("Estado", "retirado"),):
        db.add(HistorialEmpleado(empleado_id=e.id, campo=campo, valor_anterior=e.estado, valor_nuevo=valor, usuario=user.nombre))
    e.estado, e.fecha_baja = "retirado", d["fecha_baja"]
    e.motivo_baja = calculos.TIPOS_TERMINACION[d["tipo"]] + (f": {d['motivo']}" if d["motivo"] else "")
    db.commit()
    return RedirectResponse(f"/planillas/{p.id}", status_code=303)


# ---------------------------------------------------------------- provisiones


@app.get("/provisiones", response_class=HTMLResponse)
def provisiones(request: Request, anio: int = 0, mes: int = 0, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    hoy = date.today()
    anio, mes = anio or hoy.year, mes or hoy.month
    desde, hasta = date(anio, mes, 1), date(anio, mes, monthrange(anio, mes)[1])
    tasas = tasas_vigentes(db)
    grupos = []
    for emp in db.query(Empresa).order_by(Empresa.razon_social).all():
        filas = []
        for e in empleados_del_periodo(db, emp.id, desde, hasta):
            baja = e.fecha_baja if e.estado == "retirado" else None
            dias = calculos.dias_laborados(e.fecha_ingreso, baja, desde, hasta)
            if dias <= 0:
                continue
            salario_mes = calculos.r2(e.salario_base * dias / calculos.dias_inclusivos(desde, hasta))
            prov = calculos.provision_mensual(salario_mes)
            filas.append(dict(e=e, salario=salario_mes, patronal=calculos.cuota_patronal(salario_mes, tasas), **prov))
        if filas:
            totales = {k: sum((f[k] for f in filas), Decimal("0")) for k in ("salario", "aguinaldo", "bono14", "vacaciones", "indemnizacion", "patronal")}
            grupos.append(dict(empresa=emp, filas=filas, totales=totales))
    return render(request, "provisiones.html", user, grupos=grupos, anio=anio, mes=mes, meses=MESES)


# ---------------------------------------------------------------- recibos, Excel y reportes (paso 4)

from fastapi.responses import Response  # noqa: E402

from . import excel  # noqa: E402
from .letras import monto_en_letras  # noqa: E402

templates.env.filters["letras"] = monto_en_letras
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _descarga_excel(contenido: bytes, nombre: str) -> Response:
    return Response(contenido, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@app.get("/planillas/{pid}/recibos", response_class=HTMLResponse)
def planilla_recibos(pid: int, request: Request, linea: int = 0, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    p = _planilla_o_404(db, pid)
    lineas = [l for l in p.lineas if not linea or l.id == linea]
    conceptos = {l.id: json.loads(l.detalle) for l in lineas if l.detalle}
    return render(request, "recibos.html", user, p=p, lineas=lineas, conceptos=conceptos)


def _filas_planilla(p: Planilla):
    quincena = p.tipo in ("quincena1", "quincena2")
    if quincena:
        cols = [("Código", "t"), ("Colaborador", "t"), ("DPI", "t"), ("Sucursal", "t"), ("Días", "n"), ("Días no laborados", "n"),
                ("Salario", "q"), ("Bonificación", "q"), ("Otros ingresos", "q"), ("Total devengado", "q"), ("IGSS", "q"),
                ("ISR", "q"), ("Otros descuentos", "q"), ("Total descuentos", "q"), ("Líquido", "q"), ("Cuota patronal", "q"), ("Firmado", "t")]
        filas = [[l.empleado.codigo, l.empleado.nombre_completo, l.empleado.dpi, l.sucursal_nombre, l.dias, l.dias_no_laborados,
                  l.salario, l.bonificacion, l.otros_ingresos, l.devengado, l.igss, l.isr, l.otros_descuentos, l.descuentos,
                  l.liquido, l.patronal, "Sí" if l.firmado else "No"] for l in p.lineas]
        tot = ["", f"Total ({len(p.lineas)})", "", "", "", "", p.total("salario"), p.total("bonificacion"), p.total("otros_ingresos"),
               sum((l.devengado for l in p.lineas), Decimal(0)), p.total("igss"), p.total("isr"), p.total("otros_descuentos"),
               sum((l.descuentos for l in p.lineas), Decimal(0)), p.total("liquido"), p.total("patronal"), ""]
    else:
        cols = [("Código", "t"), ("Colaborador", "t"), ("DPI", "t"), ("Sucursal", "t"), ("Días", "n"), (p.nombre_tipo, "q"),
                ("Otros ingresos", "q"), ("Otros descuentos", "q"), ("Líquido", "q"), ("Firmado", "t")]
        filas = [[l.empleado.codigo, l.empleado.nombre_completo, l.empleado.dpi, l.sucursal_nombre, l.dias, l.salario,
                  l.otros_ingresos, l.otros_descuentos, l.liquido, "Sí" if l.firmado else "No"] for l in p.lineas]
        tot = ["", f"Total ({len(p.lineas)})", "", "", "", p.total("salario"), p.total("otros_ingresos"), p.total("otros_descuentos"),
               p.total("liquido"), ""]
    return cols, filas, tot


@app.get("/planillas/{pid}/excel")
def planilla_excel(pid: int, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    p = _planilla_o_404(db, pid)
    cols, filas, tot = _filas_planilla(p)
    hojas = [dict(nombre=p.nombre_tipo, titulo=f"{p.nombre_tipo} · {p.empresa.razon_social}",
                  subtitulo=f"NIT {p.empresa.nit or '—'} · Período {fecha_gt(p.desde)} al {fecha_gt(p.hasta)} · Pago {fecha_gt(p.fecha_pago)} · {p.estado}",
                  columnas=cols, filas=filas, totales=tot)]
    if p.tipo == "liquidacion":
        for l in p.lineas:
            hojas.append(dict(nombre="Detalle", titulo=f"Liquidación de {l.empleado.nombre_completo}", subtitulo=p.notas,
                              columnas=[("Concepto", "t"), ("Monto", "q")],
                              filas=[[n, Decimal(v)] for n, v in json.loads(l.detalle or "[]")], totales=["Total", l.liquido]))
    nombre = f"{p.tipo}-{p.empresa.razon_social[:20]}-{p.desde.isoformat()}.xlsx".replace(" ", "_").replace(",", "")
    return _descarga_excel(excel.libro(hojas), nombre)


def _datos_gerencial(db: Session, anio: int, mes: int):
    """Costo laboral real del mes: planillas quincenales del mes + provisiones sobre el salario devengado."""
    desde, hasta = date(anio, mes, 1), date(anio, mes, monthrange(anio, mes)[1])
    planillas_mes = (
        db.query(Planilla)
        .filter(Planilla.tipo.in_(["quincena1", "quincena2"]), Planilla.desde >= desde, Planilla.hasta <= hasta)
        .all()
    )
    claves = ("personas", "salario", "bonificacion", "otros_ingresos", "igss", "isr", "liquido", "patronal", "provisiones", "costo")

    def vacio():
        return {k: (set() if k == "personas" else Decimal(0)) for k in claves}

    por_sucursal, por_empresa, total = {}, {}, vacio()
    for p in planillas_mes:
        for l in p.lineas:
            prov = sum(calculos.provision_mensual(l.salario + l.otros_ingresos).values(), Decimal(0))
            costo = l.salario + l.bonificacion + l.otros_ingresos + l.patronal + prov
            for grupo, clave in ((por_sucursal, l.sucursal_nombre or "Sin sucursal"), (por_empresa, p.empresa.razon_social), (None, None)):
                g = total if grupo is None else grupo.setdefault(clave, vacio())
                g["personas"].add(l.empleado_id)
                for k, v in (("salario", l.salario), ("bonificacion", l.bonificacion), ("otros_ingresos", l.otros_ingresos),
                             ("igss", l.igss), ("isr", l.isr), ("liquido", l.liquido), ("patronal", l.patronal),
                             ("provisiones", prov), ("costo", costo)):
                    g[k] += v
    for g in [*por_sucursal.values(), *por_empresa.values(), total]:
        g["personas"] = len(g["personas"])
    return dict(
        planillas=planillas_mes,
        por_sucursal=sorted(por_sucursal.items()),
        por_empresa=sorted(por_empresa.items()),
        total=total,
    )


@app.get("/reportes/gerencial", response_class=HTMLResponse)
def reporte_gerencial(request: Request, anio: int = 0, mes: int = 0, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    hoy = date.today()
    anio, mes = anio or hoy.year, mes or hoy.month
    return render(request, "gerencial.html", user, anio=anio, mes=mes, meses=MESES, **_datos_gerencial(db, anio, mes))


@app.get("/reportes/gerencial/excel")
def reporte_gerencial_excel(anio: int, mes: int, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    d = _datos_gerencial(db, anio, mes)
    cols = [("Grupo", "t"), ("Colaboradores", "n"), ("Salarios", "q"), ("Bonificación", "q"), ("Otros ingresos", "q"),
            ("Cuota patronal", "q"), ("Provisiones", "q"), ("Costo total", "q"), ("IGSS laboral", "q"), ("ISR", "q"), ("Efectivo pagado", "q")]

    def fila(nombre, g):
        return [nombre, g["personas"], g["salario"], g["bonificacion"], g["otros_ingresos"], g["patronal"], g["provisiones"],
                g["costo"], g["igss"], g["isr"], g["liquido"]]

    periodo = f"{MESES[mes - 1].capitalize()} {anio}"
    hojas = [
        dict(nombre="Por sucursal", titulo=f"Nómina gerencial por sucursal · {periodo}", subtitulo="Costo laboral del mes con provisiones de prestaciones",
             columnas=[("Sucursal", "t")] + cols[1:], filas=[fila(n, g) for n, g in d["por_sucursal"]], totales=fila("Total", d["total"])),
        dict(nombre="Por patrono", titulo=f"Nómina gerencial por patrono · {periodo}", subtitulo="Costo laboral del mes con provisiones de prestaciones",
             columnas=[("Patrono", "t")] + cols[1:], filas=[fila(n, g) for n, g in d["por_empresa"]], totales=fila("Total", d["total"])),
    ]
    return _descarga_excel(excel.libro(hojas), f"nomina-gerencial-{anio}-{mes:02d}.xlsx")


@app.get("/provisiones/excel")
def provisiones_excel(anio: int, mes: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    resp = provisiones(request, anio=anio, mes=mes, db=db, user=user)
    grupos = resp.context["grupos"]
    cols = [("Colaborador", "t"), ("Sucursal", "t"), ("Salario del mes", "q"), ("Aguinaldo", "q"), ("Bono 14", "q"),
            ("Vacaciones", "q"), ("Indemnización", "q"), ("Cuota patronal", "q")]
    hojas = []
    for g in grupos:
        filas = [[f["e"].nombre_completo, f["e"].sucursal.nombre if f["e"].sucursal else "", f["salario"], f["aguinaldo"], f["bono14"],
                  f["vacaciones"], f["indemnizacion"], f["patronal"]] for f in g["filas"]]
        t = g["totales"]
        hojas.append(dict(nombre=g["empresa"].razon_social, titulo=f"Provisiones · {g['empresa'].razon_social}",
                          subtitulo=f"{MESES[mes - 1].capitalize()} {anio}", columnas=cols, filas=filas,
                          totales=["Total", "", t["salario"], t["aguinaldo"], t["bono14"], t["vacaciones"], t["indemnizacion"], t["patronal"]]))
    if not hojas:
        hojas = [dict(nombre="Provisiones", titulo="Provisiones", subtitulo="Sin colaboradores en el mes", columnas=cols, filas=[])]
    return _descarga_excel(excel.libro(hojas), f"provisiones-{anio}-{mes:02d}.xlsx")
