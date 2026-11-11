"""Modelo de datos del sistema de RRHH."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ESTADOS_EMPLEADO = ["activo", "suspendido", "retirado"]
TIPOS_CONTRATO = ["indefinido", "plazo fijo", "obra determinada"]
JORNADAS = ["diurna", "mixta", "nocturna"]
ESTADOS_CIVILES = ["soltero(a)", "casado(a)", "unido(a)", "divorciado(a)", "viudo(a)"]
TIPOS_DOCUMENTO = [
    "foto",
    "dpi_frente",
    "dpi_reverso",
    "tarjeta_salud",
    "contrato",
    "cv",
    "titulo",
    "carta",
    "antecedentes_penales",
    "antecedentes_policiacos",
    "amonestacion",
    "otro",
]
NOMBRES_DOCUMENTO = {
    "foto": "Foto del colaborador",
    "dpi_frente": "DPI (frente)",
    "dpi_reverso": "DPI (reverso)",
    "tarjeta_salud": "Tarjeta de salud",
    "contrato": "Contrato de trabajo",
    "cv": "Currículum (CV)",
    "titulo": "Título o diploma",
    "carta": "Carta (recomendación u otra)",
    "antecedentes_penales": "Antecedentes penales",
    "antecedentes_policiacos": "Antecedentes policiacos",
    "amonestacion": "Amonestación",
    "otro": "Otro documento",
}


def ahora() -> datetime:
    return datetime.now()


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Empresa(Base):
    """Patrono: cada uno tiene su número patronal de IGSS y su libro de salarios."""

    __tablename__ = "empresas"
    id: Mapped[int] = mapped_column(primary_key=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    nombre_comercial: Mapped[str] = mapped_column(String(200), default="")
    nit: Mapped[str] = mapped_column(String(20), default="")
    numero_patronal_igss: Mapped[str] = mapped_column(String(30), default="")
    erp_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    empleados: Mapped[list["Empleado"]] = relationship(back_populates="empresa")


class Sucursal(Base):
    __tablename__ = "sucursales"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    codigo: Mapped[str] = mapped_column(String(10), default="")
    direccion: Mapped[str] = mapped_column(String(250), default="")
    municipio: Mapped[str] = mapped_column(String(80), default="")
    departamento: Mapped[str] = mapped_column(String(80), default="")
    erp_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    empleados: Mapped[list["Empleado"]] = relationship(back_populates="sucursal")


class Empleado(Base):
    __tablename__ = "empleados"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), default="", index=True)
    erp_id: Mapped[str] = mapped_column(String(40), default="", index=True)

    # Datos personales
    nombres: Mapped[str] = mapped_column(String(120))
    apellidos: Mapped[str] = mapped_column(String(120), default="")
    dpi: Mapped[str] = mapped_column(String(20), default="", index=True)
    nit: Mapped[str] = mapped_column(String(20), default="")
    afiliacion_igss: Mapped[str] = mapped_column(String(30), default="")
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    sexo: Mapped[str] = mapped_column(String(10), default="")
    estado_civil: Mapped[str] = mapped_column(String(20), default="")
    nacionalidad: Mapped[str] = mapped_column(String(40), default="guatemalteca")
    direccion: Mapped[str] = mapped_column(String(250), default="")
    telefono: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    numero_hijos: Mapped[int] = mapped_column(Integer, default=0)
    nivel_academico: Mapped[str] = mapped_column(String(80), default="")

    # Datos laborales
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), nullable=True)
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales.id"), nullable=True)
    puesto: Mapped[str] = mapped_column(String(80), default="")
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_contrato: Mapped[str] = mapped_column(String(30), default="indefinido")
    fecha_fin_contrato: Mapped[date | None] = mapped_column(Date, nullable=True)
    jornada: Mapped[str] = mapped_column(String(20), default="diurna")
    salario_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    bonificacion_incentivo: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("250"))
    vacaciones_previas: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(String(20), default="activo")
    fecha_baja: Mapped[date | None] = mapped_column(Date, nullable=True)
    motivo_baja: Mapped[str] = mapped_column(String(200), default="")

    # Contactos y salud
    emergencia_nombre: Mapped[str] = mapped_column(String(120), default="")
    emergencia_parentesco: Mapped[str] = mapped_column(String(40), default="")
    emergencia_telefono: Mapped[str] = mapped_column(String(30), default="")
    beneficiarios: Mapped[str] = mapped_column(Text, default="")
    tarjeta_salud_numero: Mapped[str] = mapped_column(String(40), default="")
    tarjeta_salud_vence: Mapped[date | None] = mapped_column(Date, nullable=True)

    notas: Mapped[str] = mapped_column(Text, default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)

    empresa: Mapped[Empresa | None] = relationship(back_populates="empleados")
    sucursal: Mapped[Sucursal | None] = relationship(back_populates="empleados")
    documentos: Mapped[list["Documento"]] = relationship(
        back_populates="empleado", cascade="all, delete-orphan", order_by="Documento.subido.desc()"
    )
    historial: Mapped[list["HistorialEmpleado"]] = relationship(
        back_populates="empleado", cascade="all, delete-orphan", order_by="HistorialEmpleado.fecha.desc()"
    )

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def foto(self) -> "Documento | None":
        return next((d for d in self.documentos if d.tipo == "foto"), None)


class Documento(Base):
    __tablename__ = "documentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleados.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    descripcion: Mapped[str] = mapped_column(String(200), default="")
    nombre_original: Mapped[str] = mapped_column(String(250))
    archivo: Mapped[str] = mapped_column(String(250))
    mime: Mapped[str] = mapped_column(String(80))
    tamano: Mapped[int] = mapped_column(Integer)
    subido_por: Mapped[str] = mapped_column(String(120))
    subido: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    empleado: Mapped[Empleado] = relationship(back_populates="documentos")

    @property
    def nombre_tipo(self) -> str:
        return NOMBRES_DOCUMENTO.get(self.tipo, self.tipo)


class HistorialEmpleado(Base):
    """Cambios relevantes de la ficha: salario, puesto, sucursal, estado."""

    __tablename__ = "historial_empleados"
    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleados.id"), index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    campo: Mapped[str] = mapped_column(String(40))
    valor_anterior: Mapped[str] = mapped_column(String(250), default="")
    valor_nuevo: Mapped[str] = mapped_column(String(250), default="")
    usuario: Mapped[str] = mapped_column(String(120))
    empleado: Mapped[Empleado] = relationship(back_populates="historial")


class Parametro(Base):
    """Valores legales editables (salario mínimo, bonificación, porcentajes)."""

    __tablename__ = "parametros"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(60))
    descripcion: Mapped[str] = mapped_column(String(250), default="")
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


PARAMETROS_INICIALES = {
    # Monto a revisar cada enero con el acuerdo gubernativo vigente.
    "salario_minimo_no_agricola_c2": ("3816.90", "Salario mínimo mensual no agrícola, circunscripción 2 (resto del país), Acuerdo Gubernativo 256-2025. Actualizar cada enero."),
    "bonificacion_incentivo": ("250.00", "Bonificación incentivo mensual, Decreto 37-2001"),
    "igss_laboral_pct": ("4.83", "Cuota laboral IGSS (%)"),
    "igss_patronal_pct": ("10.67", "Cuota patronal IGSS (%)"),
    "irtra_pct": ("1.00", "IRTRA (%)"),
    "intecap_pct": ("1.00", "INTECAP (%)"),
}
