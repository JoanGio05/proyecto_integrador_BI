import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render_dashboard_ficha360(
    df_calificaciones: pd.DataFrame,
    df_condiciones: pd.DataFrame,
    df_participacion: pd.DataFrame = None,
    df_interacciones: pd.DataFrame = None,
    df_matricula: pd.DataFrame = None,
):
    """Renderiza el Dashboard 6: Ficha 360° del Alumno."""
    st.title("👤 Dashboard 6: Ficha 360° del Estudiante")
    st.markdown(
        "Vista consolidada individual de desempeño, benchmark contra el curso, matrícula y trazabilidad."
    )

    if df_condiciones.empty:
        st.warning("No hay datos de alumnos disponibles.")
        return

    # --- SELECCIÓN DE ALUMNO ---
    alumnos_lista = sorted(
        df_condiciones["id_alumno"].astype(str).unique().tolist()
    )
    nombres_map = {}
    if "nombre_completo" in df_condiciones.columns:
        nombres_map = (
            df_condiciones[["id_alumno", "nombre_completo"]]
            .dropna()
            .drop_duplicates()
            .set_index("id_alumno")["nombre_completo"]
            .to_dict()
        )

    alumno_sel = st.sidebar.selectbox(
        "Seleccionar Legajo / ID Alumno",
        alumnos_lista,
        format_func=lambda x: f"{x} - {nombres_map[x]}" if x in nombres_map else x,
    )

    # --- FILTRADO POR ALUMNO ---
    df_alumno_cond = df_condiciones[
        df_condiciones["id_alumno"].astype(str) == alumno_sel
    ].copy()
    df_alumno_calif = df_calificaciones[
        df_calificaciones["id_alumno"].astype(str) == alumno_sel
    ].copy()

    titulo = (
        f"{nombres_map[alumno_sel]} (`{alumno_sel}`)"
        if alumno_sel in nombres_map
        else f"`{alumno_sel}`"
    )
    st.header(f"Ficha del Estudiante: {titulo}")

    # --- SEMÁFORO DE CONDICIONES POR MATERIA ---
    st.subheader("🚥 Estado Académico (Semáforo)")
    cols_materias = st.columns(max(len(df_alumno_cond), 1))

    color_emoji = {
        "promociona": "🟢 Promociona",
        "regular": "🟡 Regular",
        "libre": "🔴 Libre",
    }

    for idx, (_, row) in enumerate(df_alumno_cond.iterrows()):
        materia_nom = str(row.get("nombre_materia") or row["materia"]).upper()
        cond = row["condicion"]
        nota_final = row["nota"]
        nota_norm = row["nota_normalizada"]

        puntaje_tomado = row.get("puntaje_tomado", 100.0)
        valor_metrica = (
            f"{nota_final} / {puntaje_tomado:g} pts ({nota_norm:.1f}%)"
            if puntaje_tomado != 100.0
            else f"{nota_final} pts ({nota_norm:.1f}%)"
        )
        with cols_materias[idx % len(cols_materias)]:
            st.metric(
                label=materia_nom,
                value=valor_metrica,
                delta=color_emoji.get(cond, cond),
            )

    # --- MÉTRICAS Y DESGLOSE POR MATERIA (MATRÍCULA Y PARTICIPACIÓN) ---
    df_alumno_part = pd.DataFrame()
    if df_participacion is not None and not df_participacion.empty:
        df_alumno_part = df_participacion[
            df_participacion["id_alumno"].astype(str) == alumno_sel
        ].copy()

    if not df_alumno_part.empty:
        st.markdown("---")
        st.subheader("🌐 Participación en el Campus")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric(
            "Interacciones Totales",
            f"{int(df_alumno_part['interacciones'].sum())}",
        )
        p2.metric(
            "Tiempo en Plataforma",
            f"{df_alumno_part['tiempo_uso_horas'].sum():.2f} hs",
        )
        p3.metric(
            "Avance Promedio",
            f"{df_alumno_part['avance_pct'].mean():.1f}%",
        )
        p4.metric(
            "Participó en Foros",
            "Sí" if df_alumno_part["participo_en_foros"].any() else "No",
        )

    # Tabla desglosada por materia (combinando condición, participación y matrícula)
    resumen_materias = df_alumno_cond[["materia", "nombre_materia", "condicion"]].copy()

    if not df_alumno_part.empty:
        part_cols = [
            c
            for c in [
                "materia",
                "avance_pct",
                "tiempo_uso_horas",
                "interacciones",
                "ultima_interaccion",
            ]
            if c in df_alumno_part.columns
        ]
        part_mat = df_alumno_part[part_cols].drop_duplicates("materia")
        resumen_materias = resumen_materias.merge(part_mat, on="materia", how="left")

        if "ultima_interaccion" in resumen_materias.columns:
            resumen_materias["ultima_interaccion"] = pd.to_datetime(
                resumen_materias["ultima_interaccion"], errors="coerce"
            )
            # Fecha de referencia del corte (último registro disponible en interacciones)
            if (
                df_interacciones is not None
                and not df_interacciones.empty
                and "fecha_hora" in df_interacciones.columns
            ):
                fecha_ref = pd.to_datetime(df_interacciones["fecha_hora"]).max()
            else:
                fecha_ref = resumen_materias["ultima_interaccion"].max()

            if pd.notna(fecha_ref):
                resumen_materias["dias_sin_ingresar"] = (
                    fecha_ref - resumen_materias["ultima_interaccion"]
                ).dt.days

    if df_matricula is not None and not df_matricula.empty:
        mat_al = df_matricula[
            df_matricula["id_alumno"].astype(str) == alumno_sel
        ].copy()
        if not mat_al.empty:
            if "es_ultima_inscripcion" in mat_al.columns:
                mat_al = mat_al[mat_al["es_ultima_inscripcion"] == True]
            else:
                mat_al = mat_al.sort_values("fecha_inscripcion").drop_duplicates(
                    "materia", keep="last"
                )
            cols_mat = [
                c
                for c in ["materia", "estado_inscripcion", "comision"]
                if c in mat_al.columns
            ]
            resumen_materias = resumen_materias.merge(
                mat_al[cols_mat], on="materia", how="left"
            )
            resumen_materias["estado_inscripcion"] = resumen_materias[
                "estado_inscripcion"
            ].fillna("Sin inscripción")
        else:
            resumen_materias["estado_inscripcion"] = "Sin inscripción"

    cols_tabla_mat = {
        "nombre_materia": "Materia",
        "estado_inscripcion": "Estado Matrícula",
        "comision": "Comisión",
        "condicion": "Condición",
        "avance_pct": "Avance (%)",
        "tiempo_uso_horas": "Tiempo (hs)",
        "interacciones": "Interacciones",
        "ultima_interaccion": "Último Ingreso",
        "dias_sin_ingresar": "Días sin Ingresar",
    }
    cols_presentes = [c for c in cols_tabla_mat if c in resumen_materias.columns]
    if len(cols_presentes) > 2:
        st.caption("Situación administrativa y de participación por asignatura:")
        st.dataframe(
            resumen_materias[cols_presentes].rename(columns=cols_tabla_mat),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Último Ingreso": st.column_config.DatetimeColumn(
                    format="DD/MM/YYYY HH:mm"
                ),
                "Avance (%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    st.markdown("---")

    # --- FILA DE ANÁLISIS DETALLADO DE CALIFICACIONES ---
    col_izq, col_der = st.columns(2)
    eje_x = (
        "instrumento"
        if "instrumento" in df_calificaciones.columns
        else "tipo_evaluacion"
    )
    col_color = (
        "nombre_materia"
        if "nombre_materia" in df_calificaciones.columns
        else "materia"
    )

    # Benchmark del curso por materia y evaluación (solo exámenes con nota numérica)
    df_calif_validas_global = df_calificaciones[
        df_calificaciones["nota"].notna()
    ].copy()
    df_benchmark = (
        df_calif_validas_global.groupby(["materia", eje_x], as_index=False)["nota_pct"]
        .mean()
        .rename(columns={"nota_pct": "promedio_curso_pct"})
    )
    df_benchmark["promedio_curso_pct"] = df_benchmark["promedio_curso_pct"].round(1)

    with col_izq:
        st.subheader("📝 Calificaciones vs. Promedio del Curso")
        if not df_alumno_calif.empty:
            df_plot_calif = df_alumno_calif.merge(
                df_benchmark, on=["materia", eje_x], how="left"
            )
            fig_bar = px.bar(
                df_plot_calif,
                x=eje_x,
                y="nota_pct",
                color=col_color,
                text="nota",
                labels={
                    eje_x: "Evaluación",
                    "nota_pct": "Calificación (%)",
                    col_color: "Materia",
                },
                title="Nota del Alumno (%) vs. Media de la Cátedra",
            )
            fig_bar.add_trace(
                go.Scatter(
                    x=df_plot_calif[eje_x],
                    y=df_plot_calif["promedio_curso_pct"],
                    mode="markers+lines",
                    name="Promedio del curso (%)",
                    marker=dict(color="#111111", size=9, symbol="diamond"),
                    line=dict(color="#555555", dash="dot"),
                )
            )
            fig_bar.update_layout(yaxis_range=[0, 108])
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No hay registros de evaluaciones rendidas para este alumno.")

    with col_der:
        st.subheader("📈 Progreso Académico Normalizado")
        if not df_alumno_cond.empty:
            theta_col = (
                "nombre_materia"
                if "nombre_materia" in df_alumno_cond.columns
                else "materia"
            )
            fig_radar = px.line_polar(
                df_alumno_cond,
                r="nota_normalizada",
                theta=theta_col,
                line_close=True,
                markers=True,
                range_r=[0, 100],
                title="Desempeño Normalizado por Materia (0-100%)",
            )
            st.plotly_chart(fig_radar, use_container_width=True)

    # --- DETALLE COMPLETO DE EXÁMENES (INCLUYENDO AUSENTES) ---
    materias_alumno = df_alumno_cond["materia"].unique().tolist()
    df_evals_catedra = df_calificaciones[
        df_calificaciones["materia"].isin(materias_alumno)
    ].copy()

    if not df_evals_catedra.empty:
        cols_grupo_eval = [
            c
            for c in [
                "materia",
                "nombre_materia",
                eje_x,
                "categoria_evaluacion",
                "nota_maxima",
            ]
            if c in df_evals_catedra.columns
        ]
        catalogo_evals = (
            df_evals_catedra[cols_grupo_eval]
            .drop_duplicates(subset=["materia", eje_x])
            .merge(df_benchmark, on=["materia", eje_x], how="left")
        )

        cols_al_eval = [
            c
            for c in ["materia", eje_x, "nota", "nota_pct", "observacion"]
            if c in df_alumno_calif.columns
        ]
        detalle_evals = catalogo_evals.merge(
            df_alumno_calif[cols_al_eval], on=["materia", eje_x], how="left"
        )

        def _estado_examen(fila):
            if pd.notna(fila.get("nota")):
                return "Rendido"
            cat = str(fila.get("categoria_evaluacion", "")).lower()
            if cat == "recuperatorio":
                return "No rendido (Opcional)"
            return "Ausente (0 pts)"

        detalle_evals["estado_examen"] = detalle_evals.apply(_estado_examen, axis=1)
        detalle_evals["nota_mostrada"] = detalle_evals["nota"].fillna(0.0)
        detalle_evals["nota_pct_mostrada"] = detalle_evals["nota_pct"].fillna(0.0)

        st.subheader("📑 Detalle de Evaluaciones Tomadas (Incluyendo Ausentes)")
        cols_ver_eval = {
            "nombre_materia": "Materia",
            eje_x: "Evaluación",
            "categoria_evaluacion": "Categoría",
            "estado_examen": "Estado",
            "nota_mostrada": "Nota",
            "nota_maxima": "Máximo",
            "nota_pct_mostrada": "Alumno (%)",
            "promedio_curso_pct": "Curso (%)",
        }
        cols_ok = [c for c in cols_ver_eval if c in detalle_evals.columns]
        st.dataframe(
            detalle_evals[cols_ok].rename(columns=cols_ver_eval),
            use_container_width=True,
            hide_index=True,
        )

    # --- TRAZABILIDAD DEL ESTUDIANTE ---
    if df_interacciones is not None and not df_interacciones.empty:
        df_alumno_inter = df_interacciones[
            df_interacciones["id_alumno"].astype(str) == alumno_sel
        ].copy()
        if not df_alumno_inter.empty:
            st.markdown("---")
            st.subheader("🖱️ Trazabilidad del Estudiante")
            col_tr1, col_tr2 = st.columns(2)

            with col_tr1:
                df_sec = (
                    df_alumno_inter.groupby(["nombre_materia", "seccion"])
                    .size()
                    .reset_index(name="cantidad")
                )
                fig_sec = px.bar(
                    df_sec,
                    x="seccion",
                    y="cantidad",
                    color="nombre_materia",
                    barmode="group",
                    labels={
                        "seccion": "Sección del Campus",
                        "cantidad": "Interacciones",
                        "nombre_materia": "Materia",
                    },
                    title="Actividad por Sección del Aula",
                )
                st.plotly_chart(fig_sec, use_container_width=True)

            with col_tr2:
                df_alumno_inter["fecha_hora"] = pd.to_datetime(
                    df_alumno_inter["fecha_hora"], errors="coerce"
                )
                df_alumno_inter["semana"] = (
                    df_alumno_inter["fecha_hora"]
                    .dt.to_period("W-SUN")
                    .dt.start_time
                )
                df_sem = (
                    df_alumno_inter.groupby(["semana", "nombre_materia"])
                    .size()
                    .reset_index(name="cantidad")
                )
                fig_sem = px.line(
                    df_sem,
                    x="semana",
                    y="cantidad",
                    color="nombre_materia",
                    markers=True,
                    labels={
                        "semana": "Semana (lunes)",
                        "cantidad": "Interacciones",
                        "nombre_materia": "Materia",
                    },
                    title="Evolución Semanal de Actividad en el Campus",
                )
                fig_sem.update_xaxes(tickformat="%d/%m")
                fig_sem.update_yaxes(rangemode="tozero")
                st.plotly_chart(fig_sem, use_container_width=True)

    # --- TABLA RESUMEN DEL ALUMNO ---
    st.markdown("---")
    st.subheader("📋 Resumen Consolidado del Estudiante")
    st.dataframe(df_alumno_cond, use_container_width=True, hide_index=True)