"""Estilo común de los gráficos de las vistas de Participación y Trazabilidad."""
from html import escape

import streamlit as st


def aplicar_estilo_graficos():
    st.html("""
        <style>
        .bi-titulo-grafico {
            border-top: 1px solid rgba(128, 128, 128, 0.18);
            padding-top: 18px;
            margin: 16px 0 6px;
            font-size: 1.1rem;
            font-weight: 650;
            line-height: 1.4;
            letter-spacing: -0.015em;
        }
        .bi-titulo-grafico::before {
            content: "";
            display: inline-block;
            width: 4px;
            height: 16px;
            border-radius: 2px;
            background: #7b4ea3;
            margin-right: 10px;
            vertical-align: -2px;
        }
        </style>
    """)


def encabezado_grafico(titulo, descripcion):
    st.html(f'<h3 class="bi-titulo-grafico">{escape(titulo)}</h3>')
    st.caption(descripcion)


def mostrar_grafico(fig, altura=350, calor=False, horizontal=False, destacar_eje_y=False, tipografia_clara=False):
    """Mantiene el tema claro/oscuro y unifica espacios, ejes y leyendas."""
    fuente = '"Source Sans", sans-serif' if tipografia_clara else "sans-serif"
    tamano_ejes = 13 if tipografia_clara else 11
    tamano_titulos = 15 if tipografia_clara else 12
    fig.update_layout(
        height=altura,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=fuente, size=14 if tipografia_clara else 12),
        separators=",.",
        hoverlabel=dict(
            align="left", namelength=-1,
            font=dict(family=fuente, size=14),
        ),
        margin=dict(l=12, r=16, t=12, b=64 if not calor else 32),
        legend=dict(
            orientation="h", x=0, xanchor="left", y=-0.18, yanchor="top",
            title_text="", font=dict(family=fuente, size=tamano_ejes, weight=500 if tipografia_clara else 400),
            bgcolor="rgba(0,0,0,0)",
        ),
        bargap=0.25,
    )
    fig.update_xaxes(
        showgrid=horizontal, gridcolor="rgba(128,128,128,0.10)", gridwidth=1,
        zeroline=False, showline=False,
        tickfont=dict(family=fuente, size=tamano_ejes),
        title_font=dict(family=fuente, size=tamano_titulos), automargin=True,
    )
    fig.update_yaxes(
        showgrid=not calor and not horizontal, gridcolor="rgba(128,128,128,0.10)", gridwidth=1,
        zeroline=False, showline=False,
        tickfont=dict(family=fuente, size=tamano_ejes),
        title_font=dict(family=fuente, size=tamano_titulos), automargin=True,
    )
    if destacar_eje_y:
        fig.update_yaxes(title_font=dict(family=fuente, size=14, weight=500 if tipografia_clara else 400), title_standoff=16)
    for traza in fig.data:
        if traza.type == "scatter":
            traza.update(line=dict(width=2.5), marker=dict(size=4))
        elif traza.type in ("bar", "histogram"):
            traza.update(marker_line_width=0, opacity=1 if tipografia_clara else 0.9)
            if tipografia_clara:
                traza.update(textfont=dict(family=fuente, size=14, weight=600))
    if all(traza.type == "scatter" for traza in fig.data):
        fig.update_layout(hovermode="x unified")
    st.plotly_chart(
        fig, width="stretch", theme="streamlit",
        config={
            "displaylogo": False, "scrollZoom": False,
            "modeBarButtonsToRemove": ["toImage", "zoomIn2d", "zoomOut2d", "autoScale2d", "select2d", "lasso2d"],
        },
    )


def etiquetas_materias(fig, nombres):
    """Permite leer los nombres largos en los gráficos de media pantalla."""
    import textwrap

    fig.update_xaxes(
        tickmode="array", tickvals=list(nombres),
        ticktext=["<br>".join(escape(linea) for linea in textwrap.wrap(nombre, 21)) for nombre in nombres],
        tickangle=0,
    )
    return fig
