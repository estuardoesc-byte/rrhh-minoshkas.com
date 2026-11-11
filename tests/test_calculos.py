from datetime import date
from decimal import Decimal as D

from app import calculos as c

T = c.Tasas()


def test_quincena_completa():
    q = c.calcular_quincena(D("3816.90"), D("250"), T)
    assert q.salario == D("1908.45")
    assert q.bonificacion == D("125.00")
    assert q.igss == D("92.18")  # 4.83% de 1,908.45
    assert q.isr == 0
    assert q.liquido == D("1941.27")


def test_quincena_con_dias_no_laborados():
    q = c.calcular_quincena(D("3000"), D("250"), T, dias_no_laborados=2, otros_descuentos=D("100"))
    assert q.salario == D("1300.00")  # 1500 - 2 × 100
    assert q.bonificacion == D("108.33")
    assert q.liquido == q.salario + q.bonificacion - q.igss - D("100")


def test_isr_solo_sobre_el_minimo_exento():
    assert c.isr_mensual(D("3816.90"), D("250"), T) == 0
    # 10,000 + 250: anual 123,000 - 48,000 - 5,796 IGSS = 69,204 × 5% = 3,460.20 / 12
    assert c.isr_mensual(D("10000"), D("250"), T) == D("288.35")


def test_periodos():
    assert c.periodo_bono14(date(2026, 7, 15)) == (date(2025, 7, 1), date(2026, 6, 30))
    assert c.periodo_aguinaldo(date(2026, 12, 15)) == (date(2025, 12, 1), date(2026, 11, 30))
    assert c.periodo_quincena(2026, 2, 2) == (date(2026, 2, 16), date(2026, 2, 28))


def test_bono14_completo_y_proporcional():
    desde, hasta = c.periodo_bono14(date(2026, 7, 15))
    assert c.prestacion_anual(D("3816.90"), date(2020, 1, 1), None, desde, hasta) == (365, D("3816.90"))
    dias, monto = c.prestacion_anual(D("3650"), date(2026, 1, 1), None, desde, hasta)
    assert dias == 181 and monto == D("1810.00")


def test_provision_mensual_suma_30_55():
    p = c.provision_mensual(D("1000"))
    assert sum(p.values()) == D("305.50")


def test_liquidacion_renuncia_sin_indemnizacion():
    liq = c.calcular_liquidacion(
        tipo="renuncia", ingreso=date(2026, 10, 27), baja=date(2026, 10, 31), salario_base=D("3816.90"),
        bonificacion=D("250"), salario_promedio=D("3816.90"), tasas=T, dias_salario_pendiente=5,
        dias_vacaciones_pendientes=D("0"),
    )
    nombres = [n for n, _ in liq.conceptos]
    assert not any("Indemnización" in n for n in nombres)
    conceptos = dict(liq.conceptos)
    assert conceptos["Bono 14 proporcional (5 días, Decreto 42-92)"] == D("52.29")
    assert conceptos["Aguinaldo proporcional (5 días, Decreto 76-78)"] == D("52.29")


def test_liquidacion_despido_injustificado_un_anio():
    liq = c.calcular_liquidacion(
        tipo="despido_injustificado", ingreso=date(2025, 1, 1), baja=date(2025, 12, 31), salario_base=D("3650"),
        bonificacion=D("250"), salario_promedio=D("3650"), tasas=T, dias_salario_pendiente=0,
        dias_vacaciones_pendientes=D("15"),
    )
    conceptos = dict(liq.conceptos)
    assert conceptos["Indemnización (art. 82, 365 días)"] == D("4258.33")  # 3650 × 14/12
    assert conceptos["Vacaciones pendientes (15 días)"] == D("1825.00")


def test_vacaciones_proporcionales():
    # Un año completo desde el último aniversario (1 mar 2025 a 28 feb 2026)
    assert c.vacaciones_proporcionales(date(2024, 3, 1), date(2026, 2, 28)) == D("15.00")
    # 184 días desde el aniversario: 15 × 184 / 365
    assert c.vacaciones_proporcionales(date(2024, 3, 1), date(2025, 8, 31)) == D("7.56")
