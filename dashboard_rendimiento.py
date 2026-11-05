import pandas as pd
import plotly.express as px
import streamlit as st


def render_dashboard_rendimiento(
    df_calificaciones: pd.DataFrame, df_condiciones: pd.DataFrame
):
    """Renderiza el Dashboard 4: Rendimiento Académico en Streamlit."""
    st.title("📊 Dashboard 4: Rendimiento Académico")
    st.markdown(
        "Análisis comparativo de calificaciones por evaluación y distribución de estados académicos."
    )

    # --- SIDEBAR DE FILTROS ---
    st.sidebar.header("Filtros - Rendimiento")

    materias_disponibles = ["Todas"] + sorted(
        df_condiciones["materia"].astype(str).unique().tolist()
    )
    materia_sel = st.sidebar.selectbox("Materia", materias_disponibles)

    condiciones_disponibles = ["Todas", "promociona", "regular", "libre"]
    condicion_sel = st.sidebar.selectbox("Condición", condiciones_disponibles)

    # --- FILTRADO DE DATOS ---
    df_cond_filtered = df_condiciones.copy()
    df_calif_filtered = df_calificaciones.copy()

    if materia_sel != "Todas":
        df_cond_filtered = df_cond_filtered[
            df_cond_filtered["materia"] == materia_sel
        ]
        df_calif_filtered = df_calif_filtered[
            df_calif_filtered["materia"] == materia_sel
        ]

    if condicion_sel != "Todas":
        df_cond_filtered = df_cond_filtered[
            df_cond_filtered["condicion"] == condicion_sel
        ]
        alumnos_validos = df_cond_filtered["id_alumno"].unique()
        df_calif_filtered = df_calif_filtered[
            df_calif_filtered["id_alumno"].isin(alumnos_validos)
        ]

    # --- KPIS PRINCIPALES ---
    total_alumnos = len(df_cond_filtered)
    prom_nota_norm = (
        df_cond_filtered["nota_normalizada"].mean()
        if total_alumnos > 0
        else 0.0
    )

    cant_prom = len(
        df_cond_filtered[df_cond_filtered["condicion"] == "promociona"]
    )
    cant_reg = len(
        df_cond_filtered[df_cond_filtered["condicion"] == "regular"]
    )
    cant_lib = len(df_cond_filtered[df_cond_filtered["condicion"] == "libre"])

    pct_prom = (cant_prom / total_alumnos * 100) if total_alumnos > 0 else 0
    pct_reg = (cant_reg / total_alumnos * 100) if total_alumnos > 0 else 0
    pct_lib = (cant_lib / total_alumnos * 100) if total_alumnos > 0 else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Estudiantes", f"{total_alumnos}")
    col2.metric("Promedio Normalizado", f"{prom_nota_norm:.1f}%")
    col3.metric("Promocionados", f"{cant_prom} ({pct_prom:.1f}%)")
    col4.metric("Regulares", f"{cant_reg} ({pct_reg:.1f}%)")
    col5.metric("Libres", f"{cant_lib} ({pct_lib:.1f}%)")

    st.markdown("---")

    # --- MAPA DE COLORES INSTITUCIONAL (SEMÁFORO) ---
    color_map = {
        "promociona": "#2ca02c",  # Verde
        "regular": "#ff7f0e",  # Amarillo / Naranja
        "libre": "#d62728",  # Rojo
    }

    # --- FILA 1: GRÁFICOS DE DISTRIBUCIÓN ---
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Distribución de Condición Final")
        if not df_cond_filtered.empty:
            df_counts = (
                df_cond_filtered["condicion"]
                .value_counts()
                .reset_index(name="cantidad")
            )
            df_counts.columns = ["condicion", "cantidad"]

            fig_donut = px.pie(
                df_counts,
                names="condicion",
                values="cantidad",
                hole=0.4,
                color="condicion",
                color_discrete_map=color_map,
                title="Proporción por Estado Académico",
            )
            st.plotly_chart(fig_donut, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

    with col_chart2:
        st.subheader("Distribución de Notas Normalizadas")
        if not df_cond_filtered.empty:
            fig_hist = px.histogram(
                df_cond_filtered,
                x="nota_normalizada",
                nbins=10,
                color="condicion",
                color_discrete_map=color_map,
                labels={
                    "nota_normalizada": "Nota Normalizada (%)",
                    "count": "Cantidad",
                },
                title="Histograma de Calificaciones (0-100%)",
            )
            fig_hist.update_layout(bargap=0.1)
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

    st.markdown("---")

    # --- FILA 2: COMPARACIÓN DE INSTRUMENTOS DE EVALUACIÓN ---
    st.subheader("Comparación por Instrumento de Evaluación")
    if not df_calif_filtered.empty:
        df_eval = (
            df_calif_filtered.groupby(["materia", "tipo_evaluacion"])["nota"]
            .agg(["mean", "count"])
            .reset_index()
        )
        df_eval.columns = [
            "materia",
            "tipo_evaluacion",
            "nota_promedio",
            "cantidad",
        ]

        fig_bar = px.bar(
            df_eval,
            x="tipo_evaluacion",
            y="nota_promedio",
            color="materia",
            barmode="group",
            text_auto=".1f",
            labels={
                "tipo_evaluacion": "Evaluación",
                "nota_promedio": "Nota Promedio",
                "materia": "Materia",
            },
            title="Promedio Obtenido por Tipo de Examen/Evaluación",
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Sin registros de evaluaciones asociadas.")

    # --- TABLA DETALLADA ---
    with st.expander("🔍 Explorar Padrón y Resultados Calculados"):
        st.dataframe(df_cond_filtered, use_container_width=True)