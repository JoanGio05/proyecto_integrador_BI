import pandas as pd
import plotly.express as px
import streamlit as st


def render_dashboard_rendimiento(
    df_calificaciones: pd.DataFrame, df_condiciones: pd.DataFrame
):
    """Renderiza el Dashboard 4: Rendimiento Académico en Streamlit."""
    st.title("📊 Dashboard 4: Rendimiento Académico")
    st.markdown(
        "Análisis comparativo de calificaciones por evaluación, dispersión, asistencia y distribución de estados académicos."
    )

    if df_condiciones.empty:
        st.warning("No hay datos de condiciones académicas disponibles.")
        return

    # --- SIDEBAR DE FILTROS ---
    st.sidebar.header("Filtros - Rendimiento")

    col_materia = (
        "nombre_materia"
        if "nombre_materia" in df_condiciones.columns
        and df_condiciones["nombre_materia"].notna().any()
        else "materia"
    )

    materias_disponibles = ["Todas"] + sorted(
        df_condiciones[col_materia].dropna().astype(str).unique().tolist()
    )
    materia_sel = st.sidebar.selectbox("Materia", materias_disponibles)

    condiciones_disponibles = ["Todas", "promociona", "regular", "libre"]
    condicion_sel = st.sidebar.selectbox("Condición", condiciones_disponibles)

    # --- FILTRADO DE DATOS ---
    df_cond_filtered = df_condiciones.copy()
    df_calif_filtered = df_calificaciones.copy()

    if materia_sel != "Todas":
        df_cond_filtered = df_cond_filtered[
            df_cond_filtered[col_materia] == materia_sel
        ]
        df_calif_filtered = df_calif_filtered[
            df_calif_filtered[col_materia] == materia_sel
        ]

    if condicion_sel != "Todas":
        df_cond_filtered = df_cond_filtered[
            df_cond_filtered["condicion"] == condicion_sel
        ]
        pares_validos = df_cond_filtered[["id_alumno", "materia"]].drop_duplicates()
        df_calif_filtered = df_calif_filtered.merge(
            pares_validos, on=["id_alumno", "materia"], how="inner"
        )

    # --- KPIS PRINCIPALES ---
    total_alumnos = len(df_cond_filtered)
    prom_nota_norm = (
        df_cond_filtered["nota_normalizada"].mean()
        if total_alumnos > 0
        else 0.0
    )

    cant_prom = len(df_cond_filtered[df_cond_filtered["condicion"] == "promociona"])
    cant_reg = len(df_cond_filtered[df_cond_filtered["condicion"] == "regular"])
    cant_lib = len(df_cond_filtered[df_cond_filtered["condicion"] == "libre"])

    pct_prom = (cant_prom / total_alumnos * 100) if total_alumnos > 0 else 0
    pct_reg = (cant_reg / total_alumnos * 100) if total_alumnos > 0 else 0
    pct_lib = (cant_lib / total_alumnos * 100) if total_alumnos > 0 else 0

    # Cálculo de impacto de recuperatorios en la selección
    if "categoria_evaluacion" in df_calif_filtered.columns:
        mask_recup = (
            df_calif_filtered["categoria_evaluacion"]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("recuperatorio")
        )
    else:
        mask_recup = (
            df_calif_filtered["tipo_evaluacion"]
            .astype(str)
            .str.lower()
            .str.contains("recuperatorio", na=False)
        )

    df_recup_validos = df_calif_filtered[
        mask_recup & df_calif_filtered["nota"].notna()
    ]
    pares_recup = df_recup_validos[["id_alumno", "materia"]].drop_duplicates()
    cant_recup = len(pares_recup)
    if cant_recup > 0:
        cond_recup = df_cond_filtered.merge(
            pares_recup, on=["id_alumno", "materia"], how="inner"
        )
        aprobados_recup = int(
            cond_recup["condicion"].isin(["promociona", "regular"]).sum()
        )
        texto_recup = f"{cant_recup} ({aprobados_recup} reg/prom)"
    else:
        texto_recup = "0"

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Estudiantes", f"{total_alumnos}")
    col2.metric("Promedio Normalizado", f"{prom_nota_norm:.1f}%")
    col3.metric("Promocionados", f"{cant_prom} ({pct_prom:.1f}%)")
    col4.metric("Regulares", f"{cant_reg} ({pct_reg:.1f}%)")
    col5.metric("Libres", f"{cant_lib} ({pct_lib:.1f}%)")
    col6.metric("Rindieron Recup.", texto_recup)

    st.markdown("---")

    # --- MAPA DE COLORES INSTITUCIONAL (SEMÁFORO) ---
    color_map = {
        "promociona": "#2ca02c",
        "regular": "#ff7f0e",
        "libre": "#d62728",
    }
    orden_condiciones = ["promociona", "regular", "libre"]

    # --- FILA 1: DISTRIBUCIÓN GENERAL Y POR MATERIA ---
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Distribución General de Condición")
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
                category_orders={"condicion": orden_condiciones},
                title="Proporción Global por Estado Académico",
            )
            st.plotly_chart(fig_donut, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

    with col_chart2:
        st.subheader("Condición Final por Materia (%)")
        if not df_cond_filtered.empty:
            df_mat_cond = (
                df_cond_filtered.groupby([col_materia, "condicion"])
                .size()
                .reset_index(name="cantidad")
            )
            totales_mat = df_mat_cond.groupby(col_materia)["cantidad"].transform("sum")
            df_mat_cond["porcentaje"] = (
                df_mat_cond["cantidad"] / totales_mat * 100
            ).round(1)
            df_mat_cond["etiqueta"] = df_mat_cond["porcentaje"].astype(str) + "%"

            fig_stack = px.bar(
                df_mat_cond,
                x=col_materia,
                y="porcentaje",
                color="condicion",
                text="etiqueta",
                hover_data=["cantidad"],
                color_discrete_map=color_map,
                category_orders={"condicion": orden_condiciones},
                labels={
                    col_materia: "Materia",
                    "porcentaje": "Porcentaje de Estudiantes (%)",
                    "condicion": "Condición",
                },
                title="Comparativa de Estados Académicos por Cátedra",
            )
            fig_stack.update_layout(yaxis_range=[0, 100])
            st.plotly_chart(fig_stack, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

    # --- FILA 2: HISTOGRAMA Y DISPERSIÓN POR EXAMEN ---
    col_hist, col_box = st.columns(2)

    with col_hist:
        st.subheader("Distribución de Notas Normalizadas")
        if not df_cond_filtered.empty:
            fig_hist = px.histogram(
                df_cond_filtered,
                x="nota_normalizada",
                nbins=10,
                color="condicion",
                color_discrete_map=color_map,
                category_orders={"condicion": orden_condiciones},
                labels={
                    "nota_normalizada": "Nota Normalizada (%)",
                    "count": "Cantidad",
                },
                title="Histograma de Calificaciones Finales (0-100%)",
            )
            fig_hist.update_layout(bargap=0.1)
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

    with col_box:
        st.subheader("Dispersión de Notas por Evaluación")
        df_calif_validas = df_calif_filtered[df_calif_filtered["nota"].notna()].copy()
        if not df_calif_validas.empty:
            col_eval = (
                "instrumento"
                if "instrumento" in df_calif_validas.columns
                else "tipo_evaluacion"
            )
            fig_box = px.box(
                df_calif_validas,
                x=col_eval,
                y="nota_pct",
                color=col_materia,
                points="outliers",
                labels={
                    col_eval: "Instrumento de Evaluación",
                    "nota_pct": "Calificación (%)",
                    col_materia: "Materia",
                },
                title="Mediana, Rango Intercuartílico y Outliers por Examen",
            )
            fig_box.update_layout(yaxis_range=[0, 105])
            fig_stack.update_xaxes(tickangle=30)
            st.plotly_chart(fig_box, use_container_width=True)
        else:
            st.info("Sin registros de evaluaciones con nota numérica.")

    st.markdown("---")

    # --- FILA 3: RENDIMIENTO PROMEDIO Y TASA DE ASISTENCIA POR INSTRUMENTO ---
    st.subheader("Análisis por Instrumento de Evaluación")
    df_calif_validas = df_calif_filtered[df_calif_filtered["nota"].notna()].copy()

    if not df_calif_validas.empty:
        col_eval = (
            "instrumento"
            if "instrumento" in df_calif_validas.columns
            else "tipo_evaluacion"
        )
        df_eval = (
            df_calif_validas.groupby([col_materia, col_eval])
            .agg(
                nota_promedio_pct=("nota_pct", "mean"),
                rindieron=("id_alumno", "nunique"),
            )
            .reset_index()
        )

        # Total de estudiantes en cada materia (según los filtros activos) para calcular asistencia
        totales_cohorte = (
            df_cond_filtered.groupby(col_materia)["id_alumno"]
            .nunique()
            .reset_index(name="total_cohorte")
        )
        df_eval = df_eval.merge(totales_cohorte, on=col_materia, how="left")
        df_eval["asistencia_pct"] = (
            (df_eval["rindieron"] / df_eval["total_cohorte"] * 100)
            .clip(0, 100)
            .round(1)
        )
        df_eval["ausentes"] = (
            df_eval["total_cohorte"] - df_eval["rindieron"]
        ).clip(lower=0)

        col_ev1, col_ev2 = st.columns(2)

        with col_ev1:
            fig_bar = px.bar(
                df_eval,
                x=col_eval,
                y="nota_promedio_pct",
                color=col_materia,
                barmode="group",
                text_auto=".1f",
                hover_data=["rindieron"],
                labels={
                    col_eval: "Instrumento de Evaluación",
                    "nota_promedio_pct": "Rendimiento Promedio (%)",
                    col_materia: "Materia",
                },
                title="Rendimiento Promedio (%) sobre Exámenes Rendidos",
            )
            fig_bar.update_layout(yaxis_range=[0, 105])
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_ev2:
            fig_asist = px.bar(
                df_eval,
                x=col_eval,
                y="asistencia_pct",
                color=col_materia,
                barmode="group",
                text_auto=".1f",
                hover_data=["rindieron", "ausentes", "total_cohorte"],
                labels={
                    col_eval: "Instrumento de Evaluación",
                    "asistencia_pct": "Asistencia al Examen (%)",
                    col_materia: "Materia",
                },
                title="Tasa de Asistencia por Examen (% de la Cohorte)",
            )
            fig_asist.update_layout(yaxis_range=[0, 105])
            st.plotly_chart(fig_asist, use_container_width=True)
    else:
        st.info("Sin registros de evaluaciones asociadas.")

    # --- TABLA DETALLADA ---
    with st.expander("🔍 Explorar Padrón y Resultados Calculados"):
        cols_mostrar = [
            c
            for c in [
                "id_alumno",
                "nombre_completo",
                "nombre_materia",
                "nota",
                "puntaje_tomado",
                "nota_normalizada",
                "condicion",
            ]
            if c in df_cond_filtered.columns
        ]
        st.dataframe(df_cond_filtered[cols_mostrar], use_container_width=True)