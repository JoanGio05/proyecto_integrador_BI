"""Dashboard 3: interacciones por tipo, horarios y contenidos consultados."""
from html import escape
from textwrap import shorten, wrap

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from estilo_kpis import aplicar_estilo_kpis, mostrar_kpis
from estilo_graficos import mostrar_grafico
from filtros_participacion import preparar_trazabilidad
from participacion_trazabilidad import (
    CATEGORIAS, COLORES_EVENTOS, clasificar_eventos, filtrar_rango, resumen_horarios, resumir_contenidos,
)
from presentacion_participacion import aplicar_presentacion, banda_contexto, cabecera, encabezado_seccion


NOMBRES_TIPOS = {"clic": "Clics / navegación", "material": "Accesos a materiales", "examen": "Interacciones de examen"}


def _texto_tooltip(valor, ancho=42):
    return "<br>".join(escape(linea) for linea in wrap(str(valor), ancho)) if pd.notna(valor) and str(valor).strip() else "Sin dato"


def _mostrar_evolucion(traza, desde, hasta, categorias, unidad, altura=420):
    base = pd.MultiIndex.from_product([pd.date_range(desde, hasta), categorias], names=["fecha", "categoria"])
    diario = traza.assign(fecha=traza["fecha_hora"].dt.normalize()).groupby(["fecha", "categoria"]).size()
    diario = diario.reindex(base, fill_value=0).rename("interacciones").reset_index()
    if unidad == "Semana":
        diario["fecha"] = diario["fecha"].dt.to_period("W-SUN").dt.start_time
        diario = diario.groupby(["fecha", "categoria"], as_index=False)["interacciones"].sum()
    diario["total"] = diario.groupby("fecha")["interacciones"].transform("sum")
    diario["tipo"] = diario["categoria"].map(NOMBRES_TIPOS)
    fig = px.line(
        diario, x="fecha", y="interacciones", color="tipo", markers=unidad == "Semana",
        color_discrete_map={NOMBRES_TIPOS[tipo]: color for tipo, color in COLORES_EVENTOS.items()},
        category_orders={"tipo": [NOMBRES_TIPOS[tipo] for tipo in categorias]},
        custom_data=["total"],
        labels={"fecha": "Fecha", "interacciones": "Interacciones", "tipo": "Tipo"},
    )
    fig.update_xaxes(title_text=None, tickformat="%d/%m", hoverformat="%d/%m/%Y")
    fig.update_traces(hovertemplate="%{fullData.name}: <b>%{y:,.0f}</b> interacciones<extra></extra>")
    # Una entrada de hover sin curva propia conserva el total separado del desglose.
    primera = fig.data[0]
    fig.add_trace(go.Scatter(
        x=primera.x, y=primera.y, customdata=primera.customdata,
        mode="none", name="Total", showlegend=False,
        hovertemplate="<b>Total: %{customdata[0]:,.0f} interacciones</b><extra></extra>",
    ))
    fig.data = (fig.data[-1], *fig.data[:-1])
    mostrar_grafico(fig, altura=altura, destacar_eje_y=True, tipografia_clara=True)


def _mostrar_contenidos(contenidos):
    encabezado_seccion("Contenidos con más interacciones", "Materiales y evaluaciones con mayor actividad registrada del alumno.", etiqueta="Top 5")
    grafico = contenidos.head(5).copy()
    grafico["fila"] = [str(i) for i in range(len(grafico))]
    etiquetas = []
    for _, fila in grafico.iterrows():
        titulo = "<br>".join(escape(linea) for linea in wrap(shorten(fila["Contenido"], width=72, placeholder="…"), 40))
        contexto = " · ".join(str(fila[campo]) for campo in ["Materia", "Unidad"] if fila[campo])
        etiquetas.append(titulo + "<br>" + escape(shorten(contexto, width=62, placeholder="…")))
    grafico["ultima"] = grafico["Última interacción"].dt.strftime("%d/%m/%Y %H:%M")
    for campo in ["Contenido", "Unidad", "Materia"]:
        grafico[f"tooltip_{campo}"] = grafico[campo].map(_texto_tooltip)
    fig = px.bar(
        grafico, x="Interacciones", y="fila", orientation="h", color="Tipo", text="Interacciones",
        color_discrete_map={NOMBRES_TIPOS[tipo]: color for tipo, color in COLORES_EVENTOS.items()},
        custom_data=["tooltip_Contenido", "tooltip_Unidad", "tooltip_Materia", "Tipo", "ultima"],
        labels={"Interacciones": "Interacciones", "fila": "Contenido", "Tipo": "Tipo"},
    )
    fig.update_traces(
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[3]}"
                      "<br><br><b>%{x:d} interacciones</b>"
                      "<br>Última interacción: %{customdata[4]}"
                      "<br><br><b>Materia</b><br>%{customdata[2]}"
                      "<br><br><b>Unidad</b><br>%{customdata[1]}<extra></extra>",
    )
    fig.update_yaxes(title_text=None, tickmode="array", tickvals=grafico["fila"].tolist(), ticktext=etiquetas,
                     categoryorder="array", categoryarray=grafico["fila"].tolist(), autorange="reversed")
    maximo = int(grafico["Interacciones"].max())
    fig.update_xaxes(tickmode="linear", dtick=max(1, (maximo + 4) // 5), range=[0, maximo + max(1, maximo * 0.2)])
    mostrar_grafico(fig, altura=max(340, 140 + 58 * len(grafico)), horizontal=True, tipografia_clara=True)
    cantidad_materiales = int(contenidos["Tipo"].eq(NOMBRES_TIPOS["material"]).sum())
    cantidad_evaluaciones = int(contenidos["Tipo"].eq(NOMBRES_TIPOS["examen"]).sum())
    concentracion = grafico["Interacciones"].sum() / contenidos["Interacciones"].sum() * 100
    st.caption(f"Consultó {len(contenidos)} contenidos identificados: {cantidad_materiales} materiales y {cantidad_evaluaciones} evaluaciones.")
    st.caption(f"Estos {len(grafico)} contenidos concentran el {concentracion:.1f}% de sus interacciones con contenidos identificados. El ranking muestra recurrencia de consultas; no mide comprensión ni dificultad.")


def render_dashboard_trazabilidad():
    aplicar_estilo_kpis()
    aplicar_presentacion()
    cabecera("Trazabilidad", "Qué hacen los alumnos, cuándo participan y qué contenidos consultan.")
    _, alumnos, eventos, desde, hasta = preparar_trazabilidad()
    banda_contexto(f"{desde:%d/%m/%Y} · {hasta:%d/%m/%Y}")
    categorias = st.sidebar.multiselect(
        "Tipos de interacción", CATEGORIAS, default=CATEGORIAS,
        format_func=NOMBRES_TIPOS.get, key="trazabilidad_tipos",
    )
    traza = clasificar_eventos(filtrar_rango(eventos, desde, hasta))
    traza = traza[traza["categoria"].isin(categorias)].copy()
    sin_equivalencia = int(traza["evento_sin_equivalencia"].sum())
    conteos = traza["categoria"].value_counts().reindex(CATEGORIAS, fill_value=0)
    mostrar_kpis([
        ("Interacciones en el período", len(traza)),
        ("Clics / navegación", int(conteos["clic"])),
        ("Accesos a materiales", int(conteos["material"])),
        ("Interacciones de examen", int(conteos["examen"])),
    ], key="kpis_trazabilidad", ayudas={
        "Interacciones en el período": "**Qué cuenta**\n\nSuma de las acciones de navegación, accesos a materiales e interacciones de examen registradas en el período, según los filtros seleccionados.\n\n**Cómo interpretarlo**\n\nUn mismo alumno puede generar varias interacciones durante una sesión. Cada acción registrada suma al total.",
        "Clics / navegación": "**Qué cuenta**\n\nAcciones de navegación, comunicación y administración del aula.\n\nLos materiales y los exámenes se cuentan en sus propias categorías.",
        "Accesos a materiales": "**Qué cuenta**\n\nVistas y descargas de contenidos.\n\n**Cómo interpretarlo**\n\nSon accesos registrados; no acreditan lectura efectiva.",
        "Interacciones de examen": "**Qué cuenta**\n\nAccesos, vistas y acciones sobre evaluaciones.\n\n**Cómo interpretarlo**\n\nLa cantidad de interacciones no equivale a exámenes rendidos.",
    })
    if sin_equivalencia:
        st.warning(f"Hay {sin_equivalencia} eventos sin clasificación conocida: se cuentan provisionalmente como clics.")
    if traza.empty:
        st.info("No hay interacciones con estos filtros.")

    with st.container(key="trazabilidad_horarios"):
        encabezado_seccion("Mapa de calor semanal", "Días y horarios en los que se concentra la actividad.")
        horarios = resumen_horarios(traza)
        calor = horarios["interacciones"].unstack("hora")
        calor.index = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        fig = px.imshow(
            calor, aspect="auto", color_continuous_scale=[
                [0.0, "#242238"],
                [0.2, "#303b5f"],
                [0.4, "#315e7b"],
                [0.6, "#2f8792"],
                [0.8, "#38b8ba"],
                [1.0, "#8de0cf"],
            ], zmin=0,
            zmax=max(1, int(calor.to_numpy().max())),
            labels={"x": "Hora del día", "y": "Día de la semana", "color": "Interacciones"},
        )
        fig.update_xaxes(tickmode="linear", dtick=1, tickvals=list(range(24)),
                         ticktext=[f"{hora:02d}" for hora in range(24)])
        fig.update_yaxes(title_text=None)
        fig.update_traces(
            customdata=horarios[["clic", "material", "examen", "alumnos"]].to_numpy().reshape(7, 24, 4),
            hovertemplate="<b>%{y} · %{x:02d}:00–%{x:02d}:59</b>"
                          "<br><br><b>%{z:,d} interacciones</b> en total"
                          "<br><b>%{customdata[3]:,d} alumnos distintos</b>"
                          "<br><br><b>Desglose por tipo</b>"
                          "<br>Clics / navegación: <b>%{customdata[0]:,d}</b>"
                          "<br>Accesos a materiales: <b>%{customdata[1]:,d}</b>"
                          "<br>Interacciones de examen: <b>%{customdata[2]:,d}</b>"
                          "<br><br>Acumulado de las semanas del rango<extra></extra>",
        )
        fig.update_layout(coloraxis_colorbar=dict(title="Interacciones", thickness=12))
        mostrar_grafico(fig, altura=400, calor=True, tipografia_clara=True)

    with st.container(key="trazabilidad_evolucion"):
        titulo, control = st.columns([3, 1], vertical_alignment="center")
        with titulo:
            encabezado_seccion("Evolución de las interacciones", "Cómo cambia la actividad de navegación, materiales y evaluaciones.")
        with control:
            unidad = st.segmented_control(
                "Agrupar interacciones", ["Día", "Semana"], default="Día", required=True,
                label_visibility="collapsed", width="stretch", key="trazabilidad_agrupacion",
            )
        if not traza.empty:
            _mostrar_evolucion(traza, desde, hasta, categorias, unidad)
            if unidad == "Semana":
                st.caption("Semanas de lunes a domingo. La primera y la última incluyen solo los días dentro del rango.")

    nombres = alumnos.sort_values(["apellido", "nombre", "id_alumno"]).drop_duplicates("id_alumno").set_index("id_alumno")[["apellido", "nombre"]].fillna("")
    ids = nombres.index.tolist()
    etiquetas = {identificador: f"{fila.apellido}, {fila.nombre} · {identificador}" for identificador, fila in nombres.iterrows()}
    with st.container(key="trazabilidad_detalle"):
        encabezado_seccion("Análisis por alumno", "Explorá la actividad y los contenidos consultados durante el período.")
        alumno = st.selectbox(
            "Buscar alumno", ids, index=None, placeholder="Elegí por apellido, nombre o ID",
            format_func=lambda valor: etiquetas.get(valor, valor), key="trazabilidad_alumno",
        )
        st.caption("El alumno cambia solo este resumen. Se respetan el rango, la materia y los tipos seleccionados.")
        detalle = traza if alumno is None else traza[traza["id_alumno"] == alumno]
        if alumno is None:
            st.info("Elegí un alumno para ver su actividad y los contenidos que consultó.")
        elif detalle.empty:
            st.info("Este alumno no tiene interacciones en el período con los tipos seleccionados.")
        else:
            conteos_alumno = detalle["categoria"].value_counts().reindex(CATEGORIAS, fill_value=0)
            mostrar_kpis([(NOMBRES_TIPOS[tipo], int(conteos_alumno[tipo])) for tipo in CATEGORIAS],
                         key="kpis_trazabilidad_alumno")
            dias_activos = detalle["fecha_hora"].dt.normalize().nunique()
            ultima = detalle["fecha_hora"].max()
            st.caption(f"{len(detalle):,} interacciones en {dias_activos} días con actividad · Última interacción del período: {ultima:%d/%m/%Y %H:%M}.")
            encabezado_seccion("Actividad del alumno", f"Evolución por tipo · Agrupación por {unidad.lower()}.")
            _mostrar_evolucion(detalle, desde, hasta, categorias, unidad, altura=300)

            contenidos, sin_titulo = resumir_contenidos(detalle)
            contenidos["Tipo"] = contenidos["Tipo"].map(NOMBRES_TIPOS)
            if contenidos.empty:
                encabezado_seccion("Contenidos con más interacciones")
                st.info("No hay materiales o evaluaciones con título identificable en los eventos seleccionados.")
            else:
                _mostrar_contenidos(contenidos)
            if sin_titulo:
                st.caption(f"{sin_titulo} interacciones de materiales o evaluaciones no identifican un título. Se incluyen en los indicadores, pero no en el gráfico de contenidos.")
