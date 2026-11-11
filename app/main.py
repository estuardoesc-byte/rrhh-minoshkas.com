"""Aplicación web del sistema de RRHH de Minoshkas."""
import mimetypes
from contextlib import asynccontextmanager
import uuid
from datetime import date, timedelta
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
        return f"Q{Decimal(valor):,.2f}"
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
def empleado_ficha(eid: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(requiere_usuario)):
    e = _empleado_o_404(db, eid)
    return render(request, "empleado_ficha.html", user, e=e, tipos=TIPOS_DOCUMENTO, nombres_doc=NOMBRES_DOCUMENTO,
                  max_mb=config.MAX_UPLOAD_MB)


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
