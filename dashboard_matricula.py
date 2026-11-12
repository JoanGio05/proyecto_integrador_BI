"""Dashboard 7: Matrícula y alertas.

QUÉ CONTESTA
    ¿Coincide el padrón oficial con lo que pasa en el aula? En concreto:
      - cuántos inscriptos hay y cuántos de ellos están activos;
      - quiénes tienen actividad o notas SIN estar inscriptos;
      - quiénes están inscriptos y nunca entraron, o dejaron de entrar.

CÓMO ESTÁ ARMADO
    El cálculo de la situación de cada alumno a la fecha de corte está en
    corte.py, que comparten todos los dashboards. Acá solo se arma la pantalla:
      resumen_por_materia()          totales por materia
      render_dashboard_matricula()   dibuja la pantalla
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from corte import cargar_tablas, filtros_corte, situacion_alumnos

# Las cinco situaciones posibles de un alumno en una materia, en el orden en que
# se muestran. El verde, el amarillo y el rojo quedan reservados para el semáforo
# de condición final, así que acá se usan azules, gris, naranja y violeta.
COLORES_SITUACION = {
    "Inscripto activo": "#1f77b4",
    "Inscripto inactivo": "#7fb3d5",
    "Inscripto sin actividad": "#7f7f7f",
    "Con actividad sin inscripción": "#e67e22",
    "En el aula, sin inscripción ni actividad": "#b39ddb",
}

# Las alertas: nombre de la columna de sí o no, y el texto que se muestra.
ALERTAS = {
    "alerta_actividad_sin_inscripcion": "Con actividad sin inscripción vigente",
    "alerta_nota_sin_inscripcion": "Con nota sin inscripción vigente",
    "alerta_inscripto_sin_actividad": "Inscriptos que nunca ingresaron",
    "alerta_inscripto_inactivo": "Inscriptos que dejaron de ingresar",
}


def resumen_por_materia(situacion):
    """Una fila por materia con los totales que muestran los gráficos y las alertas."""
    inscripto = situacion["inscripcion"] == "Inscripto"
    datos = pd.DataFrame({
        "nombre_materia": situacion["nombre_materia"],
        "En el aula": situacion["en_aula"],
        "Inscriptos vigentes": inscripto,
        "Con actividad": situacion["interacciones"] > 0,
        "Inscriptos activos": inscripto & (situacion["actividad"] == "Activo"),
    })
    for columna, texto in ALERTAS.items():
        datos[texto] = situacion[columna]
    return datos.groupby("nombre_materia").sum().reset_index()


def render_dashboard_matricula():
    """Dibuja el Dashboard 7: Matrícula y alertas en Streamlit."""
    st.title("🚨 Dashboard 7: Matrícula y Alertas")
    st.markdown(
        "Contraste entre el padrón oficial y la actividad real en el aula: inscriptos, "
        "activos, alumnos que cursan sin estar inscriptos e inscriptos sin participación."
    )

    tablas = cargar_tablas()
    materia_sel, fecha_corte, dias = filtros_corte(tablas)

    # --- CÁLCULO ---
    situacion = situacion_alumnos(tablas, fecha_corte, dias)
    if materia_sel != "Todas":
        situacion = situacion[situacion["nombre_materia"] == materia_sel]
    resumen = resumen_por_materia(situacion)

    st.caption(
        f"Situación al {fecha_corte:%d/%m/%Y}. Inactivo: sin ingresar en los últimos {dias} días. "
        "Las notas no tienen fecha en el campus, así que se cuentan todas las exportadas."
    )
    if situacion.empty:
        st.warning("No hay datos de matrícula ni de aula para esa fecha.")
        return

    # --- INDICADORES ---
    inscriptos = int(resumen["Inscriptos vigentes"].sum())
    activos = int(resumen["Inscriptos activos"].sum())
    pct_activos = round(activos / inscriptos * 100) if inscriptos else 0
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Inscriptos vigentes", inscriptos)
    col2.metric("Inscriptos activos", f"{activos} ({pct_activos}%)")
    col3.metric("Con actividad sin inscripción", int(resumen[ALERTAS["alerta_actividad_sin_inscripcion"]].sum()))
    col4.metric("Con nota sin inscripción", int(resumen[ALERTAS["alerta_nota_sin_inscripcion"]].sum()))
    col5.metric("Inscriptos que nunca ingresaron", int(resumen[ALERTAS["alerta_inscripto_sin_actividad"]].sum()))

    st.markdown("---")

    # --- ALERTAS AUTOMÁTICAS POR MATERIA ---
    st.subheader("Alertas automáticas por materia")
    for _, fila in resumen.iterrows():
        partes = [f"**{int(fila[texto])}** {texto.lower()}" for texto in ALERTAS.values() if fila[texto] > 0]
        if partes:
            st.warning(f"**{fila['nombre_materia']}**: " + " · ".join(partes))
        else:
            st.success(f"**{fila['nombre_materia']}**: sin alertas a esta fecha.")

    st.markdown("---")

    # --- GRÁFICOS ---
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("Matriculados contra activos")
        # De tabla ancha (una columna por indicador) a tabla larga (una fila por
        # materia e indicador), que es el formato que pide el gráfico de barras.
        barras = resumen.melt(
            id_vars="nombre_materia",
            value_vars=["En el aula", "Con actividad", "Inscriptos vigentes", "Inscriptos activos"],
            var_name="Indicador", value_name="Alumnos",
        )
        fig = px.bar(
            barras, x="nombre_materia", y="Alumnos", color="Indicador", barmode="group", text="Alumnos",
            labels={"nombre_materia": "Materia"},
            color_discrete_sequence=["#b39ddb", "#e67e22", "#7fb3d5", "#1f77b4"],
        )
        # La leyenda va abajo para que las barras usen todo el ancho.
        fig.update_layout(legend=dict(orientation="h", y=-0.35, title=None), xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

    with col_der:
        st.subheader("Situación de los alumnos del aula")
        conteo = situacion.groupby(["nombre_materia", "situacion"]).size().reset_index(name="Alumnos")
        fig = px.bar(
            conteo, x="nombre_materia", y="Alumnos", color="situacion", text="Alumnos",
            labels={"nombre_materia": "Materia", "situacion": "Situación"},
            color_discrete_map=COLORES_SITUACION,
            category_orders={"situacion": list(COLORES_SITUACION)},
        )
        fig.update_layout(legend=dict(orientation="h", y=-0.35, title=None), xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

    # --- MAPA DE INSCRIPTOS SEGÚN SU PARTICIPACIÓN ---
    st.subheader("Mapa de inscriptos según su participación")
    inscriptos_df = situacion[situacion["inscripcion"] == "Inscripto"]
    if inscriptos_df.empty:
        st.info("No hay inscriptos vigentes a esta fecha.")
    else:
        # Tabla cruzada: una fila por materia, una columna por estado de actividad.
        mapa = pd.crosstab(inscriptos_df["nombre_materia"], inscriptos_df["actividad"])
        mapa = mapa.reindex(columns=["Activo", "Inactivo", "Nunca ingresó"], fill_value=0)
        fig = px.imshow(
            mapa, text_auto=True, aspect="auto", color_continuous_scale="Blues",
            labels={"x": "Estado de actividad", "y": "Materia", "color": "Inscriptos"},
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # --- DETALLE DE ALUMNOS POR ALERTA ---
    st.subheader("Detalle de alumnos por alerta")
    # Se busca la columna de la alerta elegida a partir de su texto.
    texto_sel = st.selectbox("Alerta", list(ALERTAS.values()))
    columna_sel = next(columna for columna, texto in ALERTAS.items() if texto == texto_sel)
    detalle = situacion.loc[situacion[columna_sel], [
        "id_alumno", "apellido", "nombre", "nombre_materia", "inscripcion", "actividad",
        "interacciones", "ultima_actividad", "dias_sin_actividad", "tiene_nota",
    ]].rename(columns={
        "id_alumno": "ID", "apellido": "Apellido", "nombre": "Nombre", "nombre_materia": "Materia",
        "inscripcion": "Inscripción", "actividad": "Actividad", "interacciones": "Interacciones",
        "ultima_actividad": "Última actividad", "dias_sin_actividad": "Días sin ingresar", "tiene_nota": "Tiene nota",
    })
    st.write(f"{len(detalle)} alumnos")
    st.dataframe(
        detalle, use_container_width=True, hide_index=True,
        column_config={"Última actividad": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")},
    )
    st.download_button(
        "Descargar esta lista (CSV)", detalle.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"alerta_{columna_sel}_{fecha_corte:%Y%m%d}.csv", mime="text/csv",
    )
