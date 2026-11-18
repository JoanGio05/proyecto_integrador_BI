import streamlit as st

import estilo
from presentacion_participacion import aplicar_navegacion
from control_carga import validar_alumnos_matriculados
from corte import cargar_tablas
from dashboard_ficha360 import render_dashboard_ficha360
from dashboard_general import render_dashboard_general
from dashboard_matricula import render_dashboard_matricula
from dashboard_notas_participacion import render_dashboard_notas_participacion
from dashboard_rendimiento import render_dashboard_rendimiento
from dashboard_participacion import render_dashboard_participacion
from dashboard_trazabilidad import render_dashboard_trazabilidad
from evaluador_condiciones import (
    calcular_condiciones_estudiantes,
    cargar_reglas_json,
)

st.set_page_config(
    page_title="Seguimiento Académico LMS",
    page_icon="🎓",
    layout="wide",
)
# Misma tipografía, grilla y paleta en todos los gráficos (guía de estilo, estilo.py).
estilo.aplicar_tema()

# 1. Cargar reglas y tablas reales ya cruzadas y cacheadas desde corte.py
reglas = cargar_reglas_json("reglas_materias.json")
tablas = cargar_tablas()

df_calificaciones = tablas["calificaciones"]
df_participacion = tablas["participacion"]
df_matricula = tablas["matricula"]
df_interacciones = tablas["interacciones"]

# 2. Calcular condiciones académicas sobre las calificaciones reales
df_condiciones, alertas_reglas = calcular_condiciones_estudiantes(
    df_calificaciones, reglas, df_matricula=df_matricula
)

# Enriquecer df_condiciones con nombre_materia y nombre completo del alumno
if not df_condiciones.empty:
    alumnos_dim = tablas["alumno"][["id_alumno", "apellido", "nombre"]].copy()
    alumnos_dim["nombre_completo"] = (
        alumnos_dim["apellido"].fillna("") + ", " + alumnos_dim["nombre"].fillna("")
    ).str.strip(", ")

    materias_dim = tablas["materia"][["materia", "nombre_materia"]].drop_duplicates()

    df_condiciones = df_condiciones.merge(
        alumnos_dim[["id_alumno", "nombre_completo"]], on="id_alumno", how="left"
    ).merge(materias_dim, on="materia", how="left")

# 3. Navegación (se define primero para poder usar vista_sel en los avisos)
aplicar_navegacion()
st.sidebar.title("Seguimiento académico")
st.sidebar.caption("Análisis del campus virtual")
vista_sel = st.sidebar.radio(
    "Dashboards",
    [
        "Dashboard 1: General",
        "Dashboard 2: Participación",
        "Dashboard 3: Trazabilidad",
        "Dashboard 4: Rendimiento",
        "Dashboard 5: Notas vs. Participación",
        "Dashboard 6: Ficha 360°",
        "Dashboard 7: Matrícula y Alertas",
    ],
    label_visibility="collapsed", key="navegacion_vistas",
)

# 4. Validar consistencia entre calificaciones reales y padrón de matrícula
df_matricula_activa = df_matricula[df_matricula["activo"] == True]
df_no_matriculados, alertas_matricula = validar_alumnos_matriculados(
    df_calificaciones, df_matricula_activa
)

# Una materia sin su fila en reglas_materias.json se muestra igual en todos los
# dashboards, con la regla por defecto del evaluador. El aviso dice cuál usa.
materias_sin_regla = tablas["materia"].loc[
    ~tablas["materia"]["materia"].isin(list(reglas)), "nombre_materia"
].sort_values()
for nombre in materias_sin_regla:
    st.warning(
        f"**{nombre}** no tiene su regla en reglas_materias.json: se muestra con la regla por "
        f"defecto (nota sobre lo tomado; regular con 60 %, promoción con 85 %). "
        f"Para usar la de la cátedra, agregá su fila."
    )

# Una materia a la que le falta un archivo se muestra igual, pero sus ceros no son
# reales: sin trazabilidad, todos figuran sin actividad. Se avisa para no confundir
# "falta el dato" con "el alumno no entró".
FUENTES = {
    "matricula": ("padrón", "no tiene inscriptos y queda fuera de los indicadores que cuentan el padrón"),
    "interacciones": ("trazabilidad", "sus alumnos figuran sin actividad aunque hayan entrado"),
    "participacion": ("participación", "no hay tiempo de uso ni avance"),
    "calificaciones": ("notas", "no hay notas ni condición"),
}
for _, fila in tablas["materia"].sort_values("nombre_materia").iterrows():
    faltan = [(dato, efecto) for tabla, (dato, efecto) in FUENTES.items()
              if not tablas[tabla]["materia"].eq(fila["materia"]).any()]
    if faltan:
        datos = [d for d, _ in faltan]
        que = (f"falta el archivo de {datos[0]}" if len(datos) == 1 else
               f"faltan los archivos de {', de '.join(datos[:-1])} y de {datos[-1]}")
        efectos = "; ".join(e for _, e in faltan)
        st.warning(
            f"**{fila['nombre_materia']}**: {que}. {efectos[0].upper() + efectos[1:]}. "
            f"No es un dato real: agregá {'el archivo' if len(datos) == 1 else 'los archivos'} "
            f"en data/raw y volvé a correr cargar_datos.py."
        )

# 5. Renderizado de la vista seleccionada
if vista_sel == "Dashboard 1: General":
    render_dashboard_general()
elif vista_sel == "Dashboard 2: Participación":
    render_dashboard_participacion()
elif vista_sel == "Dashboard 3: Trazabilidad":
    render_dashboard_trazabilidad()
elif vista_sel == "Dashboard 7: Matrícula y Alertas":
    render_dashboard_matricula()
elif vista_sel == "Dashboard 5: Notas vs. Participación":
    render_dashboard_notas_participacion()
elif vista_sel == "Dashboard 4: Rendimiento":
    render_dashboard_rendimiento(df_calificaciones, df_condiciones)
elif vista_sel == "Dashboard 6: Ficha 360°":
    render_dashboard_ficha360(
        df_calificaciones,
        df_condiciones,
        df_participacion,
        df_interacciones,
        df_matricula,
    )
