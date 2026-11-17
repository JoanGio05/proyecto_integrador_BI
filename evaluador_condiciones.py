import json
import re
import pandas as pd


# Regla para una materia que todavía no tiene su fila en reglas_materias.json.
# Así una materia nueva aparece con condición en todos los dashboards apenas se
# carga, sin tocar nada. La nota se mide sobre lo tomado (puntos obtenidos ÷
# puntos tomados), así que sirve para cualquier escala de notas. Regular con 60 %
# y promoción con 85 %, como Álgebra y Probabilidad.
# La app avisa qué materias la usan: para la regla de la cátedra, se agrega su fila.
REGLA_POR_DEFECTO = {
    "metodo_calculo": "suma",
    "puntaje_maximo": 100.0,
    "umbral_regular": 60.0,
    "umbral_promocion": 85.0,
    "tratamiento_recuperatorio": "ninguno",
    "tratamiento_ausentes": "cero",
}


def regla_de(reglas_dict, materia):
    """La regla de la materia, o REGLA_POR_DEFECTO si no tiene fila en el JSON."""
    return reglas_dict.get(str(materia).strip().lower(), REGLA_POR_DEFECTO)


def cargar_reglas_json(ruta_archivo="reglas_materias.json"):
    """Carga las reglas de evaluación desde un archivo JSON."""
    with open(ruta_archivo, "r", encoding="utf-8") as f:
        return json.load(f)


def determinar_condicion(nota, umbral_regular, umbral_promocion):
    """Devuelve la condición académica según la nota."""
    if nota >= umbral_promocion:
        return "promociona"
    elif nota >= umbral_regular:
        return "regular"
    else:
        return "libre"


def _es_recuperatorio(df):
    """Identifica filas correspondientes a recuperatorios."""
    if "categoria_evaluacion" in df.columns:
        return (
            df["categoria_evaluacion"]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("recuperatorio")
        )
    return (
        df["tipo_evaluacion"]
        .astype(str)
        .str.lower()
        .str.contains("recuperatorio", na=False)
    )


def procesar_recuperatorios(df_grupo, regla):
    """Reemplaza la evaluación correspondiente (o la menor de su categoría) si el recuperatorio es mayor."""
    df = df_grupo.copy()

    tratamiento = str(regla.get("tratamiento_recuperatorio", "")).strip().lower()
    if tratamiento in ("ninguno", "no_aplica", "ignorar"):
        return df

    es_recup = _es_recuperatorio(df)
    if not es_recup.any():
        return df

    recuperatorios = df.loc[es_recup].copy()
    evaluaciones = df.loc[~es_recup].copy()

    if evaluaciones.empty:
        return evaluaciones

    tipos_eval = evaluaciones["tipo_evaluacion"].astype(str).str.strip().str.lower()

    for _, recup in recuperatorios.iterrows():
        nota_recup = recup["nota"]
        if pd.isna(nota_recup):
            continue

        tipo_recup = str(recup["tipo_evaluacion"]).strip().lower()
        objetivo_slug = re.sub(r"^recuperatorio_?", "", tipo_recup).strip("_")

        idx_objetivo = None

        # 1. Coincidencia directa con la evaluación que recupera
        if objetivo_slug:
            coincidencias = evaluaciones.index[tipos_eval == objetivo_slug]
            if len(coincidencias) > 0:
                idx_objetivo = coincidencias[0]

        # 2. Respaldo por categoría (evaluacion_semanal o parcial)
        if idx_objetivo is None:
            if "semanal" in objetivo_slug or "semanal" in tratamiento:
                cat_objetivo = "evaluacion_semanal"
            elif "parcial" in objetivo_slug or "parcial" in tratamiento:
                cat_objetivo = "parcial"
            else:
                cat_objetivo = None

            if cat_objetivo and "categoria_evaluacion" in evaluaciones.columns:
                candidatos = evaluaciones[
                    evaluaciones["categoria_evaluacion"].astype(str).str.lower()
                    == cat_objetivo
                ]
            elif cat_objetivo:
                candidatos = evaluaciones[
                    tipos_eval.str.contains(cat_objetivo, na=False)
                ]
            else:
                candidatos = pd.DataFrame()

            if not candidatos.empty:
                idx_objetivo = candidatos["nota"].fillna(-1).idxmin()

        if idx_objetivo is not None:
            nota_actual = evaluaciones.loc[idx_objetivo, "nota"]
            if pd.isna(nota_actual) or nota_recup > nota_actual:
                evaluaciones.loc[idx_objetivo, "nota"] = nota_recup

    return evaluaciones.copy()


def _obtener_evaluaciones_base_materia(df_materia, incluir_recuperatorios=False):
    """Devuelve las evaluaciones tomadas en la materia con su puntaje máximo y metadatos."""
    df_base = (
        df_materia.copy()
        if incluir_recuperatorios
        else df_materia.loc[~_es_recuperatorio(df_materia)].copy()
    )
    clave_eval = (
        "id_evaluacion" if "id_evaluacion" in df_base.columns else "tipo_evaluacion"
    )
    cols_extra = [
        c for c in ("tipo_evaluacion", "categoria_evaluacion")
        if c in df_base.columns and c != clave_eval
    ]

    if "nota_maxima" in df_base.columns:
        df_base["nota_maxima"] = pd.to_numeric(df_base["nota_maxima"], errors="coerce")
        agg_dict = {"nota_maxima": "max"}
        for c in cols_extra:
            agg_dict[c] = "first"
        evals = df_base.groupby(clave_eval, as_index=False).agg(agg_dict)
    else:
        evals = df_base[[clave_eval] + cols_extra].drop_duplicates(subset=[clave_eval]).copy()
        evals["nota_maxima"] = 100.0

    return evals, clave_eval


def calcular_resultado_estudiante(
    id_alumno,
    materia,
    df_grupo,
    regla,
    evals_materia=None,
    clave_eval="tipo_evaluacion",
):
    """Calcula la nota final, puntaje tomado, porcentaje y condición académica."""
    df = df_grupo.copy()
    df["nota"] = pd.to_numeric(df["nota"], errors="coerce")

    tratamiento_ausentes = str(regla.get("tratamiento_ausentes", "cero")).strip().lower()
    if tratamiento_ausentes == "cero":
        df["nota"] = df["nota"].fillna(0.0)

    # Completar con 0 las evaluaciones base ya tomadas en la materia que el alumno no rindió
    # ANTES de procesar recuperatorios, para que el recuperatorio encuentre su evaluación objetivo.
    if (
        evals_materia is not None
        and not evals_materia.empty
        and tratamiento_ausentes == "cero"
    ):
        es_recup = _es_recuperatorio(df)
        df_recup = df.loc[es_recup].copy()
        df_base = df.loc[~es_recup].copy()

        presentes = set(df_base[clave_eval].dropna()) if clave_eval in df_base.columns else set()
        faltantes = evals_materia[~evals_materia[clave_eval].isin(presentes)]

        if not faltantes.empty:
            filas_cero = pd.DataFrame({
                "id_alumno": id_alumno,
                "materia": materia,
                clave_eval: faltantes[clave_eval].values,
                "nota": 0.0,
            })
            if clave_eval != "tipo_evaluacion" and "tipo_evaluacion" in faltantes.columns:
                filas_cero["tipo_evaluacion"] = faltantes["tipo_evaluacion"].values
            if "categoria_evaluacion" in faltantes.columns:
                filas_cero["categoria_evaluacion"] = faltantes["categoria_evaluacion"].values

            df = pd.concat([df_base, filas_cero, df_recup], ignore_index=True)

    # Resolver recuperatorios sobre el conjunto completo de evaluaciones base
    df = procesar_recuperatorios(df, regla)

    metodo = regla.get("metodo_calculo", "promedio")
    puntaje_maximo_total = float(regla.get("puntaje_maximo", 100.0))
    umbral_reg = float(regla.get("umbral_regular", 60.0))
    umbral_prom = float(regla.get("umbral_promocion", 85.0))

    if metodo == "suma":
        nota_final = float(df["nota"].sum()) if not df.empty else 0.0
        if evals_materia is not None and not evals_materia.empty:
            puntaje_tomado = float(evals_materia["nota_maxima"].fillna(0).sum())
        else:
            puntaje_tomado = puntaje_maximo_total

        if puntaje_tomado <= 0:
            puntaje_tomado = puntaje_maximo_total

        nota_normalizada = (
            round((nota_final / puntaje_tomado) * 100, 2) if puntaje_tomado > 0 else 0.0
        )
        if puntaje_maximo_total > 0:
            pct_reg = (umbral_reg / puntaje_maximo_total) * 100
            pct_prom = (umbral_prom / puntaje_maximo_total) * 100
        else:
            pct_reg, pct_prom = umbral_reg, umbral_prom

        condicion = determinar_condicion(nota_normalizada, pct_reg, pct_prom)

    elif metodo == "promedio":
        puntaje_tomado = puntaje_maximo_total
        nota_final = float(df["nota"].mean()) if not df.empty else 0.0
        if pd.isna(nota_final):
            nota_final = 0.0

        nota_normalizada = (
            round((nota_final / puntaje_maximo_total) * 100, 2)
            if puntaje_maximo_total > 0
            else 0.0
        )
        condicion = determinar_condicion(nota_final, umbral_reg, umbral_prom)

    else:
        raise ValueError(
            f"Método de cálculo no válido para '{materia}': '{metodo}'. "
            "Usá 'suma' o 'promedio'."
        )

    return {
        "id_alumno": id_alumno,
        "materia": materia,
        "nota": round(nota_final, 2),
        "puntaje_tomado": round(puntaje_tomado, 2),
        "nota_normalizada": nota_normalizada,
        "condicion": condicion,
    }


def calcular_condiciones_estudiantes(
    df_calificaciones,
    reglas_dict,
    df_matricula=None,
):
    """Calcula los resultados de todos los alumnos considerando el avance real de cada cátedra."""
    columnas_requeridas = {
        "id_alumno",
        "materia",
        "tipo_evaluacion",
        "nota",
    }
    columnas_faltantes = columnas_requeridas - set(df_calificaciones.columns)

    if columnas_faltantes:
        raise ValueError(
            "Faltan columnas en las calificaciones: "
            + ", ".join(sorted(columnas_faltantes))
        )

    df = df_calificaciones.copy()
    df["id_alumno"] = df["id_alumno"].astype(str).str.strip()
    df["materia"] = df["materia"].astype(str).str.strip().str.lower()

    # Incluir alumnos activos en matrícula aunque tengan 0 exámenes rendidos
    pares_extra = pd.DataFrame(columns=["id_alumno", "materia"])
    if df_matricula is not None and not df_matricula.empty:
        mat = df_matricula.copy()
        if "activo" in mat.columns:
            mat = mat[mat["activo"] == True]
        mat["id_alumno"] = mat["id_alumno"].astype(str).str.strip()
        mat["materia"] = mat["materia"].astype(str).str.strip().str.lower()
        pares_extra = mat[["id_alumno", "materia"]].drop_duplicates()

    resultados = []
    alertas = []

    materias_presentes = sorted(df["materia"].dropna().unique())

    for materia in materias_presentes:
        if materia not in reglas_dict:
            alertas.append(f"Materia sin configuración: '{materia}' (se usa la regla por defecto)")
        regla = regla_de(reglas_dict, materia)
        df_mat = df[df["materia"] == materia]
        tratamiento_recup = str(regla.get("tratamiento_recuperatorio", "")).strip().lower()
        evals_materia, clave_eval = _obtener_evaluaciones_base_materia(
            df_mat,
            incluir_recuperatorios=(tratamiento_recup in ("ninguno", "no_aplica", "ignorar")),
        )

        alumnos_con_nota = set(df_mat["id_alumno"].unique())
        alumnos_matriculados = set(
            pares_extra.loc[pares_extra["materia"] == materia, "id_alumno"].unique()
        )
        todos_alumnos = sorted(alumnos_con_nota | alumnos_matriculados)

        for id_alumno in todos_alumnos:
            df_grupo = df_mat[df_mat["id_alumno"] == id_alumno]
            resultado = calcular_resultado_estudiante(
                id_alumno=id_alumno,
                materia=materia,
                df_grupo=df_grupo,
                regla=regla,
                evals_materia=evals_materia,
                clave_eval=clave_eval,
            )
            resultados.append(resultado)

    columnas_resultado = [
        "id_alumno",
        "materia",
        "nota",
        "puntaje_tomado",
        "nota_normalizada",
        "condicion",
    ]
    return pd.DataFrame(resultados, columns=columnas_resultado), alertas