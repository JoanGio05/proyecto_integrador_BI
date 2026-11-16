"""Filtros de las vistas 2 y 3, reutilizando corte.py sin alterarlo."""
import streamlit as st

from corte import DIAS_INACTIVIDAD, cargar_tablas, filtros_corte, limite_del_corte, situacion_alumnos
from dashboard_general import POBLACIONES, datos_del_corte


def _filtros_exclusivos(tablas):
    """Participación: un corte acumulado o un intervalo, nunca ambos."""
    materias = tablas["materia"]
    inicio = materias["fecha_min"].min().date()
    final = materias["fecha_max"].max().date()
    st.sidebar.header("Filtros")
    materia = st.sidebar.selectbox("Materia", ["Todas"] + sorted(materias["nombre_materia"]), key="filtro_materia")
    modo = st.sidebar.radio(
        "Analizar por", ["Fecha de corte", "Rango de actividad"], key="participacion_modo_temporal",
    )
    es_rango = modo == "Rango de actividad"
    corte_elegido = st.sidebar.date_input(
        "Fecha de corte", value=final, min_value=inicio, max_value=final,
        format="DD/MM/YYYY", key="filtro_fecha_corte", disabled=es_rango,
    )
    rango = st.sidebar.date_input(
        "Rango de actividad", value=(inicio, final), min_value=inicio, max_value=final,
        format="DD/MM/YYYY", key="participacion_rango_actividad", disabled=not es_rango,
    )
    dias = st.sidebar.select_slider(
        "Días sin ingresar para contar como inactivo", options=[7, 14, 21],
        value=DIAS_INACTIVIDAD, key="filtro_dias_inactividad",
    )
    if es_rango:
        if len(rango) != 2:
            desde, hasta, corte = None, None, final
        else:
            desde, hasta = rango
            corte = hasta
    else:
        corte = corte_elegido
        desde, hasta = inicio, corte
    return materia, corte, dias, desde, hasta, es_rango


def _datos_poblacion(tablas, materia, corte, poblacion, dias=DIAS_INACTIVIDAD):
    situacion = situacion_alumnos(tablas, corte, dias)
    alumnos, _, eventos = datos_del_corte(tablas, situacion, corte, poblacion, materia)
    if poblacion == "Todos los alumnos del aula":
        alumnos = alumnos[alumnos["en_aula"]].copy()
        eventos = eventos.merge(alumnos[["id_alumno", "materia"]], on=["id_alumno", "materia"])
    return alumnos, eventos


def preparar_trazabilidad():
    """Un único rango: su cierre determina la población, sin filtros de inactividad."""
    tablas = cargar_tablas()
    materias = tablas["materia"]
    inicio, final = materias["fecha_min"].min().date(), materias["fecha_max"].max().date()
    st.sidebar.header("Filtros")
    materia = st.sidebar.selectbox("Materia", ["Todas"] + sorted(materias["nombre_materia"]), key="filtro_materia")
    rango = st.sidebar.date_input(
        "Rango de actividad", value=(inicio, final), min_value=inicio, max_value=final,
        format="DD/MM/YYYY", key="trazabilidad_rango_actividad",
    )
    poblacion = st.sidebar.radio("Población", POBLACIONES, key="filtro_poblacion")
    if len(rango) != 2:
        st.info("Completá las fechas de inicio y fin del rango.")
        st.stop()
    desde, hasta = rango
    alumnos, eventos = _datos_poblacion(tablas, materia, hasta, poblacion)
    if alumnos.empty:
        st.info("No hay alumnos para esta población al cierre del rango.")
        st.stop()
    return tablas, alumnos, eventos, desde, hasta


def preparar_vista(mostrar_contexto=True, incluir_contexto=False, seleccion_exclusiva=False):
    tablas = cargar_tablas()
    es_rango = False
    if seleccion_exclusiva:
        materia, corte, dias, desde, hasta, es_rango = _filtros_exclusivos(tablas)
    else:
        materia, corte, dias = filtros_corte(tablas)
    poblacion = st.sidebar.radio("Población", POBLACIONES, key="filtro_poblacion")
    if seleccion_exclusiva and es_rango and desde is None:
        st.info("Completá las fechas de inicio y fin del rango.")
        st.stop()
    # La segunda opción del General conserva todo el universo de situación;
    # las vistas nuevas la limitan a las altas del aula conocidas al corte.
    alumnos, eventos = _datos_poblacion(tablas, materia, corte, poblacion, dias)

    if not seleccion_exclusiva:
        inicio = tablas["materia"]["fecha_min"].min().date()
        rango = st.sidebar.date_input(
            "Rango de actividad", value=(inicio, corte), min_value=inicio, max_value=corte,
            format="DD/MM/YYYY", key=f"participacion_rango_{corte.isoformat()}",
        )
        if len(rango) != 2:
            st.info("Completá las fechas de inicio y fin del rango.")
            st.stop()
        desde, hasta = rango
    if mostrar_contexto:
        st.caption(
            f"Corte: {corte:%d/%m/%Y} · Rango: {desde:%d/%m/%Y} a {hasta:%d/%m/%Y} · "
            f"Población: {poblacion.lower()}. Cada alumno se cuenta por materia."
        )
        st.caption(
            f"Regla compartida: activo con hasta {dias} días enteros sin actividad; "
            f"inactivo con más de {dias}. Sin eventos hasta el corte: Nunca ingresó. "
            "El rango de actividad no cambia ese estado al corte."
        )
    if alumnos.empty:
        st.info("No hay alumnos para esta población y fecha de corte.")
        st.stop()
    # Los eventos ya están truncados por datos_del_corte; se conserva el día completo.
    assert eventos.empty or (eventos["fecha_hora"] < limite_del_corte(corte)).all()
    resultado = (tablas, alumnos, eventos, desde, hasta)
    if incluir_contexto:
        return (*resultado, {"fecha_corte": corte, "dias_inactividad": dias, "es_rango": es_rango})
    return resultado


def descargar_csv(label, df, nombre, key):
    st.download_button(label, df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=nombre, mime="text/csv", key=key)
