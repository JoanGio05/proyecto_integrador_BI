from pathlib import Path

import pandas as pd


def verificar_nombres_archivos(archivos_encontrados):
    """Devuelve los archivos que no respetan la nomenclatura del LMS."""
    prefijos_validos = (
        "reporte_trazabilidad_",
        "reporte_participacion_",
        "calificaciones_alumnos_",
        "matriculados_",
    )

    archivos_no_reconocidos = []

    for archivo in archivos_encontrados:
        nombre = Path(archivo).name.lower()
        if not nombre.endswith(".csv") or not nombre.startswith(prefijos_validos):
            archivos_no_reconocidos.append(archivo)

    return archivos_no_reconocidos


def validar_columnas_requeridas(df, columnas_esperadas, nombre_fuente):
    """Informa si faltan columnas obligatorias en una fuente."""
    faltantes = columnas_esperadas - set(df.columns)

    if not faltantes:
        return []

    return [
        f"⚠️ [Estructura] La fuente '{nombre_fuente}' no contiene las columnas requeridas: "
        f"{', '.join(sorted(faltantes))}"
    ]


def validar_materias_configuradas(df_calificaciones, reglas_dict):
    """Detecta materias que no tienen reglas de evaluación en el JSON."""
    materias_configuradas = {
        str(materia).strip().lower() for materia in reglas_dict
    }
    materias_en_datos = (
        df_calificaciones["materia"].dropna().astype(str).str.strip().str.lower().unique()
    )

    alertas = []
    for materia in materias_en_datos:
        if materia not in materias_configuradas:
            alertas.append(
                f"🚨 [Configuración] Materia sin reglas de evaluación: '{materia}'"
            )

    return alertas


def validar_alumnos_matriculados(df_actividad_o_calif, df_matriculados):
    """Detecta alumnos con actividad o notas que no figuran en el padrón."""
    columnas = ["id_alumno", "materia"]

    df_actividad = df_actividad_o_calif[columnas].dropna().copy()
    df_padron = df_matriculados[columnas].dropna().copy()

    for df in [df_actividad, df_padron]:
        df["id_alumno"] = df["id_alumno"].astype(str).str.strip()
        df["materia"] = df["materia"].astype(str).str.strip().str.lower()

    df_actividad = df_actividad.drop_duplicates()
    df_padron = df_padron.drop_duplicates()

    # El cruce conserva los pares alumno-materia que no aparecen en el padrón.
    comparacion = df_actividad.merge(
        df_padron,
        on=columnas,
        how="left",
        indicator=True,
    )
    no_matriculados = comparacion.loc[
        comparacion["_merge"] == "left_only", columnas
    ]

    alertas = []
    for _, fila in no_matriculados.iterrows():
        alertas.append(
            f"🚨 [Matrícula] Alumno '{fila['id_alumno']}' registra actividad/nota "
            f"en '{fila['materia']}', pero NO está en el padrón oficial."
        )

    return no_matriculados.reset_index(drop=True), alertas


def ejecutar_control_de_carga(
    archivos_carpeta,
    df_calificaciones,
    df_matriculados,
    reglas_dict,
):
    """Ejecuta las validaciones de archivos, estructura, reglas y matrícula."""
    reporte = {
        "archivos_no_reconocidos": verificar_nombres_archivos(archivos_carpeta),
        "alertas_estructura": [],
        "alertas_configuracion": [],
        "alertas_matricula": [],
        "alumnos_no_matriculados_df": pd.DataFrame(
            columns=["id_alumno", "materia"]
        ),
        "es_valido": True,
    }

    columnas_calificaciones = {
        "id_alumno",
        "materia",
        "tipo_evaluacion",
        "nota",
    }
    columnas_matriculados = {"id_alumno", "materia"}

    reporte["alertas_estructura"].extend(
        validar_columnas_requeridas(
            df_calificaciones, columnas_calificaciones, "calificaciones"
        )
    )
    reporte["alertas_estructura"].extend(
        validar_columnas_requeridas(
            df_matriculados, columnas_matriculados, "matriculados"
        )
    )

    # No ejecutar validaciones que necesitan columnas inexistentes.
    if "materia" in df_calificaciones.columns:
        reporte["alertas_configuracion"] = validar_materias_configuradas(
            df_calificaciones, reglas_dict
        )

    if columnas_matriculados.issubset(df_calificaciones.columns) and (
        columnas_matriculados.issubset(df_matriculados.columns)
    ):
        df_no_matriculados, alertas = validar_alumnos_matriculados(
            df_calificaciones, df_matriculados
        )
        reporte["alumnos_no_matriculados_df"] = df_no_matriculados
        reporte["alertas_matricula"] = alertas

    hay_alertas = (
        reporte["archivos_no_reconocidos"]
        or reporte["alertas_estructura"]
        or reporte["alertas_configuracion"]
        or reporte["alertas_matricula"]
    )
    reporte["es_valido"] = not hay_alertas

    return reporte