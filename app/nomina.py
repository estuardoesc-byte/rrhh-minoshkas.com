"""Cálculo de las planillas como las maneja Minoshkas.

- Anticipo: la mitad del salario real (o un anticipo fijo), proporcional a los días de la 1ra quincena.
  No lleva descuentos de ley.
- Fin de mes: planilla oficial (la que cuadra con el IGSS). Salario base y bonificación del mes por
  días laborados, menos IGSS laboral, ISR y el anticipo ya entregado.
- Administrativa (1ra y 2da quincena): lo que de verdad se paga, con el salario real, de todos los
  patronos juntos. Lleva día doble, comisiones, otros ingresos y descuentos internos.
- Bono 14 y aguinaldo: proporcionales a los días del período.

Todo es editable. Un monto escrito a mano queda guardado en `manual` y el sistema lo respeta al
recalcular; los totales que dependen de él se vuelven a calcular, salvo que también se escriban a mano.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from . import calculos
from .calculos import CERO, r2

TIPOS_NUEVOS = ("anticipo", "fin_mes", "admin1", "admin2", "bono14", "aguinaldo")
ADMINISTRATIVAS = ("admin1", "admin2")
QUINCENAS_ANTIGUAS = ("quincena1", "quincena2")

# Campos que se ven en la planilla. "calc": lo calcula el sistema y se puede escribir encima.
# "dato": lo escribe usted (no tiene cálculo). "entero": días.
CAMPOS = {
    "anticipo": [
        ("dias", "Días", "entero"), ("salario", "Anticipo", "calc"),
        ("otros_ingresos", "Otros ingresos", "dato"), ("otros_descuentos", "Descuentos", "dato"),
        ("liquido", "Líquido", "calc"),
    ],
    "fin_mes": [
        ("dias", "Días", "entero"), ("salario", "Salario devengado", "calc"), ("bonificacion", "Bonificación", "calc"),
        ("dia_doble", "Día doble / asueto", "dato"), ("comisiones", "Comisiones", "dato"),
        ("otros_ingresos", "Otros ingresos", "dato"), ("igss", "IGSS", "calc"), ("isr", "ISR", "calc"),
        ("anticipo", "Anticipo", "calc"), ("otros_descuentos", "Otros descuentos", "dato"), ("liquido", "Líquido", "calc"),
    ],
    "admin": [
        ("dias", "Días", "entero"), ("salario", "Pago", "calc"), ("bonificacion", "Bonificación", "calc"),
        ("dia_doble", "Día doble / asueto", "dato"), ("comisiones", "Comisiones", "dato"),
        ("otros_ingresos", "Otros ingresos", "dato"), ("otros_descuentos", "Descuentos (adelantos, pasajes, teléfono)", "dato"),
        ("liquido", "A pagar", "calc"),
    ],
    "prestacion": [
        ("dias", "Días", "entero"), ("salario", "Monto", "calc"),
        ("otros_ingresos", "Otros ingresos", "dato"), ("otros_descuentos", "Descuentos", "dato"),
        ("liquido", "Líquido", "calc"),
    ],
    "quincena": [
        ("dias_no_laborados", "Días no laborados", "dato_entero"), ("dias", "Días", "entero"),
        ("salario", "Salario", "calc"), ("bonificacion", "Bonificación", "calc"),
        ("otros_ingresos", "Otros ingresos", "dato"), ("igss", "IGSS", "calc"), ("isr", "ISR", "calc"),
        ("otros_descuentos", "Otros descuentos", "dato"), ("liquido", "Líquido", "calc"),
    ],
    "liquidacion": [("dias", "Días", "entero"), ("salario", "Total", "calc"), ("liquido", "Líquido", "calc")],
}


def grupo(tipo: str) -> str:
    if tipo in ADMINISTRATIVAS:
        return "admin"
    if tipo in ("bono14", "aguinaldo"):
        return "prestacion"
    if tipo in QUINCENAS_ANTIGUAS:
        return "quincena"
    return tipo


def campos(tipo: str):
    return CAMPOS[grupo(tipo)]


def normalizar_numero(t: str) -> str:
    """Acepta "3,000.00", "3.000,00", "3000,50", "3000.50" y "3,000". Devuelve "3000.00"."""
    if "," in t and "." in t:
        # El separador que aparece de último es el de decimales.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        partes = t.split(",")
        if len(partes) == 2 and len(partes[1]) in (1, 2):
            t = partes[0] + "." + partes[1]  # coma decimal: 3000,50
        else:
            t = t.replace(",", "")  # coma de miles: 3,000
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[1]) == 3 and len(t.split(".")[0]) <= 3 and t.split(".")[0] != "0"):
        t = t.replace(".", "")  # punto de miles: 3.000 o 1.000.000
    return t


def valor_numerico(texto, entero: bool = False):
    """Lee un número escrito en la planilla ("Q1,750.00", "1750", ""). Devuelve None si no es número."""
    t = str(texto if texto is not None else "").replace("Q", "").replace("q", "").replace(" ", "").strip()
    t = normalizar_numero(t)
    if t == "":
        return 0 if entero else CERO
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return int(d) if entero else r2(d)


@dataclass
class Contexto:
    """Lo que el cálculo necesita saber de la persona y del período."""

    tipo: str
    desde: date
    hasta: date
    salario_base: Decimal
    bonificacion: Decimal
    salario_real: Decimal
    anticipo_mensual: Decimal
    ingreso: date | None
    baja: date | None
    tasas: calculos.Tasas
    anticipo_entregado: Decimal = CERO


def dias_estandar(tipo: str) -> int:
    return 30 if tipo == "fin_mes" else 15


def dias_por_omision(c: Contexto) -> int:
    """Días a pagar si nadie los cambia: 15 o 30, menos lo que quede antes del ingreso o después de la baja."""
    if c.tipo in ("bono14", "aguinaldo"):
        return calculos.dias_laborados(c.ingreso, c.baja, c.desde, c.hasta)
    total = calculos.dias_inclusivos(c.desde, c.hasta)
    trabajados = calculos.dias_laborados(c.ingreso, c.baja, c.desde, c.hasta)
    estandar = dias_estandar(c.tipo)
    return estandar if trabajados >= total else max(min(trabajados, estandar), 0)


def calcular(c: Contexto, datos: dict, manual: dict) -> dict:
    """Calcula una línea. `datos` trae los montos que escribe el usuario (otros ingresos, comisiones…).

    `manual` trae los montos calculados que el usuario corrigió a mano; esos se respetan.
    """
    v: dict = {}

    def poner(campo, calculado):
        if campo in manual:
            v[campo] = int(manual[campo]) if campo == "dias" else r2(Decimal(str(manual[campo])))
        else:
            v[campo] = calculado if campo == "dias" else r2(calculado)
        return v[campo]

    oi = datos.get("otros_ingresos") or CERO
    od = datos.get("otros_descuentos") or CERO
    dias = poner("dias", dias_por_omision(c))

    if c.tipo == "anticipo":
        sal = poner("salario", c.anticipo_mensual * dias / 15)
        poner("liquido", sal + oi - od)
    elif c.tipo == "fin_mes":
        sal = poner("salario", c.salario_base * dias / 30)
        bon = poner("bonificacion", c.bonificacion * dias / 30)
        dd = datos.get("dia_doble") or CERO
        com = datos.get("comisiones") or CERO
        # Día doble y comisiones son salario: pagan IGSS. La bonificación incentivo no.
        igss = poner("igss", (sal + dd + com) * c.tasas.igss_laboral / 100)
        isr = poner("isr", calculos.isr_mensual(c.salario_base, c.bonificacion, c.tasas) * dias / 30 if sal > 0 else CERO)
        ant = poner("anticipo", c.anticipo_entregado)
        poner("liquido", sal + bon + dd + com + oi - igss - isr - ant - od)
        v["patronal"] = calculos.cuota_patronal(sal + dd + com, c.tasas)
    elif c.tipo in ADMINISTRATIVAS:
        sal = poner("salario", c.salario_real * dias / 30)
        bon = poner("bonificacion", CERO)
        dd = datos.get("dia_doble") or CERO
        com = datos.get("comisiones") or CERO
        poner("liquido", sal + bon + dd + com + oi - od)
    elif c.tipo in ("bono14", "aguinaldo"):
        total = calculos.dias_inclusivos(c.desde, c.hasta)
        sal = poner("salario", c.salario_base * dias / total if total else CERO)
        poner("liquido", sal + oi - od)
    else:
        raise ValueError(f"Tipo de planilla sin cálculo: {c.tipo}")

    for campo in ("salario", "bonificacion", "igss", "isr", "anticipo", "patronal"):
        v.setdefault(campo, CERO)
    return v


def renglones(tipo: str, l) -> tuple[list, list]:
    """Ingresos y descuentos de una línea, para el recibo."""
    ing, desc = [], []
    if tipo == "anticipo":
        ing.append((f"Anticipo de salario ({l.dias} días)", l.salario))
    elif tipo in ADMINISTRATIVAS:
        ing.append((f"Pago de la quincena ({l.dias} días)", l.salario))
    elif tipo in ("bono14", "aguinaldo", "liquidacion"):
        ing.append((f"{ {'bono14': 'Bono 14 (Decreto 42-92)', 'aguinaldo': 'Aguinaldo (Decreto 76-78)'}.get(tipo, 'Liquidación') } ({l.dias} días)", l.salario))
    else:
        ing.append((f"Salario ({l.dias} días)", l.salario))
    if l.bonificacion:
        ing.append(("Bonificación incentivo (Decreto 37-2001)", l.bonificacion))
    if l.dia_doble:
        ing.append(("Día doble / asueto", l.dia_doble))
    if l.comisiones:
        ing.append(("Comisiones", l.comisiones))
    if l.otros_ingresos:
        ing.append((l.concepto_ingresos or "Otros ingresos", l.otros_ingresos))
    if l.igss:
        desc.append(("IGSS laboral", l.igss))
    if l.isr:
        desc.append(("ISR", l.isr))
    if l.anticipo:
        desc.append(("Anticipo entregado", l.anticipo))
    if l.otros_descuentos:
        desc.append((l.concepto_descuentos or "Otros descuentos", l.otros_descuentos))
    # Si el líquido se escribió a mano, la diferencia sale como ajuste para que el recibo cuadre.
    diferencia = (l.liquido or CERO) - (l.devengado - l.descuentos)
    if diferencia > 0:
        ing.append(("Ajuste", diferencia))
    elif diferencia < 0:
        desc.append(("Ajuste", -diferencia))
    return ing, desc
