"""Importación de colaboradores desde la hoja "empleados" del ERP de Minoshkas (CSV)."""
import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from .models import Empleado, Empresa, HistorialEmpleado, Sucursal

COLUMNAS_REQUERIDAS = {"id", "nombre"}


@dataclass
class Resultado:
    creados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    avisos: list[str] = field(default_factory=list)


def _texto(fila: dict, col: str) -> str:
    return (fila.get(col) or "").strip()


def _fecha(valor: str) -> date | None:
    valor = valor.strip()[:10]
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        pass
    for sep in ("/", "-"):
        partes = valor.split(sep)
        if len(partes) == 3 and len(partes[2]) == 4:
            try:
                return date(int(partes[2]), int(partes[1]), int(partes[0]))
            except ValueError:
                return None
    return None


def _dinero(valor: str) -> Decimal | None:
    v = valor.replace("Q", "").replace(" ", "").strip()
    if not v:
        return None
    if "," in v and "." not in v:
        v = v.replace(",", ".")  # el ERP guarda 3816,9
    else:
        v = v.replace(",", "")
    try:
        return Decimal(v).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _entero(valor: str) -> int:
    try:
        return max(int(float(valor.replace(",", "."))), 0)
    except ValueError:
        return 0


def _es_verdadero(valor: str) -> bool:
    return valor.strip().lower() in {"true", "1", "si", "sí", "x", "verdadero"}


def importar_csv(db: Session, contenido: bytes, usuario: str, actualizar: bool = False) -> Resultado:
    res = Resultado()
    texto = contenido.decode("utf-8-sig", errors="replace")
    lector = csv.DictReader(io.StringIO(texto))
    columnas = set(lector.fieldnames or [])
    faltan = COLUMNAS_REQUERIDAS - columnas
    if faltan:
        raise ValueError(
            "El archivo no parece ser la hoja 'empleados' del ERP. Faltan las columnas: " + ", ".join(sorted(faltan))
        )

    empresas = {e.erp_id: e for e in db.query(Empresa).all() if e.erp_id}
    sucursales = {s.erp_id: s for s in db.query(Sucursal).all() if s.erp_id}
    dpis = {e.dpi: e for e in db.query(Empleado).all() if e.dpi}

    for n, fila in enumerate(lector, start=2):
        erp_id = _texto(fila, "id")
        nombre = " ".join(_texto(fila, "nombre").split())
        if not erp_id or not nombre:
            continue
        if _es_verdadero(_texto(fila, "deleted")):
            res.omitidos += 1
            continue

        existente = db.query(Empleado).filter(Empleado.erp_id == erp_id).first()
        if existente and not actualizar:
            res.omitidos += 1
            continue

        dpi = "".join(c for c in _texto(fila, "dpi") if c.isdigit())
        if dpi and len(dpi) != 13:
            res.avisos.append(f"Fila {n} ({nombre}): el DPI '{_texto(fila, 'dpi')}' no tiene 13 dígitos; se dejó en notas.")
            dpi_nota, dpi = _texto(fila, "dpi"), ""
        else:
            dpi_nota = ""
        otro = dpis.get(dpi) if dpi else None
        if otro and otro is not existente:
            res.avisos.append(f"Fila {n} ({nombre}): el DPI ya pertenece a {otro.nombre_completo}; no se importó.")
            res.omitidos += 1
            continue

        e = existente or Empleado(erp_id=erp_id, nombres=nombre)
        e.nombres, e.apellidos = nombre, ""
        if dpi:
            e.dpi = dpi
        e.nit = _texto(fila, "nit") or e.nit or ""
        e.afiliacion_igss = _texto(fila, "igss") or e.afiliacion_igss or ""
        e.tarjeta_salud_numero = _texto(fila, "tarjetaSalud") or e.tarjeta_salud_numero or ""
        e.tarjeta_salud_vence = _fecha(_texto(fila, "tarjetaSaludVence")) or e.tarjeta_salud_vence
        e.puesto = _texto(fila, "puesto") or e.puesto or ""
        e.fecha_ingreso = _fecha(_texto(fila, "fechaIngreso")) or e.fecha_ingreso
        e.vacaciones_previas = _entero(_texto(fila, "vacPrevias")) if _texto(fila, "vacPrevias") else (e.vacaciones_previas or 0)
        salario = _dinero(_texto(fila, "salarioBase"))
        if salario is not None:
            e.salario_base = salario
        bonif = _dinero(_texto(fila, "bonificacion"))
        e.bonificacion_incentivo = bonif if bonif is not None else (e.bonificacion_incentivo or Decimal("250"))
        e.telefono = _texto(fila, "telefono") or e.telefono or ""
        e.direccion = _texto(fila, "direccion") or e.direccion or ""
        e.emergencia_nombre = _texto(fila, "emergencia") or e.emergencia_nombre or ""
        estado = _texto(fila, "estado").lower()
        e.estado = estado if estado in {"activo", "suspendido", "retirado"} else ("retirado" if estado in {"baja", "inactivo"} else "activo")
        e.fecha_baja = _fecha(_texto(fila, "fechaBaja")) or e.fecha_baja
        e.motivo_baja = _texto(fila, "motivoBaja") or e.motivo_baja or ""
        notas = [x for x in [_texto(fila, "notas"), f"DPI en el ERP: {dpi_nota}" if dpi_nota else ""] if x]
        if notas:
            e.notas = "\n".join(notas)
        e.tipo_contrato = e.tipo_contrato or "indefinido"
        e.jornada = e.jornada or "diurna"

        emp_id, suc_id = _texto(fila, "empresaId"), _texto(fila, "sucursalId")
        if emp_id in empresas:
            e.empresa_id = empresas[emp_id].id
        elif emp_id:
            res.avisos.append(f"Fila {n} ({nombre}): patrono '{emp_id}' no encontrado; queda sin patrono.")
        if suc_id in sucursales:
            e.sucursal_id = sucursales[suc_id].id
        elif suc_id:
            res.avisos.append(f"Fila {n} ({nombre}): sucursal '{suc_id}' no encontrada; queda sin sucursal.")

        if existente:
            res.actualizados += 1
        else:
            db.add(e)
            db.flush()
            e.codigo = e.codigo or f"MK-{e.id:04d}"
            db.add(HistorialEmpleado(empleado_id=e.id, campo="Importado del ERP", valor_nuevo=erp_id, usuario=usuario))
            res.creados += 1
        if e.dpi:
            dpis[e.dpi] = e

    db.commit()
    return res
