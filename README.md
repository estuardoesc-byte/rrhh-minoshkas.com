# RRHH Minoshkas

Sistema de recursos humanos de Minoshkas, independiente del ERP, según la legislación laboral guatemalteca.

El diseño y las reglas de cálculo están en el documento *Sistema de RRHH Minoshkas: diseño y reglas de cálculo*.

## Qué hace esta versión (paso 2)

- Acceso con correo y contraseña para los administradores (Sandra Marquez, Julio Santa Cruz y Estuardo).
- Patronos: los 5 patronos de Minoshkas, cada uno con su NIT y número patronal de IGSS.
- Sucursales: las 10 sucursales.
- Ficha de cada colaborador: datos personales, laborales, contactos de emergencia, beneficiarios y tarjeta de salud.
- Expediente: carga de foto, DPI, tarjeta de salud, contrato, CV, títulos, cartas, antecedentes y otros (PDF, JPG o PNG hasta 10 MB).
- Historial de cambios de salario, puesto, sucursal, patrono y estado.
- Inicio con alertas: tarjetas de salud vencidas o por vencer, contratos por vencer, salarios bajo el mínimo, colaboradores sin patrono y expedientes incompletos.
- Parámetros legales editables: salario mínimo, bonificación incentivo y porcentajes de IGSS, IRTRA e INTECAP.

Pendiente para los pasos 3 y 4: nóminas quincenales y mensuales, bono 14, aguinaldo, provisiones, liquidaciones, recibos y reportes.

## Probarlo en una computadora

Requiere Python 3.12 o más reciente.

```bash
python -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m scripts.cargar_base      # patronos y sucursales
python -m scripts.crear_usuario "Estuardo Santa Cruz" estuardo@minoshkas.com
uvicorn app.main:app --reload
```

Luego abre http://localhost:8000.

Pruebas automáticas: `pytest`.

## Publicarlo en la nube (Render)

El archivo `render.yaml` crea un servicio web con un disco de 5 GB donde viven la base de datos y los documentos. Costo aproximado: US$7 al mes del plan Starter más unos US$1.25 del disco; Render hace una copia diaria del disco.

1. Crea una cuenta en https://render.com con tu usuario de GitHub.
2. Elige **New > Blueprint** y selecciona el repositorio `rrhh-minoshkas`. Render lee `render.yaml`.
3. Cuando termine, abre la pestaña **Shell** del servicio y corre:
   ```bash
   python -m scripts.cargar_base
   python -m scripts.crear_usuario "Sandra Marquez" <correo de Sandra>
   python -m scripts.crear_usuario "Julio Santa Cruz" <correo de Julio>
   python -m scripts.crear_usuario "Estuardo Santa Cruz" <tu correo>
   ```
4. Entra a la dirección que da Render (termina en `.onrender.com`) y revisa en **Parámetros** que el salario mínimo (Q3,816.90 para 2026) esté vigente.

## Versión anterior en el navegador

`nomina-navegador.html` es la primera página de nómina que ya estaba en este repositorio (antes `index.html`). Guarda los datos solo en el navegador. Se conserva como referencia mientras la aplicación nueva incorpora las planillas de anticipo y fin de mes.

## Configuración

| Variable | Para qué sirve | Valor por omisión |
| --- | --- | --- |
| `DATABASE_URL` | Base de datos (SQLite o PostgreSQL) | `sqlite:///datos/rrhh.db` |
| `UPLOAD_DIR` | Carpeta de documentos | `datos/documentos` |
| `SECRET_KEY` | Firma de la sesión; debe ser larga y secreta en producción | valor de desarrollo |
| `HTTPS_ONLY` | `1` para que la sesión solo viaje por HTTPS | `0` |
| `MAX_UPLOAD_MB` | Tamaño máximo por documento | `10` |
