"""Fecha de corte: lo que comparten todos los dashboards.

QUÉ HAY ACÁ
    cargar_tablas()        abre las tablas que deja cargar_datos.py, una sola vez
    filtros_corte()        dibuja en la barra lateral los tres filtros comunes:
                           materia, fecha de corte y días de inactividad
    situacion_alumnos()    calcula, para cada alumno y materia, cómo estaba a la
                           fecha de corte (inscripto o no, activo o inactivo)
    color_por_materia()    asigna un color fijo a cada materia

POR QUÉ ESTÁ APARTE
    Para que todos los dashboards muestren lo mismo: el mismo alumno tiene que
    figurar activo (o inactivo) a la misma fecha en cualquier pantalla. Si cada
    dashboard hiciera su propia cuenta, los números podrían no coincidir.

LA FECHA DE CORTE
    Todo se calcula "a una fecha". Se miran solo las inscripciones y los clics
    hasta ese día, así se puede ver cómo estaba la cursada en un momento pasado.
    La excepción son las notas: el campus no informa la fecha de cada examen,
    así que las notas siempre son las de la fecha de exportación.

CÓMO SE USA DESDE UN DASHBOARD
    from corte import cargar_tablas, filtros_corte, situacion_alumnos

    tablas = cargar_tablas()
    materia_sel, fecha_corte, dias = filtros_corte(tablas)
    situacion = situacion_alumnos(tablas, fecha_corte, dias)
"""
import pandas as pd
import streamlit as st

from cargar_datos import ESTADO_INSCRIPCION_ACTIVA, leer_tabla

# Días sin entrar al aula a partir de los cuales un alumno cuenta como inactivo.
# La cursada es semanal: 14 días equivalen a perderse dos clases seguidas.
DIAS_INACTIVIDAD = 14

# Colores de los tres estados de actividad. El verde, el amarillo y el rojo
# quedan reservados para el semáforo de condición final.
COLORES_ACTIVIDAD = {
    "Activo": "#1f77b4",
    "Inactivo": "#7fb3d5",
    "Nunca ingresó": "#7f7f7f",
}


@st.cache_data
def cargar_tablas():
    """Abre las tablas una sola vez y las deja en memoria (st.cache_data)."""
    tablas = {
        "matricula": leer_tabla("matricula"),
        "participacion": leer_tabla("participacion"),
        "interacciones": leer_tabla("interacciones"),
        "calificaciones": leer_tabla("calificaciones"),
        "alumno": leer_tabla("alumno"),
        "materia": leer_tabla("materia"),
    }
    # Los CSV traen las fechas como texto: se pasan a fecha para poder compararlas.
    tablas["matricula"]["fecha_inscripcion"] = pd.to_datetime(tablas["matricula"]["fecha_inscripcion"])
    tablas["participacion"]["fecha_alta"] = pd.to_datetime(tablas["participacion"]["fecha_alta"])
    tablas["interacciones"]["fecha_hora"] = pd.to_datetime(tablas["interacciones"]["fecha_hora"])
    for col in ("fecha_min", "fecha_max"):
        tablas["materia"][col] = pd.to_datetime(tablas["materia"][col])
    return tablas


def filtros_corte(tablas):
    """Dibuja los filtros comunes en la barra lateral y devuelve lo elegido.

    Los tres llevan una clave (key) fija: así la materia y la fecha elegidas se
    mantienen al pasar de un dashboard a otro.
    """
    materias = tablas["materia"]
    st.sidebar.header("Filtros")
    materia_sel = st.sidebar.selectbox(
        "Materia", ["Todas"] + sorted(materias["nombre_materia"]), key="filtro_materia"
    )

    # La fecha de corte se mueve entre el primer y el último día con actividad.
    primer_dia, ultimo_dia = materias["fecha_min"].min().date(), materias["fecha_max"].max().date()
    fecha_corte = st.sidebar.date_input(
        "Fecha de corte", value=ultimo_dia, min_value=primer_dia, max_value=ultimo_dia,
        format="DD/MM/YYYY", key="filtro_fecha_corte",
    )
    dias = st.sidebar.select_slider(
        "Días sin ingresar para contar como inactivo", options=[7, 14, 21],
        value=DIAS_INACTIVIDAD, key="filtro_dias_inactividad",
    )
    return materia_sel, fecha_corte, dias


def limite_del_corte(fecha_corte):
    # El corte incluye el día entero: "24/10" quiere decir hasta las 23:59 del 24/10.
    return pd.Timestamp(fecha_corte).normalize() + pd.Timedelta(days=1)


def situacion_alumnos(tablas, fecha_corte, dias_inactividad=DIAS_INACTIVIDAD):
    """Devuelve una fila por alumno y materia con su situación a la fecha de corte.

    Ejemplo de una fila:
        ALU_1001 | algebra | Inscripto | Activo | Inscripto activo | 3 días sin entrar
    """
    limite = limite_del_corte(fecha_corte)
    clave = ["id_alumno", "materia"]

    # --- 1. Quiénes estaban en el aula a esa fecha (alta anterior al corte).
    partic = tablas["participacion"]
    en_aula = partic.loc[partic["fecha_alta"] < limite, clave].drop_duplicates()
    en_aula["en_aula"] = True

    # --- 2. Cómo estaba la inscripción de cada uno a esa fecha: de todas las
    # inscripciones anteriores al corte, vale la más reciente.
    matric = tablas["matricula"]
    matric = matric[matric["fecha_inscripcion"] < limite].sort_values("fecha_inscripcion")
    ultima = matric.drop_duplicates(clave, keep="last")
    inscripcion = ultima[clave + ["estado_inscripcion", "fecha_inscripcion", "comision"]].copy()
    inscripcion["inscripcion"] = inscripcion.pop("estado_inscripcion").map(
        lambda estado: "Inscripto" if estado == ESTADO_INSCRIPCION_ACTIVA else "Baja"
    )

    # --- 3. Actividad hasta esa fecha: cantidad de clics y último ingreso.
    traza = tablas["interacciones"]
    traza = traza[traza["fecha_hora"] < limite]
    actividad = traza.groupby(clave)["fecha_hora"].agg(interacciones="size", ultima_actividad="max").reset_index()

    # --- 4. Quiénes tienen al menos una nota (sin fecha: ver el comentario de arriba).
    con_nota = tablas["calificaciones"][clave].drop_duplicates()
    con_nota["tiene_nota"] = True

    # --- 5. Se junta todo. how="outer" conserva a quien figura en una sola fuente:
    # el que está en el aula sin inscripción, y el inscripto que no está en el aula.
    df = en_aula.merge(inscripcion, on=clave, how="outer")
    df = df.merge(actividad, on=clave, how="left").merge(con_nota, on=clave, how="left")
    df["en_aula"] = df["en_aula"].eq(True)
    df["tiene_nota"] = df["tiene_nota"].eq(True)
    df["inscripcion"] = df["inscripcion"].fillna("Sin inscripción")
    df["interacciones"] = df["interacciones"].fillna(0).astype(int)

    # --- 6. Estado de actividad: activo, inactivo o nunca ingresó.
    df["dias_sin_actividad"] = (limite - df["ultima_actividad"]).dt.days
    df["actividad"] = "Nunca ingresó"
    df.loc[df["interacciones"] > 0, "actividad"] = "Inactivo"
    df.loc[df["dias_sin_actividad"] <= dias_inactividad, "actividad"] = "Activo"

    # --- 7. La situación combina inscripción y actividad.
    inscripto = df["inscripcion"] == "Inscripto"
    con_actividad = df["interacciones"] > 0
    df["situacion"] = "En el aula, sin inscripción ni actividad"
    df.loc[~inscripto & con_actividad, "situacion"] = "Con actividad sin inscripción"
    df.loc[inscripto & (df["actividad"] == "Nunca ingresó"), "situacion"] = "Inscripto sin actividad"
    df.loc[inscripto & (df["actividad"] == "Inactivo"), "situacion"] = "Inscripto inactivo"
    df.loc[inscripto & (df["actividad"] == "Activo"), "situacion"] = "Inscripto activo"

    # --- 8. Las alertas, cada una en su columna de sí o no.
    df["alerta_actividad_sin_inscripcion"] = ~inscripto & con_actividad
    df["alerta_nota_sin_inscripcion"] = ~inscripto & df["tiene_nota"]
    df["alerta_inscripto_sin_actividad"] = inscripto & ~con_actividad
    df["alerta_inscripto_inactivo"] = inscripto & (df["actividad"] == "Inactivo")

    # --- 9. Nombre del alumno y de la materia, para mostrar.
    df = df.merge(tablas["alumno"][["id_alumno", "apellido", "nombre"]], on="id_alumno", how="left")
    df = df.merge(tablas["materia"][["materia", "nombre_materia"]], on="materia", how="left")
    return df.sort_values(["nombre_materia", "apellido", "nombre"]).reset_index(drop=True)


def color_por_materia(tablas):
    """Devuelve {"Álgebra": "#...", ...}: un color fijo para cada materia.

    Los colores se reparten por orden alfabético de TODAS las materias, no solo
    de las que se están mostrando: así cada materia conserva su color aunque se
    filtre, y una materia nueva recibe el siguiente color sin tocar el código.
    """
    # Violeta, naranja, celeste, rosa, marrón y gris azulado. No hay verde,
    # amarillo ni rojo: esos tres son del semáforo de condición final.
    paleta = ["#7b4ea3", "#e67e22", "#17becf", "#e377c2", "#8c564b", "#5d6d7e"]
    nombres = sorted(tablas["materia"]["nombre_materia"])
    return {nombre: paleta[i % len(paleta)] for i, nombre in enumerate(nombres)}
