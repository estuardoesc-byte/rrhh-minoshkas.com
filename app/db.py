from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    from pathlib import Path

    Path(DATABASE_URL.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    migrar()


def _literal(valor) -> str:
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def migrar():
    """Pone al día una base instalada con una versión anterior, sin perder datos.

    - Agrega las columnas nuevas de cada tabla con su valor por omisión.
    - Permite planillas sin patrono (la administrativa junta a varios).
    """
    from sqlalchemy import inspect

    insp = inspect(engine)
    with engine.begin() as conn:
        for tabla in Base.metadata.sorted_tables:
            if not insp.has_table(tabla.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabla.name)}
            for col in tabla.columns:
                if col.name in existentes:
                    continue
                tipo = col.type.compile(engine.dialect)
                defecto = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                sql = f'ALTER TABLE {tabla.name} ADD COLUMN {col.name} {tipo}'
                if defecto is not None:
                    sql += f" DEFAULT {_literal(defecto)}"
                conn.exec_driver_sql(sql)

    insp = inspect(engine)
    if not insp.has_table("planillas"):
        return
    col = next(c for c in insp.get_columns("planillas") if c["name"] == "empresa_id")
    if col["nullable"]:
        return
    if engine.dialect.name != "sqlite":
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE planillas ALTER COLUMN empresa_id DROP NOT NULL")
        return
    # SQLite no cambia la restricción de una columna: se copia la tabla.
    from .models import Planilla

    columnas = ", ".join(c["name"] for c in insp.get_columns("planillas"))
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        conn.commit()
        with conn.begin():
            conn.exec_driver_sql("ALTER TABLE planillas RENAME TO _planillas_anterior")
            Planilla.__table__.create(conn)
            conn.exec_driver_sql(f"INSERT INTO planillas ({columnas}) SELECT {columnas} FROM _planillas_anterior")
            conn.exec_driver_sql("DROP TABLE _planillas_anterior")
        conn.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
        conn.commit()
