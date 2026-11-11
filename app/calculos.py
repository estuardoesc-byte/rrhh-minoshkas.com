"""Cálculos laborales según la legislación guatemalteca.

Todas las funciones son puras (no tocan la base de datos) y trabajan con Decimal.
Las reglas están descritas en el documento de diseño del proyecto.
"""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
CERO = Decimal("0")


def r2(valor) -> Decimal:
    return Decimal(valor).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Tasas:
    igss_laboral: Decimal = Decimal("4.83")
    igss_patronal: Decimal = Decimal("10.67")
    irtra: Decimal = Decimal("1.00")
    intecap: Decimal = Decimal("1.00")

    @property
    def patronal_total(self) -> Decimal:
        return self.igss_patronal + self.irtra + self.intecap


# ---------------------------------------------------------------- períodos


def dias_inclusivos(desde: date, hasta: date) -> int:
    return max((hasta - desde).days + 1, 0)


def dias_laborados(ingreso: date | None, baja: date | None, desde: date, hasta: date) -> int:
    """Días calendario trabajados dentro del período [desde, hasta]."""
    inicio = max(desde, ingreso) if ingreso else desde
    fin = min(hasta, baja) if baja else hasta
    return dias_inclusivos(inicio, fin)


def periodo_bono14(fecha_pago: date) -> tuple[date, date]:
    """Bono 14: del 1 de julio del año anterior al 30 de junio (Decreto 42-92)."""
    anio = fecha_pago.year if fecha_pago.month >= 7 else fecha_pago.year - 1
    return date(anio - 1, 7, 1), date(anio, 6, 30)


def periodo_aguinaldo(fecha_pago: date) -> tuple[date, date]:
    """Aguinaldo: del 1 de diciembre del año anterior al 30 de noviembre (Decreto 76-78)."""
    anio = fecha_pago.year if fecha_pago.month == 12 else fecha_pago.year - 1
    return date(anio - 1, 12, 1), date(anio, 11, 30)


def periodo_quincena(anio: int, mes: int, numero: int) -> tuple[date, date]:
    if numero == 1:
        return date(anio, mes, 1), date(anio, mes, 15)
    return date(anio, mes, 16), date(anio, mes, monthrange(anio, mes)[1])


def dias_en_anio(desde: date) -> int:
    """365, o 366 si el período anual que inicia en `desde` incluye un 29 de febrero."""
    fin = date(desde.year + 1, desde.month, desde.day) - timedelta(days=1)
    return dias_inclusivos(desde, fin)


# ---------------------------------------------------------------- nómina quincenal


@dataclass
class LineaQuincena:
    dias_no_laborados: int = 0
    salario: Decimal = CERO
    bonificacion: Decimal = CERO
    otros_ingresos: Decimal = CERO
    igss: Decimal = CERO
    isr: Decimal = CERO
    otros_descuentos: Decimal = CERO

    @property
    def devengado(self) -> Decimal:
        return self.salario + self.bonificacion + self.otros_ingresos

    @property
    def descuentos(self) -> Decimal:
        return self.igss + self.isr + self.otros_descuentos

    @property
    def liquido(self) -> Decimal:
        return self.devengado - self.descuentos


def isr_mensual(salario_mensual: Decimal, bonificacion_mensual: Decimal, tasas: Tasas) -> Decimal:
    """Retención mensual estimada de ISR para asalariados.

    Renta anual = 12 salarios + 12 bonificaciones; deducción fija Q48,000 más IGSS laboral anual.
    Bono 14 y aguinaldo están exentos. 5% hasta Q300,000 y 7% sobre el excedente.
    """
    anual = (salario_mensual + bonificacion_mensual) * 12
    igss_anual = salario_mensual * 12 * tasas.igss_laboral / 100
    imponible = anual - Decimal("48000") - igss_anual
    if imponible <= 0:
        return CERO
    if imponible <= 300000:
        impuesto = imponible * Decimal("0.05")
    else:
        impuesto = Decimal("15000") + (imponible - 300000) * Decimal("0.07")
    return r2(impuesto / 12)


def calcular_quincena(
    salario_base: Decimal,
    bonificacion: Decimal,
    tasas: Tasas,
    dias_no_laborados: int = 0,
    dias_fuera_de_contrato: int = 0,
    otros_ingresos: Decimal = CERO,
    otros_descuentos: Decimal = CERO,
) -> LineaQuincena:
    """Media quincena del salario y la bonificación, menos días no pagados (salario / 30 por día).

    `dias_fuera_de_contrato` son días de la quincena antes del ingreso o después de la baja.
    El IGSS se descuenta en cada quincena sobre el salario devengado (no sobre la bonificación).
    """
    dias = max(dias_no_laborados, 0) + max(dias_fuera_de_contrato, 0)
    salario = max(r2(salario_base / 2 - salario_base / 30 * dias), CERO)
    bonif = max(r2(bonificacion / 2 - bonificacion / 30 * dias), CERO)
    igss = r2(salario * tasas.igss_laboral / 100)
    isr = r2(isr_mensual(salario_base, bonificacion, tasas) / 2) if salario > 0 else CERO
    return LineaQuincena(
        dias_no_laborados=dias_no_laborados, salario=salario, bonificacion=bonif,
        otros_ingresos=r2(otros_ingresos), igss=igss, isr=isr, otros_descuentos=r2(otros_descuentos),
    )


def cuota_patronal(salario: Decimal, tasas: Tasas) -> Decimal:
    return r2(salario * tasas.patronal_total / 100)


# ---------------------------------------------------------------- prestaciones anuales


def prestacion_anual(salario_promedio: Decimal, ingreso: date | None, baja: date | None, desde: date, hasta: date) -> tuple[int, Decimal]:
    """Bono 14 o aguinaldo: un salario por año, proporcional a los días laborados en el período."""
    dias = dias_laborados(ingreso, baja, desde, hasta)
    total = dias_inclusivos(desde, hasta)
    if dias <= 0:
        return 0, CERO
    return dias, r2(salario_promedio * dias / total)


def provision_mensual(salario: Decimal) -> dict[str, Decimal]:
    """Reserva mensual de prestaciones sobre el salario base (sin bonificación incentivo)."""
    tasas = {
        "aguinaldo": Decimal("8.33"),
        "bono14": Decimal("8.33"),
        "vacaciones": Decimal("4.17"),
        "indemnizacion": Decimal("9.72"),
    }
    return {k: r2(salario * v / 100) for k, v in tasas.items()}


# ---------------------------------------------------------------- liquidación

TIPOS_TERMINACION = {
    "renuncia": "Renuncia",
    "despido_justificado": "Despido justificado (art. 77)",
    "despido_injustificado": "Despido injustificado",
    "despido_indirecto": "Despido indirecto (art. 79)",
    "mutuo_acuerdo": "Mutuo acuerdo",
    "fallecimiento": "Fallecimiento (art. 85)",
    "fin_plazo": "Fin de contrato a plazo fijo",
}
CON_INDEMNIZACION = {"despido_injustificado", "despido_indirecto"}


@dataclass
class Liquidacion:
    conceptos: list[tuple[str, Decimal]] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((v for _, v in self.conceptos), CERO)

    def agregar(self, nombre: str, valor: Decimal) -> None:
        self.conceptos.append((nombre, r2(valor)))


def vacaciones_proporcionales(ingreso: date, baja: date) -> Decimal:
    """Días de vacaciones ganados desde el último aniversario: 15 días hábiles por año (art. 130)."""
    aniversario = date(baja.year, ingreso.month, min(ingreso.day, 28))
    if aniversario > baja:
        aniversario = date(baja.year - 1, ingreso.month, min(ingreso.day, 28))
    aniversario = max(aniversario, ingreso)
    dias = dias_inclusivos(aniversario, baja)
    return (Decimal(15) * dias / 365).quantize(Decimal("0.01"))


def calcular_liquidacion(
    *,
    tipo: str,
    ingreso: date,
    baja: date,
    salario_base: Decimal,
    bonificacion: Decimal,
    salario_promedio: Decimal,
    tasas: Tasas,
    dias_salario_pendiente: int,
    dias_vacaciones_pendientes: Decimal,
    otros_descuentos: Decimal = CERO,
    monto_pactado: Decimal = CERO,
) -> Liquidacion:
    """Liquidación por terminación de la relación laboral.

    - Salario y bonificación pendientes: salario / 30 por día no pagado.
    - Bono 14 y aguinaldo proporcionales a los días del período en curso.
    - Vacaciones pendientes en dinero: salario promedio / 30 por día.
    - Indemnización (despido injustificado o indirecto): promedio × 14/12 por año, proporcional por días.
    - Fallecimiento: prestación post mortem de un salario por año, hasta 15 (art. 85).
    """
    liq = Liquidacion()
    salario_pend = salario_base / 30 * dias_salario_pendiente
    liq.agregar(f"Salario pendiente ({dias_salario_pendiente} días)", salario_pend)
    liq.agregar(f"Bonificación incentivo pendiente ({dias_salario_pendiente} días)", bonificacion / 30 * dias_salario_pendiente)

    d14, b14 = prestacion_anual(salario_promedio, ingreso, baja, *periodo_bono14_en_curso(baja))
    liq.agregar(f"Bono 14 proporcional ({d14} días, Decreto 42-92)", b14)
    dag, ag = prestacion_anual(salario_promedio, ingreso, baja, *periodo_aguinaldo_en_curso(baja))
    liq.agregar(f"Aguinaldo proporcional ({dag} días, Decreto 76-78)", ag)
    liq.agregar(f"Vacaciones pendientes ({dias_vacaciones_pendientes} días)", salario_promedio / 30 * dias_vacaciones_pendientes)

    dias_totales = dias_inclusivos(ingreso, baja)
    if tipo in CON_INDEMNIZACION:
        indem = salario_promedio * 14 / 12 * dias_totales / 365
        liq.agregar(f"Indemnización (art. 82, {dias_totales} días)", indem)
    elif tipo == "fallecimiento":
        meses = min(Decimal(dias_totales) / 365, Decimal(15))
        liq.agregar("Prestación post mortem (art. 85)", salario_promedio * meses)
    elif tipo == "mutuo_acuerdo" and monto_pactado > 0:
        liq.agregar("Monto pactado por mutuo acuerdo", monto_pactado)

    liq.agregar("IGSS laboral sobre salario pendiente", -(salario_pend * tasas.igss_laboral / 100))
    if otros_descuentos:
        liq.agregar("Otros descuentos", -otros_descuentos)
    return liq


def periodo_bono14_en_curso(fecha: date) -> tuple[date, date]:
    anio = fecha.year if fecha.month >= 7 else fecha.year - 1
    return date(anio, 7, 1), date(anio + 1, 6, 30)


def periodo_aguinaldo_en_curso(fecha: date) -> tuple[date, date]:
    anio = fecha.year if fecha.month == 12 else fecha.year - 1
    return date(anio, 12, 1), date(anio + 1, 11, 30)
