"""Dashboard 1: General.

QUÉ CONTESTA
    ¿Cómo viene cada materia a una fecha? De un vistazo:
      - cuántos alumnos tiene y qué porcentaje está activo;
      - cómo les va en los exámenes que rindieron;
      - si la participación sube o baja semana a semana.

CÓMO ESTÁ ARMADO
    El cálculo de quién está activo a la fecha de corte está en corte.py, que
    comparten todos los dashboards. Acá:
      datos_del_corte()            deja alumnos, notas y clics de la población elegida
      resumen_por_materia()        una fila por materia con todos los indicadores
      tendencia_semanal()          alumnos con actividad y clics de cada semana
      render_dashboard_general()   dibuja la pantalla

SOBRE LAS NOTAS
    Se muestra la nota de cada examen pasada a porcentaje (nota sobre máximo),
    para poder comparar materias que califican en escalas distintas. No es la
    condición final: eso lo calcula el evaluador de condiciones (dashboard 4).
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from corte import (
    COLORES_ACTIVIDAD,
    cargar_tablas,
    color_por_materia,
    filtros_corte,
    limite_del_corte,
    situacion_alumnos,
)

# Las dos poblaciones que se pueden mirar. En estos datos el aula tiene casi el
# doble de alumnos que el padrón, así que el resultado cambia según cuál se elija.
POBLACIONES = ["Inscriptos vigentes", "Todos los alumnos del aula"]


def datos_del_corte(tablas, situacion, fecha_corte, poblacion, materia_sel):
    """Devuelve (alumnos, notas, clics) de la población y la materia elegidas."""
    if poblacion == "Inscriptos vigentes":
        situacion = situacion[situacion["inscripcion"] == "Inscripto"]
    if materia_sel != "Todas":
        situacion = situacion[situacion["nombre_materia"] == materia_sel]

    # Los pares alumno y materia que quedaron: con ellos se filtran notas y clics.
    pares = situacion[["id_alumno", "materia"]]
    notas = tablas["calificaciones"].merge(pares, on=["id_alumno", "materia"])
    clics = tablas["interacciones"]
    clics = clics[clics["fecha_hora"] < limite_del_corte(fecha_corte)].merge(pares, on=["id_alumno", "materia"])
    return situacion, notas, clics


def resumen_por_materia(situacion, notas):
    """Una fila por materia: alumnos, actividad y notas."""
    actividad = pd.crosstab(situacion["nombre_materia"], situacion["actividad"])
    actividad = actividad.reindex(columns=list(COLORES_ACTIVIDAD), fill_value=0)

    resumen = pd.DataFrame({
        "Alumnos": situacion.groupby("nombre_materia").size(),
        "Activos": actividad["Activo"],
        "Inactivos": actividad["Inactivo"],
        "Nunca ingresaron": actividad["Nunca ingresó"],
        "Interacciones por alumno": situacion.groupby("nombre_materia")["interacciones"].mean().round(0),
        "Nota promedio (%)": notas.groupby("nombre_materia")["nota_pct"].mean().round(1),
        "Exámenes tomados": notas.groupby("nombre_materia")["instrumento"].nunique(),
        "Alumnos con nota": notas.groupby("nombre_materia")["id_alumno"].nunique(),
    })
    resumen["% activos"] = (resumen["Activos"] / resumen["Alumnos"] * 100).round(0)
    # Una materia sin notas queda con cero exámenes, no con un vacío.
    for columna in ("Exámenes tomados", "Alumnos con nota"):
        resumen[columna] = resumen[columna].fillna(0).astype(int)
    orden = ["Alumnos", "Activos", "% activos", "Inactivos", "Nunca ingresaron", "Interacciones por alumno",
             "Nota promedio (%)", "Exámenes tomados", "Alumnos con nota"]
    return resumen[orden].rename_axis("Materia").reset_index()


def tendencia_semanal(clics):
    """Por semana y materia: alumnos distintos que entraron y cantidad de clics."""
    # Cada clic se lleva al lunes de su semana: 2025-08-07 (jueves) -> 2025-08-04.
    semana = clics["fecha_hora"].dt.to_period("W-SUN").dt.start_time
    return (
        clics.assign(semana=semana)
        .groupby(["semana", "nombre_materia"])
        .agg(alumnos=("id_alumno", "nunique"), interacciones=("id_alumno", "size"))
        .reset_index()
    )


def render_dashboard_general():
    """Dibuja el Dashboard 1: General en Streamlit."""
    st.title("🏠 Dashboard 1: General")
    st.markdown(
        "Resumen de cada materia a la fecha elegida: alumnos activos e inactivos, "
        "rendimiento en los exámenes y tendencia de la participación."
    )

    tablas = cargar_tablas()
    materia_sel, fecha_corte, dias = filtros_corte(tablas)
    poblacion = st.sidebar.radio("Población", POBLACIONES, key="filtro_poblacion")

    # --- CÁLCULO ---
    situacion = situacion_alumnos(tablas, fecha_corte, dias)
    situacion, notas, clics = datos_del_corte(tablas, situacion, fecha_corte, poblacion, materia_sel)
    colores = color_por_materia(tablas)

    st.caption(
        f"Situación al {fecha_corte:%d/%m/%Y} · Población: {poblacion.lower()} · "
        f"Inactivo: sin ingresar en los últimos {dias} días. "
        "Las notas no tienen fecha en el campus, así que se cuentan todas las exportadas."
    )
    if situacion.empty:
        st.warning("No hay alumnos en esa población a esta fecha.")
        return
    resumen = resumen_por_materia(situacion, notas)

    # --- INDICADORES ---
    alumnos = len(situacion)
    activos = int((situacion["actividad"] == "Activo").sum())
    nota_promedio = notas["nota_pct"].mean()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Materias", situacion["nombre_materia"].nunique())
    col2.metric("Alumnos por materia (total)", alumnos)
    col3.metric("Activos", f"{activos} ({round(activos / alumnos * 100)}%)")
    col4.metric("Nota promedio", "sin notas" if pd.isna(nota_promedio) else f"{nota_promedio:.1f}%")
    col5.metric("Interacciones", f"{len(clics):,}".replace(",", "."))

    st.markdown("---")

    # --- RESUMEN POR MATERIA ---
    st.subheader("Resumen por materia")
    st.dataframe(
        resumen, use_container_width=True, hide_index=True,
        column_config={
            "% activos": st.column_config.ProgressColumn(format="%d%%", min_value=0, max_value=100),
            "Nota promedio (%)": st.column_config.NumberColumn(format="%.1f"),
            "Interacciones por alumno": st.column_config.NumberColumn(format="%d"),
        },
    )

    st.markdown("---")

    # --- ACTIVOS E INACTIVOS, Y NOTA PROMEDIO ---
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("Activos e inactivos por materia")
        # De tabla ancha a tabla larga, y se agrega el porcentaje dentro de cada materia.
        barras = resumen.melt(
            id_vars=["Materia", "Alumnos"], value_vars=["Activos", "Inactivos", "Nunca ingresaron"],
            var_name="Estado", value_name="Cantidad",
        )
        barras["Estado"] = barras["Estado"].map(
            {"Activos": "Activo", "Inactivos": "Inactivo", "Nunca ingresaron": "Nunca ingresó"}
        )
        barras["Porcentaje"] = (barras["Cantidad"] / barras["Alumnos"] * 100).round(0)
        barras["Etiqueta"] = barras["Porcentaje"].astype(int).astype(str) + "%"
        fig = px.bar(
            barras, x="Materia", y="Porcentaje", color="Estado", text="Etiqueta",
            color_discrete_map=COLORES_ACTIVIDAD, hover_data=["Cantidad"],
            labels={"Porcentaje": "% de los alumnos"},
        )
        fig.update_layout(legend=dict(orientation="h", y=-0.35, title=None), xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

    with col_der:
        st.subheader("Rendimiento promedio por materia")
        if notas.empty:
            st.info("No hay notas para esta selección.")
        else:
            fig = px.bar(
                resumen, x="Materia", y="Nota promedio (%)", color="Materia", text="Nota promedio (%)",
                color_discrete_map=colores, range_y=[0, 100],
            )
            fig.update_layout(showlegend=False, xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

    # --- DISTRIBUCIÓN DE NOTAS ---
    st.subheader("Distribución de notas")
    if notas.empty:
        st.info("No hay notas para esta selección.")
    else:
        fig = px.histogram(
            notas, x="nota_pct", color="nombre_materia", nbins=20, barmode="group",
            color_discrete_map=colores,
            labels={"nota_pct": "Nota del examen (% del máximo)", "nombre_materia": "Materia"},
        )
        fig.update_layout(legend=dict(orientation="h", y=-0.3, title=None), yaxis_title="Notas")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Cada nota es un examen rendido por un alumno, pasada a porcentaje de su máximo. "
            "Quien no rindió un examen no figura: el promedio es sobre lo rendido."
        )

    st.markdown("---")

    # --- TENDENCIA DE PARTICIPACIÓN ---
    st.subheader("Tendencia de participación")
    if clics.empty:
        st.info("No hay actividad hasta esta fecha.")
    else:
        medida = st.radio(
            "Medida", ["Alumnos con actividad en la semana", "Interacciones en la semana"],
            horizontal=True, label_visibility="collapsed",
        )
        columna = "alumnos" if medida.startswith("Alumnos") else "interacciones"
        fig = px.line(
            tendencia_semanal(clics), x="semana", y=columna, color="nombre_materia", markers=True,
            color_discrete_map=colores,
            labels={"semana": "Semana (lunes)", columna: medida, "nombre_materia": "Materia"},
        )
        fig.update_layout(legend=dict(orientation="h", y=-0.3, title=None))
        fig.update_xaxes(tickformat="%d/%m")  # fechas como día/mes, no en inglés
        fig.update_yaxes(rangemode="tozero")   # el eje arranca en cero: no exagera las caídas
        st.plotly_chart(fig, use_container_width=True)
        st.caption("La última semana puede estar incompleta: llega solo hasta la fecha de corte.")
