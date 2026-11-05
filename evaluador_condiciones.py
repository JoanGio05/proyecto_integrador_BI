import json
import pandas as pd

# ✅ Carga las reglas de evaluación desde un archivo JSON
def cargar_reglas_json(ruta_archivo="reglas_materias.json"):
    with open(ruta_archivo, "r", encoding="utf-8") as f:
        reglas = json.load(f)
        
    return reglas

# ✅ Devuelve la condicion academica segun la nota
def determinar_condicion(nota, umbral_regular, umbral_promocion):
    if nota >= umbral_promocion:
        return "promociona"
    elif nota >= umbral_regular:
        return "regular"
    else:
        return "libre"
    
# ✅ Reemplaza la menor nota del parcial si el recuperatorio es mayor
def procesar_recuperatorios(df_grupo, regla):
    df = df_grupo.copy()

    if regla.get("tratamiento_recuperatorio") != "reemplaza_menor_parcial":
        return df

    tipos = df["tipo_evaluacion"].astype(str).str.lower()
    es_recuperatorio = tipos == "recuperatorio"
    es_parcial = tipos.str.contains("parcial", na=False)

    if es_recuperatorio.any():
        notas_recuperatorio = df.loc[es_recuperatorio, "nota"].dropna()
        notas_parcial = df.loc[es_parcial, "nota"].dropna()

        if not notas_recuperatorio.empty and not notas_parcial.empty:
            nota_recuperatorio = notas_recuperatorio.max()
            id_menor_parcial = notas_parcial.idxmin()

            if nota_recuperatorio > df.loc[id_menor_parcial, "nota"]:
                df.loc[id_menor_parcial, "nota"] = nota_recuperatorio

        df = df.loc[~es_recuperatorio].copy()

    return df

# Calcula las notas y condición para un alumno en una materia.
def calcular_resultado_estudiante(id_alumno, materia, df_grupo, regla):
    """Calcula la nota final, su porcentaje y la condición de un alumno."""
    df = df_grupo.copy()
    df["nota"] = pd.to_numeric(df["nota"], errors="coerce")

    if regla.get("tratamiento_ausentes") == "cero":
        df["nota"] = df["nota"].fillna(0)

    df = procesar_recuperatorios(df, regla)

    metodo = regla.get("metodo_calculo", "promedio")
    if metodo == "suma":
        nota_final = df["nota"].sum()
    elif metodo == "promedio":
        nota_final = df["nota"].mean()
    else:
        raise ValueError(
            f"Método de cálculo no válido para '{materia}': '{metodo}'. "
            "Usá 'suma' o 'promedio'."
        )

    if pd.isna(nota_final):
        nota_final = 0.0

    puntaje_maximo = regla.get("puntaje_maximo", 100.0)
    if puntaje_maximo > 0:
        nota_normalizada = round(nota_final / puntaje_maximo * 100, 2)
    else:
        nota_normalizada = 0.0

    condicion = determinar_condicion(
        nota_final,
        regla.get("umbral_regular", 60.0),
        regla.get("umbral_promocion", 85.0),
    )

    return {
        "id_alumno": id_alumno,
        "materia": materia,
        "nota": round(nota_final, 2),
        "nota_normalizada": nota_normalizada,
        "condicion": condicion,
    }

# Función principal que coordina el cálculo para todos los estudiantes.
def calcular_condiciones_estudiantes(df_calificaciones, reglas_dict):
    """Calcula los resultados de todos los alumnos y devuelve las alertas."""
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

    resultados = []
    alertas = []

    for (id_alumno, materia), df_grupo in df.groupby(
        ["id_alumno", "materia"]
    ):
        if materia not in reglas_dict:
            alertas.append(
                f"Materia sin configuración: '{materia}' (Alumno ID: {id_alumno})"
            )
            continue

        resultado = calcular_resultado_estudiante(
            id_alumno, materia, df_grupo, reglas_dict[materia]
        )
        resultados.append(resultado)

    columnas_resultado = [
        "id_alumno",
        "materia",
        "nota",
        "nota_normalizada",
        "condicion",
    ]
    return pd.DataFrame(resultados, columns=columnas_resultado), alertas