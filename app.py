import pandas as pd
import streamlit as st

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

# Cargar motor de reglas y datos mock
reglas = cargar_reglas_json("reglas_materias.json")
df_calificaciones = pd.read_csv("datos_mock.csv")
df_condiciones, alertas = calcular_condiciones_estudiantes(df_calificaciones, reglas)

# Mostrar las alertas del cálculo, si existen.
for alerta in alertas:
    st.warning(alerta)

# Navegación
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

# Los dashboards 1 y 7 abren sus propias tablas (datos reales) desde corte.py.
if vista_sel == "Dashboard 1: General":
    render_dashboard_general()
elif vista_sel == "Dashboard 7: Matrícula y Alertas":
    render_dashboard_matricula()
elif vista_sel == "Dashboard 4: Rendimiento":
    render_dashboard_rendimiento(df_calificaciones, df_condiciones)
elif vista_sel == "Dashboard 6: Ficha 360°":
    render_dashboard_ficha360(df_calificaciones, df_condiciones)