"""Montos en letras para recibos: 1,941.27 -> 'Un mil novecientos cuarenta y un quetzales con 27/100'."""
from decimal import ROUND_HALF_UP, Decimal

UNIDADES = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
            "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
            "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"]
DECENAS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
CENTENAS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
            "ochocientos", "novecientos"]


def _menor_mil(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cien"
    c, resto = divmod(n, 100)
    partes = [CENTENAS[c]] if c else []
    if resto < 30:
        partes.append(UNIDADES[resto])
    else:
        d, u = divmod(resto, 10)
        partes.append(DECENAS[d] + (f" y {UNIDADES[u]}" if u else ""))
    return " ".join(p for p in partes if p)


def numero_en_letras(n: int) -> str:
    if n == 0:
        return "cero"
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append("un millón" if millones == 1 else f"{numero_en_letras(millones)} millones")
    if miles:
        partes.append("un mil" if miles == 1 else f"{_menor_mil(miles)} mil")
    if unidades:
        partes.append(_menor_mil(unidades))
    return " ".join(partes)


def monto_en_letras(valor) -> str:
    v = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    signo = "menos " if v < 0 else ""
    v = abs(v)
    enteros = int(v)
    centavos = int((v - enteros) * 100)
    palabras = numero_en_letras(enteros)
    if palabras.endswith("veintiuno"):
        palabras = palabras[:-9] + "veintiún"
    elif palabras.endswith("uno"):
        palabras = palabras[:-3] + "un"
    moneda = "quetzal" if enteros == 1 else "quetzales"
    texto = f"{signo}{palabras} {moneda} con {centavos:02d}/100"
    return texto[0].upper() + texto[1:]
