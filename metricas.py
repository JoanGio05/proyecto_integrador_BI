"""Indicadores del dashboard 5 y del informe, calculados a la fecha de corte.

QUÉ HACE, EN UNA LÍNEA
    Junta en una fila por inscripto y materia lo que hace falta para cruzar
    notas con participación: la condición a la fecha de corte, las sesiones,
    la inactividad y el grupo de riesgo.

QUÉ REUSA (para que todos los dashboards den lo mismo)
    - corte.situacion_alumnos() de Juanma: quién estaba inscripto y quién
      estaba activo o inactivo a la fecha de corte.
    - evaluador_condiciones de Joan: la condición final, con las reglas de
      reglas_materias.json. Acá no hay otra regla de condición.

QUÉ AGREGA
    - La fecha de cada examen, deducida de la trazabilidad: el campus no la
      exporta. Con ella, a una fecha de corte pasada solo cuentan los exámenes
      que ya se habían abierto. En la última fecha cuentan todos, así que la
      condición coincide con la del dashboard 4.
    - Las sesiones, con la regla de Lauti (participacion_trazabilidad.py).
    - Los grupos de riesgo y la correlación de Spearman (fichas I14 e I15).

POR QUÉ ES ESCALABLE
    Ninguna función nombra una materia ni un examen. Todo se agrupa por
    "materia", y una materia nueva entra sola: sin su fila en reglas_materias.json
    usa la regla por defecto del evaluador, y con su fila, la de la cátedra.

USO
    from corte import cargar_tablas
    import metricas
    tablas = cargar_tablas()
    alumnos = metricas.tabla_alumnos(tablas, reglas, fecha_corte, dias_inactividad=14)
"""
import html
import re

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from corte import DIAS_INACTIVIDAD, limite_del_corte, situacion_alumnos
from evaluador_condiciones import _es_recuperatorio, calcular_condiciones_estudiantes, regla_de
from participacion_trazabilidad import MINUTOS_SESION, calcular_sesiones

# =============================================================================
# PARÁMETROS
# =============================================================================

# MINUTOS_SESION (30) viene de participacion_trazabilidad.py, la regla de Lauti:
# una sesión termina cuando pasan más de 30 minutos sin ningún evento.

# Los grupos de riesgo de la ficha I15, con la acción que corresponde a cada uno.
GRUPOS = ["en_camino", "autonomo", "esfuerzo_sin_resultado", "riesgo_abandono"]
ACCIONES = {
    "en_camino": "Ninguna",
    "autonomo": "Ninguna; vigilar que no baje",
    "esfuerzo_sin_resultado": "Tutoría académica: consultas y material de refuerzo",
    "riesgo_abandono": "Contacto directo del tutor (mail o llamada)",
}

# Variables de participación que se pueden cruzar con la nota.
VARIABLES_PARTICIPACION = {
    "sesiones_semana": "Sesiones por semana (trazabilidad, respeta el corte)",
    "minutos_semana": "Minutos por semana en sesión (trazabilidad, respeta el corte)",
    "tiempo_uso_semana": "Minutos por semana según el campus (participación, a la exportación)",
    "avance_pct": "Avance del aula, % (participación, a la exportación)",
}


# =============================================================================
# FECHA DE CADA EXAMEN
# =============================================================================

def _nombre_en_evento(descripcion):
    # "Realización de la evaluación '&#129504; PARCIAL 1' de la unidad ..." -> "PARCIAL 1"
    hallado = re.search(r"evaluaci[oó]n '(.+?)'", str(descripcion))
    if not hallado:
        return None
    nombre = html.unescape(hallado.group(1))
    nombre = "".join(c for c in nombre if c.isalnum() or c in " .,:;-_()°º/")
    return re.sub(r"\s+", " ", nombre).strip()


def _clave(texto):
    # Para comparar nombres de examen sin tildes, mayúsculas ni signos.
    texto = str(texto).translate(str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")).lower()
    return re.sub(r"[^a-z0-9]+", "", texto)


def fechas_examenes(tablas):
    """Una fila por examen con notas, con la fecha en que se abrió.

    El campus no exporta la fecha de los exámenes, pero la trazabilidad
    registra cada "Realizar evaluación" con el nombre del examen. Se toma:
      fecha_apertura    la primera realización: desde ahí el examen cuenta
      fecha_referencia  la mediana de las realizaciones, para el informe

    Un examen sin eventos queda sin fecha y cuenta siempre: es preferible
    contarlo de más a dejar de penalizar a un ausente.

    Devuelve (examenes, faltantes). faltantes son los exámenes que aparecen
    en la trazabilidad y no tienen archivo de notas (exportaciones que faltan).
    """
    traza = tablas["interacciones"]
    real = traza[traza["accion"] == "Realizar evaluación"].copy()
    real["instrumento_evento"] = real["descripcion"].map(_nombre_en_evento)
    real["clave"] = real["instrumento_evento"].map(_clave)
    fechas = (real.groupby(["materia", "clave"])
              .agg(instrumento_evento=("instrumento_evento", "first"),
                   fecha_apertura=("fecha_hora", "min"),
                   fecha_referencia=("fecha_hora", "median"),
                   realizaciones=("id_alumno", "nunique"))
              .reset_index())

    columnas = ["id_evaluacion", "materia", "nombre_materia", "instrumento", "categoria_evaluacion"]
    examenes = tablas["calificaciones"][columnas].drop_duplicates("id_evaluacion").copy()
    examenes["clave"] = examenes["instrumento"].map(_clave)
    examenes = examenes.merge(fechas.drop(columns="instrumento_evento"), on=["materia", "clave"], how="left")

    cruce = fechas.merge(examenes[["materia", "clave"]], on=["materia", "clave"], how="left", indicator=True)
    faltantes = cruce[cruce["_merge"] == "left_only"].drop(columns=["_merge", "clave"])
    return examenes.drop(columns="clave"), faltantes.reset_index(drop=True)


# =============================================================================
# CONDICIÓN A LA FECHA DE CORTE (I10, I11)
# =============================================================================

def umbrales_pct(reglas, materias=()):
    """{materia: (umbral de regular en %, umbral de promoción en %)} según reglas_materias.json.

    Las materias de `materias` que no tienen fila usan la regla por defecto del evaluador.
    """
    salida = {}
    for materia in list(reglas) + [m for m in materias if m not in reglas]:
        regla = regla_de(reglas, materia)
        maximo = float(regla.get("puntaje_maximo", 100)) or 100.0
        salida[materia] = (100 * float(regla.get("umbral_regular", 60)) / maximo,
                           100 * float(regla.get("umbral_promocion", 85)) / maximo)
    return salida


def condicion_al_corte(tablas, reglas, fecha_corte):
    """La condición de Joan, contando solo los exámenes abiertos hasta la fecha de corte.

    Devuelve las columnas del evaluador (id_alumno, materia, nota,
    puntaje_tomado, nota_normalizada, condicion) más examenes_tomados y
    examenes_rendidos, para explicar el motivo en la lista de intervención.
    """
    examenes, _ = fechas_examenes(tablas)
    limite = limite_del_corte(fecha_corte)
    abiertos = examenes.loc[examenes["fecha_apertura"].isna() | (examenes["fecha_apertura"] < limite),
                            "id_evaluacion"]
    notas = tablas["calificaciones"]
    notas = notas[notas["id_evaluacion"].isin(abiertos)]

    condiciones, _ = calcular_condiciones_estudiantes(notas, reglas, df_matricula=tablas["matricula"])

    # Cuántos exámenes se tomaron en cada materia y cuántos rindió cada alumno.
    # Los recuperatorios no cuentan como un examen más.
    base = notas[~_es_recuperatorio(notas)]
    tomados = base.groupby("materia")["id_evaluacion"].nunique().rename("examenes_tomados")
    rendidos = (base[base["nota"].notna()].groupby(["id_alumno", "materia"])["id_evaluacion"]
                .nunique().rename("examenes_rendidos").reset_index())
    condiciones = condiciones.merge(tomados, on="materia", how="left")
    condiciones = condiciones.merge(rendidos, on=["id_alumno", "materia"], how="left")
    condiciones["examenes_rendidos"] = condiciones["examenes_rendidos"].fillna(0).astype(int)
    return condiciones


# =============================================================================
# SESIONES (I08)
# =============================================================================

def sesiones(tablas, fecha_corte, minutos=MINUTOS_SESION):
    """Una fila por sesión: alumno, materia, inicio, fin, duración y eventos.

    Usa la regla de sesión de Lauti (participacion_trazabilidad.calcular_sesiones),
    así los dashboards 2, 3 y 5 cuentan las mismas sesiones. Solo eventos hasta el corte.
    """
    t = tablas["interacciones"]
    t = t[t["fecha_hora"] < limite_del_corte(fecha_corte)]
    s = calcular_sesiones(t, minutos)
    return s.rename(columns={"numero_sesion": "n_sesion", "duracion_observada_min": "duracion_min"})


# =============================================================================
# LA TABLA DEL DASHBOARD 5 (I14, I15)
# =============================================================================

def tabla_alumnos(tablas, reglas, fecha_corte, dias_inactividad=DIAS_INACTIVIDAD,
                  variable="sesiones_semana", minutos=MINUTOS_SESION):
    """Una fila por inscripto vigente a la fecha de corte y materia.

    Grupo de riesgo: participación contra la mediana de su materia y condición
    (regular o promociona = aprueba). Un inactivo que no aprueba va siempre a
    riesgo de abandono. Un alumno de una materia sin regla queda "sin_datos".
    """
    limite = limite_del_corte(fecha_corte)

    # 1. Inscriptos vigentes a la fecha, con su actividad (corte.py, Juanma).
    sit = situacion_alumnos(tablas, fecha_corte, dias_inactividad)
    t = sit[sit["inscripcion"] == "Inscripto"].copy()
    t["nunca_entro"] = t["actividad"] == "Nunca ingresó"
    t["inactivo"] = t["actividad"] != "Activo"

    # 2. Sesiones y minutos por semana de cursada hasta el corte.
    s = sesiones(tablas, fecha_corte, minutos)
    por_alumno = (s.groupby(["id_alumno", "materia"])
                  .agg(sesiones=("n_sesion", "size"), minutos_sesion=("duracion_min", "sum"))
                  .reset_index())
    t = t.merge(por_alumno, on=["id_alumno", "materia"], how="left")
    inicio = tablas["materia"].set_index("materia")["fecha_min"]
    semanas = ((limite - t["materia"].map(inicio)).dt.days / 7).clip(lower=1)
    t["sesiones"] = t["sesiones"].fillna(0).astype(int)
    t["sesiones_semana"] = (t["sesiones"] / semanas).round(2)
    t["minutos_semana"] = (t["minutos_sesion"].fillna(0) / semanas).round(1)

    # 3. Lo que informa el campus en el reporte de participación (a la exportación).
    p = tablas["participacion"][["id_alumno", "materia", "avance_pct", "tiempo_uso_min", "fecha_alta"]]
    t = t.merge(p.drop_duplicates(["id_alumno", "materia"]), on=["id_alumno", "materia"], how="left")
    exportacion = pd.to_datetime(t["materia"].map(tablas["materia"].set_index("materia")["fecha_exportacion"]),
                                 format="%d/%m/%Y", errors="coerce")
    semanas_alta = ((exportacion - t["fecha_alta"]).dt.days / 7).clip(lower=1)
    t["tiempo_uso_semana"] = (t["tiempo_uso_min"] / semanas_alta).round(1)

    # 4. Condición a la fecha de corte (evaluador de Joan).
    cond = condicion_al_corte(tablas, reglas, fecha_corte)
    t = t.merge(cond, on=["id_alumno", "materia"], how="left")
    umbrales = umbrales_pct(reglas, t["materia"].unique())
    t["umbral_regular_pct"] = t["materia"].map(lambda m: umbrales.get(m, (np.nan, np.nan))[0])

    # 5. Grupo de riesgo.
    mediana = t.groupby("materia")[variable].transform("median")
    alta = t[variable] > mediana
    aprueba = t["condicion"].isin(["regular", "promociona"])
    t["participacion_alta"] = alta
    t["grupo"] = np.select(
        [alta & aprueba, ~alta & aprueba, alta & ~aprueba],
        ["en_camino", "autonomo", "esfuerzo_sin_resultado"], default="riesgo_abandono")
    t.loc[t["inactivo"] & ~aprueba, "grupo"] = "riesgo_abandono"
    t.loc[t["condicion"].isna(), "grupo"] = "sin_datos"

    # 6. El motivo, en palabras, para el que tiene que llamar al alumno.
    motivos = []
    for _, r in t.iterrows():
        m = []
        if r["nunca_entro"]:
            m.append("nunca entró al aula")
        elif r["inactivo"]:
            m.append(f"{int(r['dias_sin_actividad'])} días sin entrar")
        if pd.notna(r["examenes_tomados"]) and r["examenes_rendidos"] < r["examenes_tomados"]:
            m.append(f"rindió {int(r['examenes_rendidos'])} de {int(r['examenes_tomados'])} exámenes")
        if r["grupo"] in ("riesgo_abandono", "esfuerzo_sin_resultado") and pd.notna(r["nota_normalizada"]):
            m.append(f"nota {r['nota_normalizada']:.0f} % (regular {r['umbral_regular_pct']:.0f} %)")
        motivos.append("; ".join(m))
    t["motivo"] = motivos
    t["accion"] = t["grupo"].map(ACCIONES).fillna("Revisar la regla de la materia")
    return t.reset_index(drop=True)


def correlaciones(tabla, variable="sesiones_semana"):
    """ρ de Spearman entre la variable de participación y la nota, por materia (I14)."""
    filas = []
    for materia, g in tabla.dropna(subset=[variable, "nota_normalizada"]).groupby("materia"):
        if len(g) >= 10 and g[variable].nunique() > 1 and g["nota_normalizada"].nunique() > 1:
            r = spearmanr(g[variable], g["nota_normalizada"])
            filas.append({"materia": materia, "rho": round(float(r.statistic), 2),
                          "p_valor": float(r.pvalue), "n": len(g)})
        else:
            filas.append({"materia": materia, "rho": np.nan, "p_valor": np.nan, "n": len(g)})
    return pd.DataFrame(filas, columns=["materia", "rho", "p_valor", "n"])


def fuerza(rho):
    """Lectura en palabras del coeficiente, para que el docente no tenga que interpretarlo."""
    if pd.isna(rho):
        return "sin datos suficientes"
    a = abs(rho)
    nivel = "muy débil" if a < 0.2 else "débil" if a < 0.4 else "moderada" if a < 0.6 else "fuerte"
    return f"{nivel}, {'positiva' if rho > 0 else 'negativa'}"
