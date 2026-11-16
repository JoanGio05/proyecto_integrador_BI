import pandas as pd
import streamlit as st
from presentacion_participacion import aplicar_navegacion

from dashboard_ficha360 import render_dashboard_ficha360
from dashboard_general import render_dashboard_general
from dashboard_matricula import render_dashboard_matricula
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

# Cargar motor de reglas y datos mock
reglas = cargar_reglas_json("reglas_materias.json")
df_calificaciones = pd.read_csv("datos_mock.csv")
df_condiciones, alertas = calcular_condiciones_estudiantes(df_calificaciones, reglas)

# Mostrar las alertas del cálculo, si existen.
for alerta in alertas:
    st.warning(alerta)

# Navegación
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
        "Dashboard 6: Ficha 360°",
        "Dashboard 7: Matrícula y Alertas",
    ],
    format_func=lambda vista: vista.split(": ", 1)[-1],
    label_visibility="collapsed", key="navegacion_vistas", width="stretch",
)

# Los dashboards 1 y 7 abren sus propias tablas (datos reales) desde corte.py.
if vista_sel == "Dashboard 1: General":
    render_dashboard_general()
elif vista_sel == "Dashboard 2: Participación":
    render_dashboard_participacion()
elif vista_sel == "Dashboard 3: Trazabilidad":
    render_dashboard_trazabilidad()
elif vista_sel == "Dashboard 7: Matrícula y Alertas":
    render_dashboard_matricula()
elif vista_sel == "Dashboard 4: Rendimiento":
    render_dashboard_rendimiento(df_calificaciones, df_condiciones)
elif vista_sel == "Dashboard 6: Ficha 360°":
    render_dashboard_ficha360(df_calificaciones, df_condiciones)
