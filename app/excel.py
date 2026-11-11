"""Exportación a Excel (.xlsx) de planillas y reportes."""
import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FORMATO_Q = '"Q"#,##0.00'
ENCABEZADO = PatternFill("solid", fgColor="F4E6EE")
NEGRITA = Font(bold=True)
LINEA = Side(style="thin", color="D9D2D5")


def _num(v):
    return float(v) if isinstance(v, Decimal) else v


def hoja(ws, titulo: str, subtitulo: str, columnas: list[tuple[str, str]], filas: list[list], totales: list | None = None):
    """Escribe una tabla con título. columnas = [(nombre, 'q'|'n'|'t')]."""
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([subtitulo])
    ws.append([])
    ws.append([c for c, _ in columnas])
    fila_enc = ws.max_row
    for i in range(1, len(columnas) + 1):
        celda = ws.cell(row=fila_enc, column=i)
        celda.font, celda.fill = NEGRITA, ENCABEZADO
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        celda.border = Border(bottom=LINEA)
    for f in filas:
        ws.append([_num(v) for v in f])
    if totales:
        ws.append([_num(v) for v in totales])
        for i in range(1, len(columnas) + 1):
            c = ws.cell(row=ws.max_row, column=i)
            c.font, c.border = NEGRITA, Border(top=LINEA)
    for i, (_, tipo) in enumerate(columnas, start=1):
        if tipo == "q":
            for fila in ws.iter_rows(min_row=fila_enc + 1, min_col=i, max_col=i):
                fila[0].number_format = FORMATO_Q
        ancho = max(len(str(ws.cell(row=r, column=i).value or "")) for r in range(fila_enc, ws.max_row + 1))
        ws.column_dimensions[get_column_letter(i)].width = min(max(ancho + 2, 10), 45)
    ws.freeze_panes = ws.cell(row=fila_enc + 1, column=1)


def libro(hojas: list[dict]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for h in hojas:
        ws = wb.create_sheet(h["nombre"][:31])
        hoja(ws, h["titulo"], h["subtitulo"], h["columnas"], h["filas"], h.get("totales"))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
