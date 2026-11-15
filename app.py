import streamlit as st

from control_carga import validar_alumnos_matriculados
from corte import cargar_tablas
from dashboard_ficha360 import render_dashboard_ficha360
from dashboard_general import render_dashboard_general
from dashboard_matricula import render_dashboard_matricula
from dashboard_rendimiento import render_dashboard_rendimiento
from evaluador_condiciones import (
    calcular_condiciones_estudiantes,
    cargar_reglas_json,
)

st.set_page_config(
    page_title="Seguimiento Académico LMS",
    page_icon="🎓",
    layout="wide",
)

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
st.sidebar.title("Navegación")
vista_sel = st.sidebar.radio(
    "Seleccionar Vista",
    [
        "Dashboard 1: General",
        "Dashboard 4: Rendimiento",
        "Dashboard 6: Ficha 360°",
        "Dashboard 7: Matrícula y Alertas",
    ],
)

# 4. Validar consistencia entre calificaciones reales y padrón de matrícula
df_matricula_activa = df_matricula[df_matricula["activo"] == True]
df_no_matriculados, alertas_matricula = validar_alumnos_matriculados(
    df_calificaciones, df_matricula_activa
)

# 5. Renderizado de la vista seleccionada
# 5. Renderizado de la vista seleccionada
if vista_sel == "Dashboard 1: General":
    render_dashboard_general()
elif vista_sel == "Dashboard 7: Matrícula y Alertas":
    render_dashboard_matricula()
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