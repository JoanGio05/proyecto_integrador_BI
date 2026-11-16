"""Presentación compartida de Participación y Trazabilidad."""
from html import escape

import streamlit as st


def aplicar_navegacion():
    st.html("""
        <style>
        [data-testid="stSidebar"] h1 {
            font-size: 1.2rem;
            line-height: 1.35;
            font-weight: 650;
            letter-spacing: -0.025em;
            padding-bottom: 0.35rem;
        }
        [data-testid="stSidebar"] h2 {
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            opacity: 0.7;
            padding-top: 1.25rem;
        }
        .st-key-navegacion_vistas [role="radiogroup"] {
            gap: 3px;
            width: 100%;
        }
        .st-key-navegacion_vistas [role="radiogroup"] > div {
            width: 100%;
        }
        .st-key-navegacion_vistas [data-testid="stRadioOption"] {
            width: 100%;
            box-sizing: border-box;
            padding: 6px 12px;
            border: 1px solid transparent;
            border-radius: 9px;
        }
        .st-key-navegacion_vistas [data-testid="stRadioOption"] > div > div:first-child {
            display: none;
        }
        .st-key-navegacion_vistas [data-testid="stRadioOption"][data-selected="true"] {
            background: rgba(123, 78, 163, 0.14);
            border-color: rgba(123, 78, 163, 0.35);
        }
        .st-key-navegacion_vistas [data-testid="stRadioOption"][data-selected="true"] p {
            font-weight: 600;
        }
        .st-key-navegacion_vistas [data-testid="stRadioOption"][data-focus-visible="true"] {
            outline: 2px solid #7b4ea3;
            outline-offset: 2px;
        }
        </style>
    """)


def aplicar_presentacion():
    st.html("""
        <style>
        [data-testid="stMainBlockContainer"] {
            max-width: 1440px;
            padding: 3.75rem 2rem 3rem;
        }
        .bi-contexto {
            display: flex;
            flex-wrap: wrap;
            gap: 8px 22px;
            align-items: center;
            padding: 14px 0 18px;
            margin-bottom: 8px;
        }
        .bi-contexto-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 0.875rem;
            line-height: 1.4;
        }
        .bi-contexto-item span {
            font-size: 0.65rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            opacity: 0.65;
        }
        .bi-contexto-item strong {
            font-weight: 550;
        }
        .bi-contexto-item + .bi-contexto-item {
            border-left: 1px solid rgba(128, 128, 128, 0.22);
            padding-left: 22px;
        }
        .participacion-cabecera {
            padding: 0 0 2px;
        }
        .participacion-cabecera .antetitulo::before {
            content: "";
            display: inline-block;
            width: 20px;
            height: 2px;
            background: #7b4ea3;
            vertical-align: middle;
            margin-right: 9px;
        }
        .participacion-cabecera .antetitulo {
            font-size: 0.6875rem;
            font-weight: 600;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            opacity: 0.75;
            margin: 0 0 10px;
        }
        .participacion-cabecera h1 {
            font-size: clamp(2rem, 3vw, 2.6rem);
            line-height: 1.15;
            font-weight: 650;
            letter-spacing: -0.045em;
            padding: 0;
            margin: 0 0 10px;
        }
        .participacion-cabecera .bajada {
            font-size: 0.9375rem;
            line-height: 1.6;
            opacity: 0.75;
            margin: 0;
        }
        .st-key-participacion_evolucion, .st-key-participacion_actividad, .st-key-participacion_detalle,
        .st-key-trazabilidad_horarios, .st-key-trazabilidad_evolucion, .st-key-trazabilidad_detalle {
            border: 1px solid rgba(128, 128, 128, 0.17);
            border-radius: 16px;
            background: rgba(128, 128, 128, 0.025);
            padding: 22px 22px 12px;
            margin-top: 16px;
        }
        .participacion-seccion h2 {
            font-size: clamp(1.25rem, 1.8vw, 1.375rem);
            font-weight: 650;
            letter-spacing: -0.025em;
            line-height: 1.4;
            margin: 0;
            padding: 0;
        }
        .participacion-seccion p {
            font-size: 0.875rem;
            line-height: 1.5;
            opacity: 0.72;
            margin: 6px 0 0;
        }
        .bi-seccion-titulo {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        .bi-etiqueta {
            display: inline-block;
            padding: 3px 8px;
            border: 1px solid rgba(123, 78, 163, 0.32);
            border-radius: 6px;
            background: rgba(123, 78, 163, 0.10);
            font-size: 0.6875rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            line-height: 1.5;
        }
        [data-testid="stCaptionContainer"] p {
            font-size: 0.8125rem;
            line-height: 1.55;
        }
        .st-key-participacion_detalle [data-testid="stDownloadButton"] button {
            font-size: 0.875rem;
            min-height: 2.4rem;
            border-radius: 9px;
        }
        .st-key-participacion_evolucion .js-plotly-plot text,
        .st-key-participacion_actividad .js-plotly-plot text,
        .st-key-trazabilidad_horarios .js-plotly-plot text,
        .st-key-trazabilidad_evolucion .js-plotly-plot text,
        .st-key-trazabilidad_detalle .js-plotly-plot text {
            text-rendering: geometricPrecision;
        }
        .js-plotly-plot .hoverlayer .hovertext {
            filter: drop-shadow(0 4px 10px rgba(0, 0, 0, 0.18));
        }
        .js-plotly-plot .hoverlayer text,
        .js-plotly-plot .hoverlayer text tspan {
            fill: currentColor !important;
        }
        [role="tooltip"] {
            max-width: min(360px, calc(100vw - 32px));
            padding: 0;
            border: none;
            background: transparent;
            box-shadow: none;
            text-align: left;
        }
        [role="tooltip"] p {
            font-size: 0.9375rem;
            line-height: 1.6;
            color: inherit;
            margin: 0 0 10px;
        }
        [role="tooltip"] p:last-child {
            margin-bottom: 0;
        }
        [role="tooltip"] [data-testid="stTooltipContent"] {
            padding: 14px 16px;
            border-radius: 10px;
            max-width: min(360px, calc(100vw - 32px));
        }
        .st-key-participacion_agrupacion button[role="radio"][aria-checked="true"],
        .st-key-trazabilidad_agrupacion button[role="radio"][aria-checked="true"] {
            background: rgba(123, 78, 163, 0.16);
            border-color: #7b4ea3;
            color: inherit;
            box-shadow: none;
        }
        @media (max-width: 640px) {
            [data-testid="stMainBlockContainer"] {
                padding: 3.5rem 1rem 2rem;
            }
            .bi-contexto { gap: 12px 18px; }
            .bi-contexto-item + .bi-contexto-item { border-left: none; padding-left: 0; }
            .st-key-participacion_evolucion, .st-key-participacion_actividad, .st-key-participacion_detalle,
            .st-key-trazabilidad_horarios, .st-key-trazabilidad_evolucion, .st-key-trazabilidad_detalle {
                padding: 16px 12px 8px;
            }
        }
        </style>
    """)


def cabecera(titulo="Participación", descripcion="Sesiones, avance y continuidad de la actividad en el campus."):
    st.html(f"""
        <header class="participacion-cabecera">
            <p class="antetitulo">Seguimiento académico</p>
            <h1>{escape(titulo)}</h1>
            <p class="bajada">{escape(descripcion)}</p>
        </header>
    """)


def banda_contexto(periodo, tipo="Período"):
    materia = st.session_state.get("filtro_materia", "Todas")
    materia = "Todas las materias" if materia == "Todas" else materia
    poblacion = st.session_state.get("filtro_poblacion", "Inscriptos vigentes")
    items = [(tipo, periodo), ("Materia", materia), ("Población", poblacion)]
    contenido = "".join(
        f'<div class="bi-contexto-item"><span>{escape(etiqueta)}</span><strong>{escape(valor)}</strong></div>'
        for etiqueta, valor in items
    )
    st.html(f'<div class="bi-contexto">{contenido}</div>')


def encabezado_seccion(titulo, descripcion=None, etiqueta=None):
    descripcion_html = f"<p>{escape(descripcion)}</p>" if descripcion else ""
    etiqueta_html = f'<span class="bi-etiqueta">{escape(etiqueta)}</span>' if etiqueta else ""
    st.html(f'<div class="participacion-seccion"><div class="bi-seccion-titulo"><h2>{escape(titulo)}</h2>{etiqueta_html}</div>{descripcion_html}</div>')
