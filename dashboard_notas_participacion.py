"""Dashboard 5: Notas vs. participación (Nano).

QUÉ PREGUNTA CONTESTA
    ¿Rinden mejor los que más participan? ¿Quiénes están en riesgo, por qué, y
    qué hay que hacer con cada uno?

PARA QUIÉN
    Coordinación y tutores. La pestaña "Lista de intervención" es la lista de
    trabajo de la semana; las otras explican de dónde sale.

INDICADORES (catálogo, sección 5)
    I10 nota normalizada al corte · I11 condición proyectada · I07 inactividad
    I14 correlación participación–nota · I15 grupos de riesgo

ESCALABLE
    No nombra materias ni exámenes: las materias salen de la tabla materia, la
    fecha de cada examen de la trazabilidad y los umbrales de reglas_materias.json.

CÓMO ESTÁ ARMADO
    Los filtros de materia, fecha de corte y días de inactividad son los de
    corte.py, los mismos de los dashboards 1 y 7: lo que se elige en uno queda
    elegido en los otros. La condición es la del evaluador de Joan, la misma
    del dashboard 4. Los cálculos propios están en metricas.py.
"""
import json

import pandas as pd
import plotly.express as px
import streamlit as st

import estilo
import metricas
from corte import firma_datos, cargar_tablas, color_por_materia, filtros_corte
from evaluador_condiciones import cargar_reglas_json


@st.cache_data(show_spinner="Calculando indicadores…")
def _tabla(fecha_corte, dias, variable, minutos, reglas_texto, firma):
    # Va con caché: cambiar de pestaña o de grupo no recalcula las sesiones.
    # reglas_texto y firma entran en la clave: si se edita reglas_materias.json o se
    # vuelven a cargar los datos (una materia nueva), se recalcula solo.
    return metricas.tabla_alumnos(cargar_tablas(), json.loads(reglas_texto), fecha_corte, dias, variable, minutos)


def render_dashboard_notas_participacion():
    """Dibuja el Dashboard 5: Notas vs. participación en Streamlit."""
    st.title("Dashboard 5: Notas vs. Participación")
    st.markdown(
        "¿Rinden mejor los que más participan? ¿Quiénes están en riesgo y qué hacer con cada uno? "
        "Cuenta solo a los inscriptos vigentes del padrón a la fecha de corte."
    )

    tablas = cargar_tablas()
    materia_sel, fecha_corte, dias = filtros_corte(tablas)
    colores = color_por_materia(tablas)
    orden_m = list(colores)  # todas las materias, en el orden de la paleta

    with st.sidebar:
        variable = st.selectbox(
            "Variable de participación", list(metricas.VARIABLES_PARTICIPACION),
            format_func=metricas.VARIABLES_PARTICIPACION.get, key="filtro_variable_d5",
            help="Las dos primeras salen de la trazabilidad y respetan la fecha de corte. "
                 "Las otras dos las informa el campus a la fecha de exportación.")
        minutos = st.number_input("Minutos sin eventos que cortan una sesión", 5, 120,
                                  metricas.MINUTOS_SESION, key="filtro_minutos_sesion")

    reglas_texto = json.dumps(cargar_reglas_json("reglas_materias.json"), sort_keys=True)
    tabla = _tabla(fecha_corte, dias, variable, int(minutos), reglas_texto, firma_datos())
    t = tabla if materia_sel == "Todas" else tabla[tabla["nombre_materia"] == materia_sel]
    t = t.copy()
    t["materia_nombre"] = t["nombre_materia"]
    t["grupo_etiqueta"] = t["grupo"].map(estilo.ETIQUETAS_RIESGO).fillna("Sin datos")
    sin_datos = t[t["grupo"] == "sin_datos"]
    t = t[t["grupo"] != "sin_datos"]

    st.caption(
        f"Situación al {fecha_corte:%d/%m/%Y} · {metricas.VARIABLES_PARTICIPACION[variable]} · "
        f"Inactivo: sin ingresar en los últimos {dias} días. A una fecha pasada solo cuentan los "
        "exámenes que ya se habían abierto."
    )
    if len(sin_datos):
        st.warning(f"{len(sin_datos)} inscriptos no se muestran: su materia todavía no tomó "
                   "exámenes a esta fecha, así que no tienen nota.")
    if t.empty:
        st.info(f"Al {fecha_corte:%d/%m/%Y} todavía no hay exámenes tomados en esta selección.")
        return

    # ---------------------------------------------------------------- tarjetas
    n = len(t)
    riesgo = int((t["grupo"] == "riesgo_abandono").sum())
    esfuerzo = int((t["grupo"] == "esfuerzo_sin_resultado").sum())
    inactivos = int(t["inactivo"].sum())
    corr = metricas.correlaciones(t, variable)
    rho_med = corr["rho"].median()
    # El valor va solo y el porcentaje abajo, para que no se corte en pantallas angostas.
    # Se usa una leyenda debajo y no el "delta" de st.metric, que dibuja una flecha
    # de subida que acá no significa nada.
    tarjetas = [
        ("Inscriptos", estilo.fmt_entero(n), "vigentes en el padrón", "I01"),
        ("✖ Riesgo de abandono", riesgo, f"{estilo.fmt_pct(100 * riesgo / n)} del total", "I15"),
        ("▲ Esfuerzo sin resultado", esfuerzo, f"{estilo.fmt_pct(100 * esfuerzo / n)} del total", "I15"),
        ("Inactivos", inactivos, f"{estilo.fmt_pct(100 * inactivos / n)} del total", "I07"),
        ("Correlación ρ", "s/d" if pd.isna(rho_med) else f"{rho_med:.2f}".replace(".", ","),
         "mediana de las materias", "I14"),
    ]
    for col, (etiqueta, valor, leyenda, codigo) in zip(st.columns(5), tarjetas):
        col.metric(etiqueta, valor, help=estilo.ayuda(codigo))
        col.caption(leyenda)

    tab1, tab2, tab3, tab4 = st.tabs(["Cruce", "Grupos de riesgo", "Lista de intervención", "Cómo se calcula"])

    # ---------------------------------------------------------------- cruce
    with tab1:
        st.subheader("Participación contra nota, por materia")
        st.caption("Cada punto es un alumno. La línea vertical es la mediana de participación de la materia; "
                   "la horizontal, el umbral de regular. Los cuatro cuadrantes son los grupos de riesgo.")
        fig = px.scatter(
            t, x=variable, y="nota_normalizada", color="grupo_etiqueta", facet_col="materia_nombre",
            facet_col_wrap=3, category_orders={"materia_nombre": orden_m,
                                               "grupo_etiqueta": [estilo.ETIQUETAS_RIESGO[g] for g in estilo.ORDEN_RIESGO]},
            color_discrete_map={estilo.ETIQUETAS_RIESGO[g]: col for g, col in estilo.COLORES_RIESGO.items()},
            hover_data={"apellido": True, "nombre": True, "id_alumno": True, "condicion": True,
                        "dias_sin_actividad": True, "materia_nombre": False, "grupo_etiqueta": False},
            labels={variable: metricas.VARIABLES_PARTICIPACION[variable].split(" (")[0],
                    "nota_normalizada": "Nota al corte (%)", "grupo_etiqueta": "", "materia_nombre": ""},
            height=90 + 340 * -(-t["materia_nombre"].nunique() // 3),  # 340 px por fila de materias
        )
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        # Con más de 3 materias el gráfico pasa a varias filas, y plotly numera
        # las filas de abajo hacia arriba: se convierte la posición de lectura.
        presentes = [m for m in orden_m if m in set(t["materia_nombre"])]
        filas_fig = -(-len(presentes) // 3)
        for i, m in enumerate(presentes):
            g = t[t["materia_nombre"] == m]
            fila, col = filas_fig - i // 3, i % 3 + 1
            fig.add_vline(x=g[variable].median(), line_dash="dot", line_color=estilo.GRIS_TEXTO, row=fila, col=col)
            fig.add_hline(y=g["umbral_regular_pct"].iloc[0], line_dash="dot", line_color=estilo.GRIS_TEXTO,
                          row=fila, col=col)
        fig.update_yaxes(range=[-3, 103])
        # Unos pocos alumnos con muchísima actividad aplastan al resto contra el eje.
        # Se corta el eje en el percentil 98; los que quedan afuera se avisan abajo.
        tope = t[variable].quantile(0.98)
        fuera = int((t[variable] > tope).sum())
        if tope > 0:
            fig.update_xaxes(range=[-0.03 * tope, tope * 1.05])
        fig.update_layout(legend=dict(y=1.18), margin=dict(t=90))
        st.plotly_chart(fig, width="stretch")
        if fuera:
            st.caption(f"{fuera} alumnos con participación mayor a {tope:.1f} quedan fuera del eje para que "
                       "se lea el resto. Están en la lista de intervención si corresponde.")

        st.subheader("¿Cuánto se relacionan?")
        corr["Materia"] = corr["materia"].map(t.drop_duplicates("materia").set_index("materia")["nombre_materia"])
        corr["Lectura"] = corr["rho"].map(metricas.fuerza)
        corr["ρ de Spearman"] = corr["rho"]
        corr["Significativa"] = corr["p_valor"].map(lambda p: "sí (p < 0,05)" if p < 0.05 else "no")
        st.dataframe(corr[["Materia", "ρ de Spearman", "Lectura", "n", "Significativa"]],
                     hide_index=True, width="stretch")
        st.caption("Spearman y no Pearson: tiempo y nota no son normales y tienen muchos ceros. "
                   "Correlación no implica causa.")

    # ---------------------------------------------------------------- grupos
    with tab2:
        st.subheader("Tamaño de cada grupo por materia")
        g = (t.groupby(["materia_nombre", "grupo_etiqueta"]).size().reset_index(name="alumnos"))
        g["pct"] = 100 * g["alumnos"] / g.groupby("materia_nombre")["alumnos"].transform("sum")
        fig2 = px.bar(
            g, y="materia_nombre", x="pct", color="grupo_etiqueta", orientation="h",
            category_orders={"grupo_etiqueta": [estilo.ETIQUETAS_RIESGO[x] for x in estilo.ORDEN_RIESGO],
                             "materia_nombre": orden_m},
            color_discrete_map={estilo.ETIQUETAS_RIESGO[x]: col for x, col in estilo.COLORES_RIESGO.items()},
            custom_data=["alumnos"],
            labels={"pct": "% de inscriptos vigentes", "materia_nombre": "", "grupo_etiqueta": ""}, height=320)
        fig2.update_traces(hovertemplate="%{y}<br>%{x:.1f} %% · %{customdata[0]} alumnos<extra></extra>")
        st.plotly_chart(fig2, width="stretch")

        resumen = (t.pivot_table(index="materia_nombre", columns="grupo_etiqueta", values="id_alumno",
                                 aggfunc="count", fill_value=0)
                   .reindex(columns=[estilo.ETIQUETAS_RIESGO[x] for x in estilo.ORDEN_RIESGO], fill_value=0)
                   .rename_axis(index="Materia", columns=None))
        st.dataframe(resumen, width="stretch")
        st.markdown("\n".join(f"- **{estilo.ETIQUETAS_RIESGO[x]}**: {metricas.ACCIONES[x]}" for x in estilo.ORDEN_RIESGO))

    # ---------------------------------------------------------------- lista
    with tab3:
        st.subheader("A quién contactar esta semana")
        grupos = st.multiselect(
            "Grupos", estilo.ORDEN_RIESGO, default=["riesgo_abandono", "esfuerzo_sin_resultado"],
            format_func=estilo.ETIQUETAS_RIESGO.get)
        # Primero lo más urgente: riesgo de abandono, después esfuerzo sin resultado...
        prioridad = {g: i for i, g in enumerate(reversed(estilo.ORDEN_RIESGO))}
        lista = (t[t["grupo"].isin(grupos)]
                 .assign(_p=lambda d: d["grupo"].map(prioridad))
                 .sort_values(["_p", "materia", "nota_normalizada"]))
        cols = {"id_alumno": "Legajo", "apellido": "Apellido", "nombre": "Nombre", "materia_nombre": "Materia",
                "comision": "Comisión", "grupo_etiqueta": "Grupo", "nota_normalizada": "Nota al corte (%)",
                "condicion": "Condición proyectada", variable: "Participación", "dias_sin_actividad": "Días sin entrar",
                "motivo": "Motivo", "accion": "Acción sugerida"}
        vista = lista[list(cols)].round({"nota_normalizada": 1, variable: 2}).rename(columns=cols)
        st.dataframe(vista, hide_index=True, width="stretch", height=420)
        st.download_button("Descargar la lista (CSV)", vista.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"intervencion_{fecha_corte:%Y%m%d}.csv", mime="text/csv")

    # ---------------------------------------------------------------- reglas
    with tab4:
        st.markdown(f"""
**Nota al corte (I10).** Es la del evaluador de condiciones, la misma del dashboard 4: lo no rendido vale cero, el
recuperatorio se trata como dice `reglas_materias.json`, y las materias que suman se miden sobre los puntos tomados.
A una fecha de corte pasada solo cuentan los exámenes que ya se habían abierto: la fecha de cada examen es su primera
realización en la trazabilidad, porque el campus no la exporta.

**Condición proyectada (I11).** Los umbrales de `reglas_materias.json`; una materia sin su fila usa la regla por defecto (regular 60 %, promoción 85 % sobre lo tomado). Aprueba quien queda regular o promociona.

**Sesión.** Termina cuando pasan más de {int(minutos)} minutos sin eventos.

**Inactivo (I07).** Más de {dias} días sin eventos al corte, o nunca entró. Es la misma regla de los dashboards 1 y 7.

**Grupos (I15).** Participación alta = por encima de la mediana de su materia. Aprueba = condición regular o
promociona. Un inactivo que no aprueba va siempre a riesgo de abandono.

**Limitaciones.** Avance y tiempo de uso del campus son datos a la fecha de exportación. La correlación no implica
causa. La mediana de participación es relativa: siempre hay una mitad "baja".
""")
