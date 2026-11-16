"""Cálculos de Lauti sobre las tablas existentes, sin modificar el ETL."""
from pathlib import Path
import html
import re
import unicodedata

import pandas as pd

MINUTOS_SESION = 30
CATEGORIAS = ["clic", "material", "examen"]
COLORES_EVENTOS = {"clic": "#7b4ea3", "material": "#17becf", "examen": "#e67e22"}
RUTA_EQUIVALENCIAS = Path(__file__).with_name("equivalencias_eventos.csv")


def normalizar_evento(valor):
    if pd.isna(valor):
        return ""
    return " ".join(unicodedata.normalize("NFKD", str(valor)).encode(
        "ascii", "ignore").decode().lower().split())


def cargar_equivalencias(ruta=RUTA_EQUIVALENCIAS):
    tabla = pd.read_csv(ruta, keep_default_na=False)
    for campo in ("seccion", "accion"):
        tabla[campo] = tabla[campo].map(normalizar_evento)
    if tabla.duplicated(["seccion", "accion"]).any():
        raise ValueError("Hay eventos repetidos en la tabla de equivalencias.")
    if not tabla["categoria"].isin(CATEGORIAS).all():
        raise ValueError("Las categorías permitidas son clic, material y examen.")
    return tabla


def clasificar_eventos(eventos, equivalencias=None):
    """Cruce por sección Y acción; evento nuevo = clic provisional y aviso.

    No se usan id_evento del ETL: pueden cambiar al incorporar otra materia.
    El cruce muchos-a-uno conserva exactamente la cantidad de hechos.
    """
    equivalencias = cargar_equivalencias() if equivalencias is None else equivalencias
    df = eventos.copy()
    for campo in ("seccion", "accion"):
        df[f"_{campo}"] = df[campo].map(normalizar_evento)
    reglas = equivalencias.rename(columns={"seccion": "_seccion", "accion": "_accion"})
    df = df.merge(reglas[["_seccion", "_accion", "categoria"]],
                  on=["_seccion", "_accion"], how="left", validate="many_to_one")
    df["evento_sin_equivalencia"] = df["categoria"].isna()
    df["categoria"] = df["categoria"].fillna("clic")
    return df.drop(columns=["_seccion", "_accion"])


def calcular_sesiones(eventos, minutos=MINUTOS_SESION):
    """Sesión por alumno/materia/aula: un hueco MAYOR a 30 min inicia otra.

    Se ejecuta antes de filtrar el rango visible. La duración es solo el lapso
    observado entre primer y último evento, sin agregar minutos al final.
    """
    if minutos <= 0:
        raise ValueError("El umbral de sesión debe ser positivo.")
    claves = ["id_alumno", "materia", "id_materia_aula"]
    columnas = claves + ["numero_sesion", "inicio", "fin", "eventos", "duracion_observada_min"]
    if eventos.empty:
        return pd.DataFrame(columns=columnas)
    df = eventos.copy()
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
    df = df.sort_values(claves + ["fecha_hora"], kind="stable")
    diferencia = df.groupby(claves)["fecha_hora"].diff()
    nueva = diferencia.isna() | diferencia.gt(pd.Timedelta(minutes=minutos))
    df["numero_sesion"] = nueva.groupby([df[c] for c in claves]).cumsum()
    sesiones = df.groupby(claves + ["numero_sesion"], as_index=False).agg(
        inicio=("fecha_hora", "min"), fin=("fecha_hora", "max"), eventos=("fecha_hora", "size"))
    sesiones["duracion_observada_min"] = (sesiones["fin"] - sesiones["inicio"]).dt.total_seconds() / 60
    return sesiones[columnas]


def filtrar_rango(df, desde, hasta, columna="fecha_hora"):
    inicio = pd.Timestamp(desde).normalize()
    fin = pd.Timestamp(hasta).normalize() + pd.Timedelta(days=1)
    return df.loc[(df[columna] >= inicio) & (df[columna] < fin)].copy()


def sesiones_en_periodo(sesiones, desde, hasta):
    """Conserva las sesiones con actividad en el rango, sin reconstruirlas otra vez.

    Una sesión que cruza el inicio del período se cuenta una sola vez.
    """
    inicio = pd.Timestamp(desde).normalize()
    fin = pd.Timestamp(hasta).normalize() + pd.Timedelta(days=1)
    return sesiones.loc[sesiones["fin"].ge(inicio) & sesiones["inicio"].lt(fin)].copy()


def resumen_participacion(alumnos, sesiones, participacion):
    """Una fila por alumno/materia; los que no entraron tienen cero sesiones.

    Tiempo y avance se leen exclusivamente de la foto exportada, sin estimar
    valores históricos. Un valor ausente queda ausente.
    """
    claves = ["id_alumno", "materia"]
    conteo = sesiones.groupby(claves).size().rename("sesiones").reset_index()
    foto = participacion.groupby(claves, as_index=False).agg(
        tiempo_uso_min=("tiempo_uso_min", lambda s: s.sum(min_count=1)),
        avance_pct=("avance_pct", "mean"))
    resultado = alumnos.merge(conteo, on=claves, how="left", validate="one_to_one")
    resultado = resultado.merge(foto, on=claves, how="left", validate="one_to_one")
    resultado["sesiones"] = resultado["sesiones"].fillna(0).astype(int)
    return resultado


def mapa_calor(eventos):
    """Siempre siete días por 24 horas, incluso sin eventos."""
    if eventos.empty:
        return pd.DataFrame(0, index=range(7), columns=range(24))
    return pd.crosstab(eventos["fecha_hora"].dt.dayofweek, eventos["fecha_hora"].dt.hour).reindex(
        index=range(7), columns=range(24), fill_value=0)


def resumen_horarios(eventos):
    """168 celdas con total, tipos y personas únicas dentro de los eventos recibidos.

    Un alumno en varias materias o semanas cuenta una vez en la misma celda.
    Las personas de distintas celdas no se pueden sumar como alumnos únicos.
    """
    indice = pd.MultiIndex.from_product([range(7), range(24)], names=["dia", "hora"])
    resumen = pd.DataFrame(0, index=indice, columns=["interacciones", *CATEGORIAS, "alumnos"])
    if eventos.empty:
        return resumen
    datos = eventos.assign(dia=eventos["fecha_hora"].dt.day_of_week, hora=eventos["fecha_hora"].dt.hour)
    grupos = datos.groupby(["dia", "hora"])
    resumen["interacciones"] = grupos.size().reindex(indice, fill_value=0)
    resumen["alumnos"] = grupos["id_alumno"].nunique().reindex(indice, fill_value=0)
    tipos = datos.groupby(["dia", "hora", "categoria"]).size().unstack("categoria", fill_value=0)
    resumen[CATEGORIAS] = tipos.reindex(index=indice, columns=CATEGORIAS, fill_value=0)
    return resumen


def resumir_contenidos(eventos):
    """Agrupa consultas al mismo contenido, conservando materia, aula, sección y unidad.

    Vista, descarga y otras acciones sobre un mismo título se cuentan juntas.
    Las entradas genéricas sin título no se presentan como contenidos consultados.
    """
    columnas = ["Materia", "Aula", "Tipo", "Sección", "Contenido", "Unidad", "Interacciones", "Última interacción"]
    datos = eventos.loc[eventos["categoria"].isin(["material", "examen"])].copy()
    identificados = []
    for indice, descripcion in datos["descripcion"].items():
        texto = html.unescape(str(descripcion)) if pd.notna(descripcion) else ""
        coincidencia = re.fullmatch(r"[^']*'(.+)' de la unidad '(.*)'\s*", texto)
        if coincidencia:
            titulo, unidad = coincidencia.groups()
        else:
            coincidencia = re.fullmatch(r"[^']*'(.+)'\s*", texto)
            titulo, unidad = (coincidencia.group(1), "") if coincidencia else ("", "")
        if titulo.strip():
            identificados.append((indice, " ".join(titulo.split()), " ".join(unidad.split())))
    sin_titulo = len(datos) - len(identificados)
    if not identificados:
        return pd.DataFrame(columns=columnas), sin_titulo
    titulos = pd.DataFrame(identificados, columns=["indice", "contenido", "unidad"]).set_index("indice")
    datos = datos.join(titulos, how="inner")
    for campo in ["seccion", "contenido", "unidad"]:
        datos[f"clave_{campo}"] = datos[campo].map(normalizar_evento)
    claves = ["materia", "id_materia_aula", "categoria", "clave_seccion", "clave_contenido", "clave_unidad"]
    resumen = datos.groupby(claves, as_index=False, dropna=False).agg(
        Materia=("nombre_materia", "first"), Aula=("aula", "first"),
        Tipo=("categoria", "first"), Sección=("seccion", "first"),
        Contenido=("contenido", "first"), Unidad=("unidad", "first"),
        Interacciones=("fecha_hora", "size"), ultima=("fecha_hora", "max"),
    ).rename(columns={"ultima": "Última interacción"})
    return resumen[columnas].sort_values(
        ["Interacciones", "Última interacción", "Contenido"], ascending=[False, False, True], kind="stable",
    ).reset_index(drop=True), sin_titulo
