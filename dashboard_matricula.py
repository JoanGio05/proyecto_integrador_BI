"""Dashboard 7: Matrícula y alertas.

QUÉ CONTESTA
    ¿Coincide el padrón oficial con lo que pasa en el aula? En concreto:
      - cuántos inscriptos hay y cuántos de ellos están activos;
      - quiénes tienen actividad o notas SIN estar inscriptos;
      - quiénes están inscriptos y nunca entraron, o dejaron de entrar.

CÓMO ESTÁ ARMADO
    1. cargar_tablas()           abre las tablas que deja cargar_datos.py
    2. situacion_matricula()     calcula, para cada alumno y materia, cómo estaba
                                 a una fecha de corte (no usa Streamlit: se puede
                                 probar sola)
    3. render_dashboard_matricula()  dibuja la pantalla

LA FECHA DE CORTE
    Todo se calcula "a una fecha". Se miran solo las inscripciones y los clics
    hasta ese día, así se puede ver cómo estaba la cursada en un momento pasado.
    La excepción son las notas: el campus no informa la fecha de cada examen,
    así que "tiene nota" siempre es a la fecha de exportación.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from cargar_datos import ESTADO_INSCRIPCION_ACTIVA, leer_tabla

# Días sin entrar al aula a partir de los cuales un alumno cuenta como inactivo.
# La cursada es semanal: 14 días equivalen a perderse dos clases seguidas.
DIAS_INACTIVIDAD = 14

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


@st.cache_data
def cargar_tablas():
    """Abre las tablas una sola vez y las deja en memoria (st.cache_data)."""
    tablas = {
        "matricula": leer_tabla("matricula"),
        "participacion": leer_tabla("participacion"),
        "interacciones": leer_tabla("interacciones"),
        "calificaciones": leer_tabla("calificaciones"),
        "alumno": leer_tabla("alumno"),
        "materia": leer_tabla("materia"),
    }
    # Los CSV traen las fechas como texto: se pasan a fecha para poder compararlas.
    tablas["matricula"]["fecha_inscripcion"] = pd.to_datetime(tablas["matricula"]["fecha_inscripcion"])
    tablas["participacion"]["fecha_alta"] = pd.to_datetime(tablas["participacion"]["fecha_alta"])
    tablas["interacciones"]["fecha_hora"] = pd.to_datetime(tablas["interacciones"]["fecha_hora"])
    for col in ("fecha_min", "fecha_max"):
        tablas["materia"][col] = pd.to_datetime(tablas["materia"][col])
    return tablas


def situacion_matricula(tablas, fecha_corte, dias_inactividad=DIAS_INACTIVIDAD):
    """Devuelve una fila por alumno y materia con su situación a la fecha de corte.

    Ejemplo de una fila:
        ALU_1001 | algebra | Inscripto | Activo | Inscripto activo | 3 días sin entrar
    """
    # El corte incluye el día entero: "24/10" quiere decir hasta las 23:59 del 24/10.
    limite = pd.Timestamp(fecha_corte).normalize() + pd.Timedelta(days=1)
    clave = ["id_alumno", "materia"]

    # --- 1. Quiénes estaban en el aula a esa fecha (alta anterior al corte).
    partic = tablas["participacion"]
    en_aula = partic.loc[partic["fecha_alta"] < limite, clave].drop_duplicates()
    en_aula["en_aula"] = True

    # --- 2. Cómo estaba la inscripción de cada uno a esa fecha: de todas las
    # inscripciones anteriores al corte, vale la más reciente.
    matric = tablas["matricula"]
    matric = matric[matric["fecha_inscripcion"] < limite].sort_values("fecha_inscripcion")
    ultima = matric.drop_duplicates(clave, keep="last")
    inscripcion = ultima[clave + ["estado_inscripcion", "fecha_inscripcion", "comision"]].copy()
    inscripcion["inscripcion"] = inscripcion.pop("estado_inscripcion").map(
        lambda estado: "Inscripto" if estado == ESTADO_INSCRIPCION_ACTIVA else "Baja"
    )

    # --- 3. Actividad hasta esa fecha: cantidad de clics y último ingreso.
    traza = tablas["interacciones"]
    traza = traza[traza["fecha_hora"] < limite]
    actividad = traza.groupby(clave)["fecha_hora"].agg(interacciones="size", ultima_actividad="max").reset_index()

    # --- 4. Quiénes tienen al menos una nota (sin fecha: ver el comentario de arriba).
    con_nota = tablas["calificaciones"][clave].drop_duplicates()
    con_nota["tiene_nota"] = True

    # --- 5. Se junta todo. how="outer" conserva a quien figura en una sola fuente:
    # el que está en el aula sin inscripción, y el inscripto que no está en el aula.
    df = en_aula.merge(inscripcion, on=clave, how="outer")
    df = df.merge(actividad, on=clave, how="left").merge(con_nota, on=clave, how="left")
    df["en_aula"] = df["en_aula"].eq(True)
    df["tiene_nota"] = df["tiene_nota"].eq(True)
    df["inscripcion"] = df["inscripcion"].fillna("Sin inscripción")
    df["interacciones"] = df["interacciones"].fillna(0).astype(int)

    # --- 6. Estado de actividad: activo, inactivo o nunca ingresó.
    df["dias_sin_actividad"] = (limite - df["ultima_actividad"]).dt.days
    df["actividad"] = "Nunca ingresó"
    df.loc[df["interacciones"] > 0, "actividad"] = "Inactivo"
    df.loc[df["dias_sin_actividad"] <= dias_inactividad, "actividad"] = "Activo"

    # --- 7. La situación combina inscripción y actividad.
    inscripto = df["inscripcion"] == "Inscripto"
    con_actividad = df["interacciones"] > 0
    df["situacion"] = "En el aula, sin inscripción ni actividad"
    df.loc[~inscripto & con_actividad, "situacion"] = "Con actividad sin inscripción"
    df.loc[inscripto & (df["actividad"] == "Nunca ingresó"), "situacion"] = "Inscripto sin actividad"
    df.loc[inscripto & (df["actividad"] == "Inactivo"), "situacion"] = "Inscripto inactivo"
    df.loc[inscripto & (df["actividad"] == "Activo"), "situacion"] = "Inscripto activo"

    # --- 8. Las alertas, cada una en su columna de sí o no.
    df["alerta_actividad_sin_inscripcion"] = ~inscripto & con_actividad
    df["alerta_nota_sin_inscripcion"] = ~inscripto & df["tiene_nota"]
    df["alerta_inscripto_sin_actividad"] = inscripto & ~con_actividad
    df["alerta_inscripto_inactivo"] = inscripto & (df["actividad"] == "Inactivo")

    # --- 9. Nombre del alumno y de la materia, para mostrar.
    df = df.merge(tablas["alumno"][["id_alumno", "apellido", "nombre"]], on="id_alumno", how="left")
    df = df.merge(tablas["materia"][["materia", "nombre_materia"]], on="materia", how="left")
    return df.sort_values(["nombre_materia", "apellido", "nombre"]).reset_index(drop=True)


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
    materias = tablas["materia"]

    # --- FILTROS (barra lateral) ---
    st.sidebar.header("Filtros - Matrícula")
    materia_sel = st.sidebar.selectbox("Materia", ["Todas"] + sorted(materias["nombre_materia"]))

    # La fecha de corte se mueve entre el primer y el último día con actividad.
    primer_dia, ultimo_dia = materias["fecha_min"].min().date(), materias["fecha_max"].max().date()
    fecha_corte = st.sidebar.date_input(
        "Fecha de corte", value=ultimo_dia, min_value=primer_dia, max_value=ultimo_dia, format="DD/MM/YYYY"
    )
    dias = st.sidebar.select_slider(
        "Días sin ingresar para contar como inactivo", options=[7, 14, 21], value=DIAS_INACTIVIDAD
    )

    # --- CÁLCULO ---
    situacion = situacion_matricula(tablas, fecha_corte, dias)
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
