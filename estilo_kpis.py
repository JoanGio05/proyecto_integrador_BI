"""Presentación común de los indicadores de Participación y Trazabilidad."""
import streamlit as st
from numbers import Integral


def mostrar_kpis(indicadores, key, ayudas=None):
    """Filas ordenadas de hasta cuatro tarjetas del mismo ancho."""
    with st.container(key=key):
        for inicio in range(0, len(indicadores), 4):
            fila = indicadores[inicio:inicio + 4]
            columnas = st.columns(len(fila), gap="small")
            for columna, (titulo, valor) in zip(columnas, fila):
                valor_visible = f"{valor:,}".replace(",", ".") if isinstance(valor, Integral) else valor
                columna.metric(titulo, valor_visible, border=True, height=120, help=(ayudas or {}).get(titulo))


def aplicar_estilo_kpis():
    """Da formato de tarjeta a los st.metric de la vista que lo invoca."""
    st.html(
        """
        <style>
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg,
                rgba(123, 78, 163, 0.045), rgba(23, 190, 207, 0.015));
            border: 1px solid rgba(128, 128, 128, 0.20);
            border-top: 2px solid #7b4ea3;
            border-radius: 12px;
            padding: 16px 18px;
            min-height: 112px;
            box-sizing: border-box;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.025);
            display: flex;
            align-items: flex-start;
            justify-content: center;
            text-align: left;
        }

        /* El borde nativo agrega un contenedor con su propio relleno. */
        div[data-testid="stMetric"] > div:first-child {
            padding: 0;
            width: 100%;
        }

        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            min-height: 2.6rem;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            text-align: left;
        }

        div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {
            font-size: 1rem;
            font-weight: 600;
            line-height: 1.3;
            white-space: normal;
            overflow: visible;
            text-align: left;
        }

        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: clamp(1.5rem, 2.4vw, 1.875rem);
            font-weight: 650;
            line-height: 1.2;
            letter-spacing: -0.02em;
            text-align: left;
            font-variant-numeric: tabular-nums;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2)
            [data-testid="stMetric"] {
            border-top-color: #17becf;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3)
            [data-testid="stMetric"] {
            border-top-color: #e67e22;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4)
            [data-testid="stMetric"] {
            border-top-color: #1f77b4;
        }

        .st-key-kpis_trazabilidad [data-testid="stColumn"]:first-child [data-testid="stMetric"] {
            border-top-color: rgba(128, 128, 128, 0.48);
        }
        .st-key-kpis_trazabilidad [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {
            border-top-color: #7b4ea3;
        }
        .st-key-kpis_trazabilidad [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] {
            border-top-color: #17becf;
        }
        .st-key-kpis_trazabilidad [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] {
            border-top-color: #e67e22;
        }

        @media (max-width: 640px) {
            div[data-testid="stMetric"] {
                padding: 12px 14px;
            }
        }
        </style>
        """,
    )
