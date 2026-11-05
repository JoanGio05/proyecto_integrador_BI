import pandas as pd
import plotly.express as px
import streamlit as st


def render_dashboard_ficha360(
    df_calificaciones: pd.DataFrame,
    df_condiciones: pd.DataFrame,
    df_participacion: pd.DataFrame = None,
):
    """Renderiza el Dashboard 6: Ficha 360° del Alumno."""
    st.title("👤 Dashboard 6: Ficha 360° del Estudiante")
    st.markdown(
        "Vista consolidada individual de desempeño, semaforización académica y trazabilidad."
    )

    if df_condiciones.empty:
        st.warning("No hay datos de alumnos disponibles.")
        return

    # --- SELECCIÓN DE ALUMNO ---
    alumnos_lista = sorted(
        df_condiciones["id_alumno"].astype(str).unique().tolist()
    )
    alumno_sel = st.sidebar.selectbox("Seleccionar Legajo / ID Alumno", alumnos_lista)

    # --- FILTRADO POR ALUMNO ---
    df_alumno_cond = df_condiciones[
        df_condiciones["id_alumno"].astype(str) == alumno_sel
    ]
    df_alumno_calif = df_calificaciones[
        df_calificaciones["id_alumno"].astype(str) == alumno_sel
    ]

    st.header(f"Ficha del Estudiante: `{alumno_sel}`")

    # --- SEMÁFORO DE CONDICIONES POR MATERIA ---
    st.subheader("🚥 Estado Académico (Semáforo)")
    cols_materias = st.columns(max(len(df_alumno_cond), 1))

    color_emoji = {
        "promociona": "🟢 Promociona",
        "regular": "🟡 Regular",
        "libre": "🔴 Libre",
    }

    for idx, (_, row) in enumerate(df_alumno_cond.iterrows()):
        materia_nom = row["materia"].upper()
        cond = row["condicion"]
        nota_final = row["nota"]
        nota_norm = row["nota_normalizada"]

        with cols_materias[idx % len(cols_materias)]:
            st.metric(
                label=materia_nom,
                value=f"{nota_final} pts ({nota_norm:.1f}%)",
                delta=color_emoji.get(cond, cond),
            )

    st.markdown("---")

    # --- FILA DE ANÁLISIS DETALLADO ---
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("📝 Historial de Calificaciones")
        if not df_alumno_calif.empty:
            fig_bar = px.bar(
                df_alumno_calif,
                x="tipo_evaluacion",
                y="nota",
                color="materia",
                text="nota",
                labels={
                    "tipo_evaluacion": "Evaluación",
                    "nota": "Nota Obtenida",
                    "materia": "Materia",
                },
                title="Desglose de Exámenes y Trabajos",
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No hay registros de evaluaciones para este alumno.")

    with col_der:
        st.subheader("📈 Progreso Académico Normalizado")
        if not df_alumno_cond.empty:
            fig_radar = px.line_polar(
                df_alumno_cond,
                r="nota_normalizada",
                theta="materia",
                line_close=True,
                range_r=[0, 100],
                title="Desempeño Normalizado por Materia (0-100%)",
            )
            st.plotly_chart(fig_radar, use_container_width=True)

    # --- TABLA RESUMEN DEL ALUMNO ---
    st.markdown("---")
    st.subheader("📋 Resumen Consolidado del Estudiante")
    st.dataframe(df_alumno_cond, use_container_width=True)