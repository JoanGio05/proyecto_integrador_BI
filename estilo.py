"""Guía de estilo común de los 7 dashboards (TFI de BI) — Nano.

QUÉ RESUELVE, EN UNA LÍNEA
    Cada materia tiene SIEMPRE el mismo color en los 7 dashboards, sin escribir
    a mano ningún nombre de materia, y el semáforo de condición es igual en todos.

EL PROBLEMA QUE TENÍAMOS
    Plotly pinta las series en el orden en que aparecen en el DataFrame. Si en el
    dashboard 4 filtrás y queda una sola materia, esa materia pasa a ser "la
    primera" y cambia de color. Y una materia nueva desplaza a las demás.

LA REGLA
    1. Las materias de la paleta son 5 colores validados para daltonismo
       (deuteranopía, protanopía, tritanopía) en fondo claro y oscuro.
    2. Ninguno es verde, amarillo ni rojo: esos tres quedan reservados para el
       semáforo (promociona / regular / libre), así un color nunca significa
       dos cosas.
    3. Las materias se ordenan alfabéticamente y cada una toma el casillero de
       su posición. Con hasta 3 materias, los 3 colores se distinguen entre
       todos los pares (también con daltonismo); con 4 o 5, los vecinos.
    4. Siempre se le pasa la lista COMPLETA de materias (la tabla materia del
       modelo), no la filtrada. Así un filtro no repinta las materias que
       quedan, y como los 7 dashboards leen la misma tabla, los 7 coinciden.

    Lo que se resignó: si se agrega una materia que va en el medio del
    alfabeto, las que vienen después cambian de color en la corrida siguiente.
    Se probó asignar por huella del nombre (md5) para evitarlo, pero entonces
    el color depende del azar del nombre y con las 3 materias reales caían
    azul y violeta juntos, que con deuteranopía casi no se distinguen. Se
    eligió que siempre se lean bien antes que el color sea fijo entre corridas.

USO EN UN DASHBOARD
    import estilo
    from corte import cargar_tablas, color_por_materia

    estilo.aplicar_tema()                    # una vez, en app.py

    tablas = cargar_tablas()
    colores = color_por_materia(tablas)      # {"Álgebra": "#...", ...}, lista completa

    fig = px.bar(df, x="nombre_materia", y="valor", color="nombre_materia",
                 color_discrete_map=colores,
                 category_orders={"nombre_materia": list(colores)})

    fig = px.pie(df, names="condicion", color="condicion",
                 color_discrete_map=estilo.COLORES_CONDICION,
                 category_orders={"condicion": estilo.ORDEN_CONDICION})

    st.metric("Promocionan", estilo.fmt_pct(61.3),
              help=estilo.ayuda("I11"))     # la definición sale del catálogo

    corte.color_por_materia() llama a colores_materias() con la tabla materia
    completa: así los 7 dashboards comparten la misma paleta.
"""

import warnings

import plotly.graph_objects as go
import plotly.io as pio

# =============================================================================
# PALETAS
# =============================================================================

# Colores de materia. El ORDEN importa: está elegido para que dos casilleros
# vecinos se distingan aun con daltonismo (validado con ΔE en OKLab).
# Los tres primeros además se distinguen entre todos los pares, que es lo que
# hace falta en un gráfico de dispersión con varias materias.
PALETA_MATERIAS = [
    "#2a78d6",  # azul
    "#d55181",  # magenta
    "#9a6a1f",  # ocre
    "#1b9aaa",  # petróleo
    "#6250d6",  # violeta
]

# Semáforo de condición. Reservado: no se usa para nada más.
COLORES_CONDICION = {
    "promociona": "#0ca30c",  # verde
    "regular": "#fab219",     # amarillo
    "libre": "#d03b3b",       # rojo
}
ORDEN_CONDICION = ["promociona", "regular", "libre"]

# El color solo no alcanza (daltonismo, impresión en blanco y negro):
# el semáforo siempre va con ícono y palabra.
ETIQUETAS_CONDICION = {
    "promociona": "✔ Promociona",
    "regular": "● Regular",
    "libre": "✖ Libre",
}

# Grupos de riesgo del dashboard 5 (notas vs. participación). Usan la misma
# escala de estados que el semáforo, de "bien" a "crítico".
COLORES_RIESGO = {
    "en_camino": "#0ca30c",           # participa y rinde
    "autonomo": "#fab219",            # rinde sin participar mucho
    "esfuerzo_sin_resultado": "#ec835a",  # participa y no rinde
    "riesgo_abandono": "#d03b3b",     # ni participa ni rinde
}
ORDEN_RIESGO = ["en_camino", "autonomo", "esfuerzo_sin_resultado", "riesgo_abandono"]
ETIQUETAS_RIESGO = {
    "en_camino": "✔ En camino",
    "autonomo": "● Autónomo",
    "esfuerzo_sin_resultado": "▲ Esfuerzo sin resultado",
    "riesgo_abandono": "✖ Riesgo de abandono",
}

# Para lo que no es serie: textos, ejes, grilla, "sin dato".
GRIS_TEXTO = "#52514e"
GRIS_GRILLA = "#e6e5e1"
GRIS_SIN_DATO = "#a3a29c"
FUENTE = "Inter, Segoe UI, Helvetica, Arial, sans-serif"


# =============================================================================
# COLOR POR MATERIA
# =============================================================================

def colores_materias(materias, en_orden=False):
    """Devuelve {materia: color} para usar como color_discrete_map.

    materias: cualquier lista o columna con los nombres (pueden venir repetidos).
              Tiene que ser la lista COMPLETA del modelo
              (tablas["materia"]["nombre_materia"]), no la filtrada en el dashboard.

    Ejemplo:
        colores_materias(["Álgebra", "Probabilidad y Estadística"])
        -> {"Probabilidad y Estadística": "#...", "Álgebra": "#..."}
    """
    limpias = [str(m).strip() for m in materias if str(m).strip()]
    # en_orden=True respeta el orden recibido (corte.color_por_materia lo da
    # estable); si no, orden alfabético.
    unicas = list(dict.fromkeys(limpias)) if en_orden else sorted(set(limpias))
    n = len(PALETA_MATERIAS)

    if len(unicas) > n:
        warnings.warn(
            f"Hay {len(unicas)} materias y la paleta tiene {n} colores: algunos "
            "se repiten. Para más materias conviene separar en paneles "
            "(facet_col='materia') en vez de distinguir por color."
        )

    # Posición -> casillero. Pasada la 5ª materia vuelve a empezar.
    return {materia: PALETA_MATERIAS[i % n] for i, materia in enumerate(unicas)}


def orden_materias(materias):
    """Las materias en el mismo orden en que se asignan los colores.

    Va en category_orders={"materia": ...}: así la leyenda y las barras salen
    siempre en el mismo orden en los 7 dashboards.
    """
    return sorted({str(m).strip() for m in materias if str(m).strip()})


def etiquetas_materias(tabla_materia):
    """{clave: nombre lindo} a partir de la tabla materia: 'algebra' -> 'Álgebra'.

    Sirve para labels= de plotly o para los títulos de las tarjetas.
    """
    return dict(zip(tabla_materia["materia"], tabla_materia["nombre_materia"]))


def ayuda(codigo):
    """Texto corto de un indicador del catálogo, para help= de st.metric.

    Así el que mira el tablero pasa el mouse por el ícono (?) y ve qué mide el
    número y cómo se calcula, igual en todos los dashboards.
    """
    return INDICADORES.get(codigo, "")


# Una línea por indicador del catálogo (sección 5 del informe).
INDICADORES = {
    "I01": "Inscriptos vigentes: alumnos del padrón cuya última inscripción está aceptada.",
    "I02": "Tasa de baja: alumnos cuya última inscripción es una baja, sobre los inscriptos.",
    "I03": "Alumnos del aula fuera del padrón: usuarios con perfil Alumnos sin inscripción vigente.",
    "I04": "Tasa de acceso: inscriptos vigentes con al menos un evento hasta la fecha de corte.",
    "I05": "Avance mediano: la mitad de los inscriptos recorrió más que esto. Dato a la fecha de exportación.",
    "I06": "Tiempo de uso semanal mediano: minutos estimados por el campus, divididos por las semanas desde el alta.",
    "I07": "Tasa de inactividad: inscriptos vigentes sin eventos en el período que fija la regla de inactividad.",
    "I08": "Sesiones por alumno por semana, según la regla de sesión.",
    "I09": "Mezcla de actividad: eventos de cada categoría sobre el total.",
    "I10": "Nota normalizada al corte: lo obtenido sobre lo que se podía obtener hasta la fecha de corte. Lo no rendido cuenta cero.",
    "I11": "Condición proyectada a la fecha de corte, con los umbrales de la materia.",
    "I12": "Tasa de entrega: inscriptos vigentes que rindieron el instrumento.",
    "I13": "Tasa de aprobación: notas marcadas como aprobadas sobre las rendidas.",
    "I14": "Correlación de Spearman entre tiempo de uso y nota. Correlación no es causa.",
    "I15": "Grupos de riesgo: participación contra la mediana de la materia y nota contra el umbral de regular.",
}


# =============================================================================
# TEMA DE PLOTLY
# =============================================================================

def aplicar_tema():
    """Registra el tema 'tfi' y lo deja como predeterminado para todos los gráficos.

    Se llama una sola vez, al principio de app.py. Después cualquier px.bar,
    px.line, etc. sale con la misma tipografía, grilla y márgenes.
    """
    tema = go.layout.Template()
    tema.layout = go.Layout(
        font=dict(family=FUENTE, size=13, color=GRIS_TEXTO),
        # El título va pegado arriba del todo y la leyenda justo encima del gráfico:
        # así no se pisan aunque el gráfico tenga las dos cosas.
        title=dict(font=dict(size=16), x=0, xanchor="left", y=0.98, yref="container", yanchor="top"),
        colorway=PALETA_MATERIAS,
        paper_bgcolor="rgba(0,0,0,0)",  # respeta el fondo de Streamlit
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=90, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    title_text=""),
        hoverlabel=dict(font_family=FUENTE),
        bargap=0.25,
        xaxis=dict(showgrid=False, linecolor=GRIS_GRILLA, ticks=""),
        yaxis=dict(gridcolor=GRIS_GRILLA, zeroline=False, ticks=""),
    )
    # Barras sin borde y puntos con un aro blanco: separa marcas superpuestas.
    tema.data.bar = [go.Bar(marker_line_width=0)]
    tema.data.scatter = [go.Scatter(marker=dict(size=9, line=dict(width=1, color="white")))]
    pio.templates["tfi"] = tema
    pio.templates.default = "plotly_white+tfi"


# =============================================================================
# FORMATO DE NÚMEROS (que el mismo dato se lea igual en todos lados)
# =============================================================================

def fmt_pct(valor, decimales=1, es_proporcion=False):
    """45.67 -> '45,7 %'. Con es_proporcion=True, 0.4567 -> '45,7 %'.

    Se pide explícito porque adivinarlo falla: un 1 puede ser 1 % o 100 %.
    """
    if valor is None or valor != valor:  # None o NaN
        return "s/d"
    if es_proporcion:
        valor = valor * 100
    return f"{valor:.{decimales}f} %".replace(".", ",")


def fmt_entero(valor):
    """1793 -> '1.793'."""
    if valor is None or valor != valor:
        return "s/d"
    return f"{int(round(valor)):,}".replace(",", ".")
