"""Carga los patronos y sucursales de Minoshkas (tomados del ERP) si aún no existen.

Uso:
    python -m scripts.cargar_base
Es seguro correrlo varias veces: no duplica registros.
"""
from app.db import SessionLocal, init_db
from app.models import Empresa, Sucursal

EMPRESAS = [
    # (id en el ERP, razón social, nombre comercial)
    ("e-sa", "Inversiones Santa Cruz, S.A.", "Minoshkas Salón"),
    ("e-smq", "Sandra Marquez", "Minoshkas Salón"),
    ("e-peq", "Edgar Estuardo Santa Cruz", "Minoshkas Girl"),
    ("e-asc", "Alejandra Santa Cruz", "Minoshkas Salón"),
    ("e-esm", "Estuardo Santa Cruz Marquez", "Minoshkas Salón"),
]

SUCURSALES = [
    # (id en el ERP, nombre, código, municipio, departamento)
    ("s-7ma", "7ma", "7MA", "Antigua Guatemala", "Sacatepéquez"),
    ("s-4ca", "4ta Calle", "4CA", "Antigua Guatemala", "Sacatepéquez"),
    ("s-5ca", "5ta Calle", "5CA", "Antigua Guatemala", "Sacatepéquez"),
    ("s-gla", "Glamour", "GLA", "Antigua Guatemala", "Sacatepéquez"),
    ("s-bb1", "Bamboo 1", "BB1", "Antigua Guatemala", "Sacatepéquez"),
    ("s-bbj", "Bamboo Jr", "BBJ", "Antigua Guatemala", "Sacatepéquez"),
    ("s-par", "Parque", "PAR", "", ""),
    ("s-pan", "Panorama", "PAN", "Antigua Guatemala", "Sacatepéquez"),
    ("s-pue", "Puertas", "PUE", "San Lucas Sacatepéquez", "Sacatepéquez"),
    ("s-and", "Andaria", "AND", "Chimaltenango", "Chimaltenango"),
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        nuevas = 0
        for erp_id, razon, comercial in EMPRESAS:
            if not db.query(Empresa).filter(Empresa.erp_id == erp_id).first():
                db.add(Empresa(erp_id=erp_id, razon_social=razon, nombre_comercial=comercial))
                nuevas += 1
        for erp_id, nombre, codigo, municipio, depto in SUCURSALES:
            if not db.query(Sucursal).filter(Sucursal.erp_id == erp_id).first():
                db.add(Sucursal(erp_id=erp_id, nombre=nombre, codigo=codigo, municipio=municipio, departamento=depto))
                nuevas += 1
        db.commit()
        print(f"Registros nuevos: {nuevas}")


if __name__ == "__main__":
    main()
