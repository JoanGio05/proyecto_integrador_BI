"""Dashboard 2: sesiones, actividad e indicadores de la foto exportada."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from html import escape
from textwrap import wrap

from corte import COLORES_ACTIVIDAD, color_por_materia
from estilo_kpis import aplicar_estilo_kpis, mostrar_kpis
from estilo_graficos import mostrar_grafico
from filtros_participacion import preparar_vista
from participacion_trazabilidad import calcular_sesiones, filtrar_rango, resumen_participacion, sesiones_en_periodo
from presentacion_participacion import aplicar_presentacion, banda_contexto, cabecera, encabezado_seccion


def render_dashboard_participacion():
    aplicar_estilo_kpis()
    aplicar_presentacion()
    cabecera()
    tablas, alumnos, eventos, desde, hasta, contexto = preparar_vista(
        mostrar_contexto=False, incluir_contexto=True, seleccion_exclusiva=True,
    )
    es_rango = contexto["es_rango"]
    banda_contexto(
        f"{desde:%d/%m/%Y} · {hasta:%d/%m/%Y}" if es_rango else f"{contexto['fecha_corte']:%d/%m/%Y}",
        tipo="Período" if es_rango else "Fecha de corte",
    )
    sesiones = calcular_sesiones(eventos)
    if es_rango:
        sesiones = sesiones_en_periodo(sesiones, desde, hasta)
    eventos_rango = filtrar_rango(eventos, desde, hasta)
    resumen = resumen_participacion(alumnos, sesiones, tablas["participacion"])
    colores = color_por_materia(tablas)

    activos = int(resumen["actividad"].eq("Activo").sum())
    inactivos = int(resumen["actividad"].eq("Inactivo").sum())
    tiempo, avance = resumen["tiempo_uso_min"], resumen["avance_pct"]
    dias = contexto["dias_inactividad"]
    fechas_exportacion = pd.to_datetime(
        tablas["materia"].loc[tablas["materia"]["materia"].isin(resumen["materia"]), "fecha_exportacion"],
        dayfirst=True, errors="coerce",
    )
    reporte_disponible = (
        not es_rango and not fechas_exportacion.empty and fechas_exportacion.notna().all()
        and fechas_exportacion.le(pd.Timestamp(contexto["fecha_corte"])).all()
    )
    titulo_tiempo = "Tiempo estimado (reporte final)"
    titulo_avance = "Avance promedio (reporte final)"
    explicacion_sesiones = (
        "Promedio de sesiones con actividad dentro del rango seleccionado, incluyendo alumnos sin sesiones. "
        if es_rango else
        "Promedio de sesiones iniciadas, incluyendo alumnos sin sesiones. "
    )
    ayudas = {
        "Sesiones promedio por alumno": (
            explicacion_sesiones +
            "Una pausa mayor a 30 minutos inicia otra sesión del mismo alumno."
        ),
        titulo_tiempo: (
            "Suma del tiempo estimado por el campus en horas. "
            "Es el acumulado del reporte final. No hay registros para calcularlo en fechas anteriores ni dentro de un rango."
        ),
        titulo_avance: (
            "Promedio de los porcentajes de avance informados por el campus en el reporte final. "
            "No hay avances históricos ni incrementos por período."
        ),
        "Activos / inactivos": (
            ("Cantidad de activos dividida por la de inactivos al cierre del rango. " if es_rango else
             "Cantidad de activos dividida por la de inactivos. ") +
            f"Activo: hasta {dias} días enteros sin actividad; inactivo: más de {dias}. "
            "Quienes nunca ingresaron no integran el ratio y se muestran aparte en el gráfico."
        ),
    }
    mostrar_kpis([
        ("Sesiones promedio por alumno", f"{resumen['sesiones'].mean():.2f}"),
        (titulo_tiempo, "—" if not reporte_disponible else
            ("sin datos" if tiempo.notna().sum() == 0 else f"{tiempo.sum() / 60:.1f} h")),
        (titulo_avance, "—" if not reporte_disponible else
            ("sin datos" if avance.notna().sum() == 0 else f"{avance.mean():.1f}%")),
        ("Activos / inactivos", "sin inactivos" if not inactivos else f"{activos / inactivos:.2f}"),
    ], key="kpis_participacion", ayudas=ayudas)
    if fechas_exportacion.notna().all() and not fechas_exportacion.empty:
        if fechas_exportacion.nunique() == 1:
            origen = f"la exportación del {fechas_exportacion.iloc[0]:%d/%m/%Y}"
        else:
            origen = f"exportaciones entre el {fechas_exportacion.min():%d/%m/%Y} y el {fechas_exportacion.max():%d/%m/%Y}"
    else:
        origen = "los reportes finales del campus"
    if reporte_disponible:
        st.caption(f"Tiempo y avance: acumulados informados en {origen}, para la población seleccionada.")
    else:
        st.caption(
            f"Tiempo y avance no disponibles para {'rangos de actividad' if es_rango else 'este corte histórico'}. "
            f"Solo se cuenta con los acumulados de {origen}; no se reconstruyen valores históricos. "
            "Las sesiones y los accesos sí se calculan con sus registros fechados."
        )

    with st.container(key="participacion_evolucion"):
        titulo, control = st.columns([3, 1], vertical_alignment="center")
        with titulo:
            descripcion = (f"Accesos registrados del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}." if es_rango else
                           f"Accesos registrados hasta el {hasta:%d/%m/%Y}.")
            encabezado_seccion("Evolución de los accesos", descripcion)
        with control:
            unidad = st.segmented_control(
                "Agrupar accesos", ["Día", "Semana"], default="Día", required=True,
                label_visibility="collapsed", width="stretch", key="participacion_agrupacion",
            )
        if eventos_rango.empty:
            st.info("Sin accesos en el rango elegido. Los alumnos sin sesiones siguen en el denominador.")
        else:
            fechas = pd.date_range(desde, hasta, freq="D")
            nombres = sorted(resumen["nombre_materia"].unique())
            base = pd.MultiIndex.from_product([fechas, nombres], names=["fecha", "nombre_materia"])
            diario = eventos_rango.assign(fecha=eventos_rango["fecha_hora"].dt.normalize()).groupby(
                ["fecha", "nombre_materia"]).size().reindex(base, fill_value=0).rename("interacciones").reset_index()
            if unidad == "Semana":
                diario["fecha"] = diario["fecha"].dt.to_period("W-SUN").dt.start_time
                diario = diario.groupby(["fecha", "nombre_materia"], as_index=False)["interacciones"].sum()
            diario["total"] = diario.groupby("fecha")["interacciones"].transform("sum")
            fig = px.line(diario, x="fecha", y="interacciones", color="nombre_materia", markers=unidad == "Semana",
                color_discrete_map=colores, custom_data=["total"], labels={"fecha": "Fecha", "interacciones": "Accesos / eventos",
                                                   "nombre_materia": "Materia"})
            fig.update_xaxes(title_text=None, tickformat="%d/%m", hoverformat="%d/%m/%Y")
            fig.update_traces(hovertemplate="%{fullData.name}: <b>%{y:,.0f}</b> accesos<extra></extra>")
            primera = fig.data[0]
            fig.add_trace(go.Scatter(
                x=primera.x, y=primera.y, customdata=primera.customdata,
                mode="none", name="Total", showlegend=False,
                hovertemplate="<b>Total: %{customdata[0]:,.0f} accesos</b><extra></extra>",
            ))
            fig.data = (fig.data[-1], *fig.data[:-1])
            mostrar_grafico(fig, altura=420, destacar_eje_y=True, tipografia_clara=True)

    with st.container(key="participacion_actividad"):
        encabezado_seccion(
            "Actividad por materia",
            (f"Estado al cierre del período ({hasta:%d/%m/%Y}) · Activos, inactivos y alumnos que nunca ingresaron."
             if es_rango else "Estado a la fecha de corte · Activos, inactivos y alumnos que nunca ingresaron."),
        )
        estados = pd.crosstab(resumen["nombre_materia"], resumen["actividad"]).reindex(
            columns=list(COLORES_ACTIVIDAD), fill_value=0,
        )
        totales = estados.sum(axis=1)
        orden = (estados["Inactivo"] / totales).sort_values(ascending=False, kind="stable").index.tolist()
        distribucion = estados.rename_axis(columns="actividad").reset_index().melt(
            id_vars="nombre_materia", var_name="actividad", value_name="alumnos",
        )
        distribucion["total"] = distribucion["nombre_materia"].map(totales)
        distribucion["porcentaje"] = distribucion["alumnos"] / distribucion["total"] * 100
        distribucion["etiqueta"] = distribucion["porcentaje"].map(lambda p: f"{p:.1f}%" if p >= 6 else "")
        fig = px.bar(
            distribucion, x="porcentaje", y="nombre_materia", color="actividad", orientation="h",
            barmode="stack", text="etiqueta", color_discrete_map=COLORES_ACTIVIDAD,
            category_orders={"actividad": list(COLORES_ACTIVIDAD)},
            custom_data=["alumnos", "total"],
            labels={"porcentaje": "Alumnos (%)", "nombre_materia": "Materia", "actividad": "Estado"},
        )
        fig.update_traces(
            textposition="inside", insidetextanchor="middle",
            hovertemplate="%{y}<br>%{fullData.name}: %{customdata[0]:.0f} alumnos"
                          "<br>%{x:.1f}% de %{customdata[1]:.0f}<extra></extra>",
        )
        fig.update_xaxes(
            range=[0, 100], tickvals=[0, 25, 50, 75, 100],
            ticktext=["0%", "25%", "50%", "75%", "100%"], title_text=None,
        )
        fig.update_yaxes(
            title_text=None, categoryorder="array", categoryarray=orden[::-1],
            tickmode="array", tickvals=orden,
            ticktext=["<br>".join(escape(linea) for linea in wrap(nombre, 25)) for nombre in orden],
        )
        mostrar_grafico(fig, altura=max(360, 180 + 64 * len(orden)), horizontal=True, tipografia_clara=True)

    columnas = {
        "apellido": "Apellido",
        "nombre": "Nombre",
        "nombre_materia": "Materia",
        "actividad": "Actividad",
        "dias_sin_actividad": "Días sin actividad",
        "sesiones": "Sesiones",
    }
    detalle = resumen[list(columnas)].rename(columns=columnas)
    with st.container(key="participacion_detalle"):
        titulo, accion = st.columns([3, 1], vertical_alignment="center")
        with titulo:
            encabezado_seccion("Detalle de participación")
        with accion:
            st.download_button(
                "Descargar CSV", detalle.to_csv(index=False).encode("utf-8-sig"),
                file_name="participacion_del_corte.csv", mime="text/csv", icon=":material/download:",
                key="descarga_participacion", width="stretch",
            )
        st.dataframe(
            detalle, width="stretch", height=390, row_height=36, hide_index=True,
            column_config={
                "Días sin actividad": st.column_config.NumberColumn(format="%d"),
                "Sesiones": st.column_config.NumberColumn(format="%d"),
            },
        )
