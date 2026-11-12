"""Carga automática de los datos del LMS (modelo v2 del TFI de BI).

QUÉ HACE, EN UNA LÍNEA
    Entran 26 planillas de Excel desprolijas del campus; salen 13 tablas limpias
    (CSV) que usan todos los dashboards, armadas como un modelo en estrella:
    4 tablas de hechos, 8 dimensiones y la tabla intermedia materia_aula.
    El diagrama y el diccionario de datos están en docs/DER.md.

EJEMPLO QUE SE SIGUE EN LOS COMENTARIOS
    En la planilla original del 1° Parcial de Álgebra, el alumno aparece así:

        Fecha de exportación: 24/10/2025      <- títulos que hay que saltear
        Calificación: 1° Parcial              <- de acá sale el nombre del examen
        ...
        Usuario    Apellido  Nombre   Nota
        ALU_1001   Gómez     Manuel   24.00/25.00

    y al abrirla con leer_tabla("calificaciones") termina así:

        id_alumno  materia  instrumento  nota  nota_maxima
        ALU_1001   algebra  1° Parcial   24    25

    (En el archivo data/processed/calificaciones.csv la materia y el examen
    figuran como claves, id_materia_aula e id_evaluacion: ver PASO 6.)

LOS 6 PASOS
    PASO 1. Abrir la carpeta y ver qué hay ............ descubrir()
    PASO 2. Saltear los títulos y encontrar la tabla .. leer_con_encabezado()
    PASO 3. Limpiar cada tipo de archivo .............. leer_trazabilidad(), leer_participacion(),
                                                        leer_calificaciones(), leer_matriculados()
    PASO 4. Armar la fila limpia ...................... (dentro de cada lector)
    PASO 5. Juntar todo y guardar ..................... cargar() y guardar()
    PASO 6. Pasar a modelo en estrella ................ armar_estrella()

CRITERIO: NO SE TIRA NADA
    Las columnas originales se conservan y las transformadas se agregan al lado
    (por ejemplo "10:07" queda en tiempo_estimado_de_uso y 607 en tiempo_uso_min).
    Tampoco se descartan tutores, coordinadores ni invitados: quedan con su
    perfil, y leer_tabla() los filtra por defecto.

POR QUÉ ES ESCALABLE
    El programa no sabe qué materias existen: lo descubre mirando la carpeta.
    Una carpeta nueva (por ejemplo "Química") se procesa sola, sin tocar el código.

Uso:
    python cargar_datos.py [carpeta_datos] [carpeta_salida]
    (por defecto las carpetas del archivo .env, o data/raw y data/processed)

Para usar las tablas desde un dashboard:
    from cargar_datos import leer_tabla
    interacciones = leer_tabla("interacciones")                      # solo alumnos
    con_docentes = leer_tabla("interacciones", solo_alumnos=False)   # todos los perfiles
    leer_tabla() ya trae pegadas las columnas de las dimensiones (materia, aula,
    perfil, sección, acción, examen...), así que no hace falta cruzar nada a mano.
"""
import html
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# =============================================================================
# CONFIGURACIÓN: lo único que habría que cambiar si el campus cambia sus nombres
# =============================================================================

# Los valores sueltos (carpetas y nombres del campus) se leen del archivo .env,
# que está al lado de este programa. Si el archivo no existe, o le falta una
# línea, se usa el valor por defecto que figura acá. Ver .env.example.
load_dotenv()

# Carpeta que NO es una materia: tiene el padrón oficial, un archivo por materia.
CARPETA_MATRICULADOS = os.getenv("CARPETA_MATRICULADOS", "matriculados").lower()

# Tabla de reconocimiento: "si el nombre del archivo empieza con esto, es de este tipo".
# Ejemplo: calificaciones_alumnos_20251024_114944.xlsx -> es un archivo de notas.
PREFIJOS = {
    "reporte_trazabilidad_": "trazabilidad",    # cada clic y cada acceso
    "reporte_participacion_": "participacion",  # resumen por alumno
    "calificaciones_alumnos_": "calificaciones",  # un archivo por examen
}

# Tipos de archivo que se leen como planilla.
EXTENSIONES = (".xlsx", ".xls", ".csv")

# En el campus hay alumnos, tutores, coordinadores e invitados. Se guardan todos,
# y este es el perfil que se marca con es_alumno = True.
PERFIL_ALUMNO = os.getenv("PERFIL_ALUMNO", "Alumnos")

# Estado del padrón que cuenta como inscripción vigente (el otro es "Baja").
ESTADO_INSCRIPCION_ACTIVA = os.getenv("ESTADO_INSCRIPCION_ACTIVA", "Aceptada")

# Carpetas por defecto (se pueden cambiar al correr el programa, ver el final del archivo).
CARPETA_DATOS = Path(os.getenv("CARPETA_DATOS", "data/raw"))
CARPETA_SALIDA = Path(os.getenv("CARPETA_SALIDA", "data/processed"))

# Columnas de sí o no que se agregan al reporte de participación, para poder
# contar "cuántos alumnos usaron tal canal". Se lee: la columna nueva es
# verdadera cuando esta columna del campus es mayor que cero.
CANALES_PARTICIPACION = {
    "tuvo_actividad": "interacciones",
    "envio_emails": "cantidad_de_emails_enviados",
    "participo_en_foros": "foros_cantidad_de_intervenciones_del_usuario",
}

# Nombres en castellano para la tabla de fechas (lunes = 0, enero = 1).
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Para clasificar cada examen según las palabras de su nombre.
# El orden importa: "Recuperatorio: Evaluación Semanal" tiene que caer en
# "recuperatorio" antes de que lo atrape "evaluacion semanal".
CATEGORIAS_EVALUACION = [
    ("recuperatorio", "recuperatorio"),
    ("parcial", "parcial"),
    ("autoevaluacion", "autoevaluacion"),
    ("evaluacion semanal", "evaluacion_semanal"),
    ("actividad", "actividad"),
]


# =============================================================================
# UTILIDADES: funciones chicas que usan los pasos de más abajo
# =============================================================================

def sin_tildes(texto):
    # "Estadística" -> "Estadistica"
    tabla = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return texto.translate(tabla)


def normalizar_id(serie):
    """El formato acordado: sin espacios y en mayúsculas (ALU_1001).

    Es lo que hace que los cruces funcionen: " alu_1001" y "ALU_1001" pasan a
    ser el mismo alumno en las cuatro fuentes.
    """
    return serie.astype("string").str.strip().str.upper()


def limpiar_nombre_instrumento(nombre):
    """Saca entidades HTML y emojis: '&#129504; PARCIAL 1' -> 'PARCIAL 1'.

    Probabilidad y Estadística pone emojis en el nombre de sus exámenes,
    y el campus los exporta como códigos raros.
    """
    nombre = html.unescape(nombre)  # convierte '&#129504;' en el emoji
    nombre = "".join(c for c in nombre if c.isalnum() or c in " .,:;-_()°º/")  # saca el emoji
    return re.sub(r"\s+", " ", nombre).strip()  # deja un solo espacio entre palabras


def categoria_evaluacion(nombre):
    # "1° Parcial" -> "parcial"; "AUTOEVALUACION1" -> "autoevaluacion"
    clave = sin_tildes(nombre).lower()
    for palabra, tipo in CATEGORIAS_EVALUACION:
        if palabra in clave:
            return tipo
    return "otro"


def a_snake(nombre):
    # "Probabilidad y Estadística" -> "probabilidad_y_estadistica"
    # Es el formato de las claves de reglas_materias.json de Joan.
    nombre = sin_tildes(nombre).lower()
    return re.sub(r"[^a-z0-9]+", "_", nombre).strip("_")


def hhmm_a_minutos(serie):
    """'10:07' -> 607. El LMS informa horas:minutos (hay valores como '31:26')."""
    # Separa lo de antes y lo de después de los dos puntos: ("10", "07")
    partes = serie.astype("string").str.extract(r"^\s*(\d+):(\d{2})\s*$")
    # 10 horas * 60 + 7 minutos = 607 minutos
    return pd.to_numeric(partes[0]) * 60 + pd.to_numeric(partes[1])


def texto(serie):
    # Pasa una columna a texto y le saca los espacios de las puntas.
    return serie.astype("string").str.strip()


def aula_del_filtro(meta):
    # "Aula: TUCD-MD-Álgebra 2025 | Fecha desde: ..." -> "TUCD-MD-Álgebra 2025"
    aula = re.search(r"Aula:\s*([^|]+)", meta.get("Filtro aplicado", ""))
    return aula.group(1).strip() if aula else None


def id_fecha(serie):
    # 2025-08-05 18:05:40 -> 20250805. Es la clave de la tabla fecha.
    return pd.to_numeric(serie.dt.strftime("%Y%m%d"), errors="coerce").astype("Int64")


# =============================================================================
# PASO 1. ABRIR LA CARPETA Y VER QUÉ HAY
# =============================================================================

def descubrir(carpeta):
    """Recorre data/raw y arma el inventario de archivos, sin saber de antemano
    qué materias hay.

    Devuelve tres cosas:
      materias:       {"Álgebra": {"calificaciones": [archivo1, archivo2, ...], ...}, ...}
      matriculados:   {"Álgebra": archivo del padrón, ...}
      no_reconocidos: archivos cuyo nombre no empieza con ningún prefijo conocido
    """
    materias, no_reconocidos = {}, []

    # Las subcarpetas de data/raw que son materias ("Álgebra", ...).
    # Matriculados no es una materia: se trata aparte, más abajo.
    carpetas_materia = [
        p for p in carpeta.iterdir() if p.is_dir() and p.name.lower() != CARPETA_MATRICULADOS
    ]

    for sub in sorted(carpetas_materia):
        # Una "caja" vacía por tipo de archivo: {"trazabilidad": [], "participacion": [], ...}
        archivos = {tipo: [] for tipo in PREFIJOS.values()}

        # Solo las planillas: deja afuera, por ejemplo, desktop.ini, y los "~$..."
        # que crea Excel mientras un archivo está abierto.
        planillas = [
            a for a in sub.iterdir()
            if a.suffix.lower() in EXTENSIONES and not a.name.startswith("~$")
        ]

        # Para cada planilla de esa materia, busca con qué prefijo empieza su nombre.
        for archivo in sorted(planillas):
            tipo = next((t for pre, t in PREFIJOS.items() if archivo.name.startswith(pre)), None)
            if tipo:
                archivos[tipo].append(archivo)  # lo guarda en la caja que corresponde
            else:
                no_reconocidos.append(archivo)  # lo anota para avisar en el reporte
        materias[sub.name] = archivos

    # El padrón: un archivo por materia, con el mismo nombre que la carpeta de la materia.
    # Ejemplo: Matriculados/Álgebra.xlsx corresponde a la carpeta Álgebra/
    carpeta_matric = next(
        (p for p in carpeta.iterdir() if p.is_dir() and p.name.lower() == CARPETA_MATRICULADOS), None
    )
    matriculados = {}
    if carpeta_matric:
        for archivo in sorted(carpeta_matric.iterdir()):
            if archivo.suffix.lower() in EXTENSIONES and not archivo.name.startswith("~$"):
                matriculados[archivo.stem] = archivo  # .stem es el nombre sin ".xlsx"
    return materias, matriculados, no_reconocidos


# =============================================================================
# PASO 2. SALTEAR LOS TÍTULOS Y ENCONTRAR LA TABLA
# =============================================================================

def leer_con_encabezado(ruta, columna_clave, filas_encabezado=1):
    """Lee un Excel del campus, que no empieza en la fila 1: arriba tiene títulos.

    En vez de suponer "la tabla empieza en la fila 7", busca la fila donde
    aparece una columna conocida (por ejemplo "Usuario"). Así funciona aunque
    otra materia tenga más o menos títulos arriba.

    Devuelve (tabla, metadatos). Los metadatos son lo que había arriba, por ejemplo
    {"Calificación": "1° Parcial", "Fecha de exportación": "24/10/2025 11:49"}.
    """
    # Lee la planilla entera tal cual, sin decirle dónde está el encabezado.
    crudo = pd.read_excel(ruta, header=None, dtype=object)

    # Revisa las primeras 20 filas y se queda con la primera que contiene "Usuario".
    # crudo.iloc[i] es "la fila número i". En el ejemplo, "Usuario" está en la fila 6.
    fila = next(
        (i for i in range(min(20, len(crudo)))
         if columna_clave in [str(v).strip() for v in crudo.iloc[i].values]),
        None,
    )
    if fila is None:
        raise ValueError(f"no se encontró la columna '{columna_clave}'")

    # Lo que está arriba del encabezado no se tira: se guarda como metadatos.
    # "Calificación: 1° Parcial" -> metadatos["Calificación"] = "1° Parcial"
    metadatos = {}
    for i in range(fila):
        valores = [str(v).strip() for v in crudo.iloc[i].values if pd.notna(v)]
        if len(valores) == 1 and ":" in valores[0]:
            # Formato "Clave: valor" en una sola celda
            clave, valor = valores[0].split(":", 1)
            metadatos[clave.strip()] = valor.strip()
        elif len(valores) >= 2:
            # Formato "Clave" | "valor" en dos celdas
            metadatos[valores[0]] = " | ".join(valores[1:])
        # Si la fila está vacía no entra en ninguno de los dos casos.

    if filas_encabezado == 1:
        columnas = [str(v).strip() for v in crudo.iloc[fila].values]
    else:
        # El reporte de participación tiene el encabezado en DOS filas:
        #     Encuestas |           | Archivos | ...
        #     Cantidad  | Cargados  | Cantidad | ...
        # Se unen como "Encuestas - Cantidad", "Encuestas - Cargados", ...
        columnas, grupo = [], ""
        for arriba, abajo in zip(crudo.iloc[fila].values, crudo.iloc[fila + 1].values):
            if pd.notna(arriba):
                grupo = str(arriba).strip()  # recuerda el último título de arriba
            columnas.append(f"{grupo} - {str(abajo).strip()}" if pd.notna(abajo) else grupo)

    # La tabla de verdad empieza debajo del encabezado.
    tabla = crudo.iloc[fila + filas_encabezado:].copy()
    tabla.columns = columnas
    tabla = tabla[tabla[columna_clave].notna()]  # saca filas vacías o de totales al final
    return tabla.reset_index(drop=True), metadatos


# =============================================================================
# PASOS 3 Y 4. LIMPIAR CADA TIPO DE ARCHIVO Y ARMAR LA FILA LIMPIA
# Un lector por tipo de archivo. Todos siguen el mismo patrón:
#   leer (PASO 2) -> armar columnas con nombres prolijos (PASO 4) -> limpiar (PASO 3)
#   -> anotar en el reporte qué se descartó
# =============================================================================

def leer_trazabilidad(ruta, materia, reporte):
    """Registro de actividad: una fila por cada clic o acceso, de cualquier perfil."""
    df, meta = leer_con_encabezado(ruta, "Usuario")

    # El aula viene en cada fila. Si alguna está vacía se usa la del título del archivo.
    aula = texto(df["Aula"]) if "Aula" in df.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    aula = aula.fillna(aula_del_filtro(meta) or "Sin aula")

    # PASO 4: columnas con nombres prolijos (los del campus tienen tildes y mayúsculas).
    df = pd.DataFrame({
        "id_alumno": normalizar_id(df["Usuario"]),
        "materia": materia,
        "aula": aula,
        "fecha_hora": pd.to_datetime(df["Fecha"], errors="coerce"),  # texto -> fecha
        "ip": df.get("IP Usuario"),
        "perfil": texto(df["Perfil"]),
        "apellido": texto(df["Apellido"]),  # después pasan a la tabla alumno
        "nombre": texto(df["Nombre"]),
        "seccion": texto(df["Sección"]),
        "accion": texto(df["Acción"]),
        "descripcion": texto(df["Descripción"]),
    })

    # PASO 3: limpieza, contando cuánto se descarta en cada etapa para el reporte.
    filas = len(df)
    fechas_invalidas = int(df["fecha_hora"].isna().sum())
    df = df[df["fecha_hora"].notna()]       # sin fecha no sirve para nada
    duplicados = int(df.duplicated().sum())
    df = df.drop_duplicates().copy()        # saca filas repetidas exactas

    # Docentes, tutores y coordinadores NO se descartan: quedan marcados.
    df["es_alumno"] = df["perfil"] == PERFIL_ALUMNO
    no_alumnos = int((~df["es_alumno"]).sum())

    # Columna para los reportes: la hora sola (0 a 23) arma el mapa de calor.
    df["hora"] = df["fecha_hora"].dt.hour

    reporte.append(
        f"  trazabilidad {ruta.name}: {filas} filas leídas, {duplicados} duplicados exactos descartados, "
        f"{fechas_invalidas} fechas inválidas, {len(df)} filas finales "
        f"({len(df) - no_alumnos} de alumnos y {no_alumnos} de otros perfiles, que se conservan)"
    )
    return df, meta


def leer_participacion(ruta, materia, reporte):
    """Resumen por usuario y aula: avance, interacciones, tiempo de uso, primer y último ingreso."""
    df, meta = leer_con_encabezado(ruta, "Usuario", filas_encabezado=2)

    # PASO 4: "Encuestas - Cantidad" -> "encuestas_cantidad"
    df.columns = [a_snake(c) for c in df.columns]
    df = df.rename(columns={"usuario": "id_alumno"})
    df["id_alumno"] = normalizar_id(df["id_alumno"])
    df.insert(1, "materia", materia)

    # PASO 3: no se saca ninguna columna ni ningún perfil. Las columnas de texto
    # se prolijan y las transformadas se agregan al lado de la original.
    filas = len(df)
    for col in ("apellido", "nombre", "email", "aula", "perfil"):
        df[col] = texto(df[col])
    df["aula"] = df["aula"].fillna(aula_del_filtro(meta) or "Sin aula")
    perfiles = df["perfil"].value_counts().to_dict()
    df["es_alumno"] = df["perfil"] == PERFIL_ALUMNO

    # Textos -> fechas ("05/08/2025" se lee como día/mes/año)
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"], format="%d/%m/%Y", errors="coerce")
    for col in ("primera_interaccion", "ultima_interaccion"):
        df[col] = pd.to_datetime(df[col], format="%d/%m/%Y %H:%M:%S", errors="coerce")

    # Todo lo que no es ID, texto o fecha se pasa a número
    no_numericas = ("id_alumno", "materia", "apellido", "nombre", "email", "aula", "perfil", "es_alumno",
                    "avance", "tiempo_estimado_de_uso",
                    "fecha_alta", "primera_interaccion", "ultima_interaccion")
    numericas = [c for c in df.columns if c not in no_numericas]
    df[numericas] = df[numericas].apply(pd.to_numeric, errors="coerce")

    # Columnas que se AGREGAN (las originales "avance" y "tiempo_estimado_de_uso" quedan):
    # "86" -> 86; "no aplica" -> vacío
    df["avance_pct"] = pd.to_numeric(df["avance"], errors="coerce")
    # "10:07" -> 607 minutos, y también 10.12 horas
    df["tiempo_uso_min"] = hhmm_a_minutos(df["tiempo_estimado_de_uso"])
    df["tiempo_uso_horas"] = (df["tiempo_uso_min"] / 60).round(2)
    # Una columna de sí o no por canal: envio_emails es verdadera si mandó al menos uno.
    for nueva, origen in CANALES_PARTICIPACION.items():
        if origen in df.columns:
            df[nueva] = df[origen].fillna(0) > 0

    duplicados = int(df.duplicated(["id_alumno", "aula"]).sum())
    df = df.drop_duplicates(["id_alumno", "aula"])  # un usuario, una fila por aula
    reporte.append(
        f"  participacion {ruta.name}: {filas} filas, perfiles {perfiles}, "
        f"{duplicados} usuarios repetidos, {len(df)} filas finales ({int(df['es_alumno'].sum())} alumnos)"
    )
    return df, meta


def leer_calificaciones(ruta, materia, reporte):
    """Un archivo por examen. Es el ejemplo de los comentarios de arriba:
    ALU_1001 | 24.00/25.00  ->  ALU_1001 | algebra | 1° Parcial | 24 | 25
    """
    df, meta = leer_con_encabezado(ruta, "Usuario")

    # El nombre del examen no está en la tabla: está en los títulos de arriba.
    # meta["Calificación"] = "1° Parcial"
    instrumento = limpiar_nombre_instrumento(meta.get("Calificación", ruta.stem))

    # PASO 3: separar "24.00/25.00" en dos números.
    # El patrón se lee: "números, una barra, números". Lo de cada lado queda por separado.
    nota = df["Nota"].astype("string").str.extract(r"^\s*([\d.,]+)\s*/\s*([\d.,]+)\s*$")
    puntaje = pd.to_numeric(nota[0].str.replace(",", "."), errors="coerce")  # "24.00" -> 24
    maximo = pd.to_numeric(nota[1].str.replace(",", "."), errors="coerce")   # "25.00" -> 25

    # PASO 4: la fila limpia.
    out = pd.DataFrame({
        "id_alumno": normalizar_id(df["Usuario"]),               # ALU_1001
        "materia": materia,                                      # algebra
        "aula": meta.get("Nombre del aula", "Sin aula"),         # TUCD-MD-Álgebra 2025
        "apellido": texto(df["Apellido"]),                       # después pasan a la tabla alumno
        "nombre": texto(df["Nombre"]),
        "instrumento": instrumento,                              # 1° Parcial
        "tipo_evaluacion": a_snake(instrumento),                 # 1_parcial
        "categoria_evaluacion": categoria_evaluacion(instrumento),  # parcial
        "nota": puntaje,                                         # 24
        "nota_maxima": maximo,                                   # 25
        "nota_pct": (puntaje / maximo * 100).round(2),           # 96: sirve para comparar materias
        "observacion": df["Observaciones"].astype("string").str.strip(),  # aprobada
        "archivo_origen": ruta.name,  # para poder volver a la planilla original
    })

    sin_nota = int(out["nota"].isna().sum())
    duplicados = int(out["id_alumno"].duplicated().sum())
    out = out.drop_duplicates("id_alumno")  # un alumno, una nota por examen
    reporte.append(
        f"  calificaciones {ruta.name}: '{instrumento}' ({categoria_evaluacion(instrumento)}), "
        f"{len(out)} notas, máximo {sorted(out['nota_maxima'].dropna().unique().tolist())}, "
        f"{sin_nota} sin nota numérica, {duplicados} repetidos"
    )
    return out


def leer_matriculados(ruta, materia, reporte):
    """Padrón oficial: quién está inscripto en la materia."""
    # El padrón usa "Identificación" en vez de "Usuario", pero es el mismo ALU_####.
    df, _ = leer_con_encabezado(ruta, "Identificación")

    # El padrón trae el nombre en una sola columna y en mayúsculas: "PÉREZ, FELIPE".
    # Se separa en la coma y se pasa a "Pérez" y "Felipe".
    partes = df["Alumno"].astype("string").str.split(",", n=1, expand=True)

    # PASO 4: la fila limpia.
    df = pd.DataFrame({
        "id_alumno": normalizar_id(df["Identificación"]),
        "materia": materia,
        "apellido": partes[0].str.strip().str.title(),
        "nombre": partes[1].str.strip().str.title(),
        "comision": texto(df["Comisión"]),
        "estado_inscripcion": texto(df["Estado Insc."]),  # Aceptada o Baja
        "instancia": texto(df["Instancia"]),
        "fecha_inscripcion": pd.to_datetime(df["Fecha inscripción"], format="%d/%m/%Y %H:%M:%S", errors="coerce"),
        "nro_transaccion": texto(df["Nro de Transacción"]) if "Nro de Transacción" in df.columns else pd.NA,
    })

    # PASO 3: un alumno puede tener varias inscripciones (se dio de baja y se volvió
    # a inscribir). Se conservan TODAS, ordenadas por fecha, y se marcan:
    #   es_ultima_inscripcion: la más reciente de ese alumno en la materia
    #   activo: la más reciente y además aceptada (o sea, hoy está inscripto)
    # Un alumno dado de baja, o una inscripción vieja, queda con activo = False.
    df = df.sort_values(["id_alumno", "fecha_inscripcion"]).reset_index(drop=True)
    df["registros_inscripcion"] = df.groupby("id_alumno")["id_alumno"].transform("size")
    df["es_ultima_inscripcion"] = ~df.duplicated("id_alumno", keep="last")
    df["activo"] = df["es_ultima_inscripcion"] & (df["estado_inscripcion"] == ESTADO_INSCRIPCION_ACTIVA)

    ultimas = df[df["es_ultima_inscripcion"]]
    reporte.append(
        f"  matriculados {ruta.name}: {len(df)} filas, {len(ultimas)} alumnos, "
        f"{len(df) - len(ultimas)} inscripciones anteriores conservadas, {int(df['activo'].sum())} activos, "
        f"estado de la última inscripción {ultimas['estado_inscripcion'].value_counts().to_dict()}"
    )
    return df


# =============================================================================
# PASO 5. JUNTAR TODO Y GUARDAR
# =============================================================================

def cargar(carpeta_datos):
    """Llama a los pasos 1 a 4 para cada materia y junta los resultados."""
    carpeta_datos = Path(carpeta_datos)

    # PASO 1: inventario de la carpeta.
    materias, matriculados, no_reconocidos = descubrir(carpeta_datos)

    reporte = [f"Carga de {carpeta_datos} ({datetime.now():%Y-%m-%d %H:%M})", ""]
    # Una lista vacía por tabla: acá se van acumulando los pedazos de cada materia.
    trazas, partics, califs, matrics, materias_encontradas, avisos = [], [], [], [], [], []

    # Para cada materia que encontró descubrir() ("Álgebra", "Probabilidad y Estadística", ...)
    for nombre, archivos in materias.items():
        materia = a_snake(nombre)  # "Álgebra" -> "algebra"
        reporte.append(f"[{nombre}] -> materia '{materia}'")
        fila_materia = {"materia": materia, "nombre": nombre}

        # Avisa si a una materia le falta algún tipo de archivo.
        for tipo in PREFIJOS.values():
            if not archivos[tipo]:
                avisos.append(f"{nombre}: no tiene archivos de {tipo}")

        # PASOS 2 a 4 para cada archivo, con el lector que corresponde a su tipo.
        for ruta in archivos["trazabilidad"]:
            df, meta = leer_trazabilidad(ruta, materia, reporte)
            trazas.append(df)
            fila_materia["fecha_exportacion"] = meta.get("Fecha de exportación")
        for ruta in archivos["participacion"]:
            df, meta = leer_participacion(ruta, materia, reporte)
            partics.append(df)
        for ruta in archivos["calificaciones"]:
            califs.append(leer_calificaciones(ruta, materia, reporte))  # uno por examen
        if nombre in matriculados:
            matrics.append(leer_matriculados(matriculados[nombre], materia, reporte))
        else:
            avisos.append(f"{nombre}: no tiene archivo en la carpeta de matriculados")

        materias_encontradas.append(fila_materia)
        reporte.append("")

    # Controles de la carpeta: padrones sin materia y archivos desconocidos.
    for nombre in matriculados:
        if nombre not in materias:
            avisos.append(f"matriculados/{nombre}: no hay carpeta de materia con ese nombre")
    for ruta in no_reconocidos:
        avisos.append(f"archivo no reconocido: {ruta.relative_to(carpeta_datos)}")

    # Pegar los pedazos de todas las materias uno debajo del otro (pd.concat).
    # Ejemplo: las notas de Álgebra + las de Algoritmos + las de Probabilidad = 1.793 filas.
    modelo = {
        "interacciones": pd.concat(trazas, ignore_index=True),
        "participacion": pd.concat(partics, ignore_index=True),
        "calificaciones": pd.concat(califs, ignore_index=True),
        "matricula": pd.concat(matrics, ignore_index=True),
    }

    # PASO 6: modelo en estrella (ver armar_estrella, más abajo).
    modelo = armar_estrella(modelo, pd.DataFrame(materias_encontradas), avisos)

    # Cierre del reporte: avisos y resumen de las tablas.
    reporte.append("AVISOS" if avisos else "Sin avisos.")
    reporte.extend(f"  - {a}" for a in avisos)
    reporte.append("")
    reporte.append("TABLAS")
    reporte.extend(f"  {n}: {len(t)} filas, columnas {list(t.columns)}" for n, t in modelo.items())
    return modelo, "\n".join(reporte)


# =============================================================================
# PASO 6. PASAR A MODELO EN ESTRELLA
# Hasta acá las tablas de hechos traen todo mezclado: lo que se mide (una nota,
# un clic) y lo que lo describe ("algebra", "TUCD-MD-Álgebra 2025", "Alumnos").
# En un modelo en estrella eso se separa:
#   - cada tabla de HECHOS queda en el centro, con claves y medidas;
#   - cada DIMENSIÓN (alumno, materia, aula, perfil, fecha, evento, evaluacion,
#     comision) es una tabla aparte con lo descriptivo, a un solo paso del hecho.
#     La excepción son materia y aula: se llega a ellas pasando por la tabla
#     intermedia materia_aula, porque su relación es de muchos a muchos.
# Las cuatro tablas de hechos comparten las mismas dimensiones.
# El diagrama está en docs/DER.md.
# =============================================================================

def numerar(tabla, columna_id):
    # Agrega adelante una clave 1, 2, 3... siguiendo el orden de las filas.
    tabla = tabla.reset_index(drop=True)
    tabla.insert(0, columna_id, range(1, len(tabla) + 1))
    return tabla


def dimension(hechos, columnas, columna_id):
    """Arma una dimensión con las combinaciones distintas de esas columnas.

    Ejemplo: de las 159.118 interacciones salen 95 pares (sección, acción)
    distintos, y cada uno recibe su id_evento.
    """
    return numerar(hechos[columnas].drop_duplicates().sort_values(columnas), columna_id)


def poner_clave(hechos, dim, columnas, columna_id):
    # Agrega a la tabla de hechos la clave de la dimensión, buscándola por sus columnas de texto.
    return hechos.merge(dim[columnas + [columna_id]], on=columnas, how="left")


def claves_adelante(tabla, sobran):
    # Saca las columnas que ya viven en una dimensión y deja las claves (id_...) primero.
    tabla = tabla.drop(columns=sobran)
    claves = [c for c in tabla.columns if c.startswith("id_")]
    return tabla[claves + [c for c in tabla.columns if c not in claves]]


# Las cuatro tablas de hechos: las que se cuentan y se promedian. El resto de
# las tablas son dimensiones (o la intermedia materia_aula).
TABLAS_DE_HECHOS = ("interacciones", "participacion", "calificaciones", "matricula")

# Clave primaria de cada tabla: la columna que identifica una fila y no se
# puede repetir. Todas las tablas tienen un número propio (id_...), salvo
# alumno, que usa el identificador del campus, y fecha, que usa el día.
CLAVES_PRIMARIAS = {
    "interacciones": ["id_interaccion"],
    "participacion": ["id_participacion"],
    "calificaciones": ["id_calificacion"],
    "matricula": ["id_matricula"],
    "alumno": ["id_alumno"],
    "materia": ["id_materia"],
    "aula": ["id_aula"],
    "materia_aula": ["id_materia_aula"],
    "perfil": ["id_perfil"],
    "evento": ["id_evento"],
    "evaluacion": ["id_evaluacion"],
    "comision": ["id_comision"],
    "fecha": ["id_fecha"],
}

# Combinaciones que tampoco se pueden repetir, aunque no sean la clave primaria.
# El número propio no alcanza para evitar duplicados: dos filas del mismo alumno
# en el mismo examen tendrían distinto id_calificacion y pasarían inadvertidas.
# Las interacciones no figuran: ahí ninguna combinación identifica un clic.
COMBINACIONES_UNICAS = {
    "participacion": ["id_alumno", "id_materia_aula"],   # un usuario, una fila por materia y aula
    "calificaciones": ["id_alumno", "id_evaluacion"],    # un alumno, una nota por examen
    "matricula": ["nro_transaccion"],                    # el número que el campus le pone a cada inscripción
    "materia_aula": ["id_materia", "id_aula"],           # una fila por combinación
}


def armar_estrella(modelo, materia, avisos):
    """Recibe las 4 tablas de hechos con textos y devuelve el modelo en estrella."""
    traza, partic = modelo["interacciones"], modelo["participacion"]
    califs, matric = modelo["calificaciones"], modelo["matricula"]

    # --- materia: una fila por materia, con su rango de fechas de actividad.
    # El rango sirve para saber entre qué fechas se puede mover la fecha de corte.
    # Se mide solo con la actividad de alumnos: los docentes entran al aula
    # semanas antes de que empiece la cursada y correrían el inicio.
    de_alumnos = traza[traza["es_alumno"]]
    rango = de_alumnos.groupby("materia")["fecha_hora"].agg(fecha_min="min", fecha_max="max").reset_index()
    materia = numerar(materia.merge(rango, on="materia", how="left").sort_values("materia"), "id_materia")

    # --- aula: una fila por aula del campus. El año sale del final del nombre.
    pares = pd.concat([t[["materia", "aula"]] for t in (traza, partic, califs)]).drop_duplicates()
    aula = dimension(pares, ["aula"], "id_aula")
    aula["anio"] = pd.to_numeric(aula["aula"].str.extract(r"(20\d{2})\s*$")[0]).astype("Int64")

    # A cada hecho se le busca la clave de su materia y la de su aula. Son un paso
    # intermedio: más abajo se cambian por una sola clave, id_materia_aula.
    traza =poner_clave(poner_clave(traza, materia, ["materia"], "id_materia"), aula, ["aula"], "id_aula")
    partic = poner_clave(poner_clave(partic, materia, ["materia"], "id_materia"), aula, ["aula"], "id_aula")
    califs = poner_clave(poner_clave(califs, materia, ["materia"], "id_materia"), aula, ["aula"], "id_aula")
    # El padrón no dice en qué aula cursa el alumno: solo se relaciona con la materia.
    matric = poner_clave(matric, materia, ["materia"], "id_materia")

    # --- materia_aula: la tabla intermedia entre materia y aula. La relación es de
    # muchos a muchos: una materia puede tener varias aulas (una por comisión o por
    # año) y un aula puede compartirse entre materias. Tiene una fila por cada
    # combinación que aparece en los datos; hoy cada materia tiene un aula sola.
    # Cada combinación tiene su propia clave, id_materia_aula, y dos claves
    # foráneas: una a materia y otra a aula.
    materia_aula = poner_clave(poner_clave(pares, materia, ["materia"], "id_materia"), aula, ["aula"], "id_aula")
    materia_aula = numerar(materia_aula[["id_materia", "id_aula"]].sort_values(["id_materia", "id_aula"]), "id_materia_aula")

    # --- perfil: Alumnos, Tutores, Coordinadores, Invitados.
    perfil = dimension(pd.concat([traza[["perfil"]], partic[["perfil"]]]).dropna(), ["perfil"], "id_perfil")
    perfil["es_alumno"] = perfil["perfil"] == PERFIL_ALUMNO
    traza = poner_clave(traza, perfil, ["perfil"], "id_perfil")
    partic = poner_clave(partic, perfil, ["perfil"], "id_perfil")
    # Las notas no traen perfil: se toma el que tiene ese usuario en esa aula.
    # Quien tiene nota sin figurar en el aula se cuenta como alumno.
    perfil_en_aula = partic[["id_alumno", "id_materia", "id_aula", "id_perfil"]]
    califs = califs.merge(perfil_en_aula, on=["id_alumno", "id_materia", "id_aula"], how="left")
    clave_alumnos = perfil.loc[perfil["es_alumno"], "id_perfil"]
    if len(clave_alumnos):
        califs["id_perfil"] = califs["id_perfil"].fillna(clave_alumnos.iloc[0])
    califs["id_perfil"] = califs["id_perfil"].astype("Int64")

    # --- evento: qué se hizo y dónde ("Acceder" en "Inicio", "Ver tópico" en "Presentación").
    # Es la dimensión para contar interacciones por tipo. La tabla de equivalencias
    # de eventos (acción -> categoría) se puede agregar acá como una columna más.
    evento = dimension(traza, ["seccion", "accion"], "id_evento")
    traza = poner_clave(traza, evento, ["seccion", "accion"], "id_evento")

    # --- evaluacion: un examen de una materia, con su tipo y su categoría.
    # Es la dimensión para comparar instrumentos (parciales contra autoevaluaciones).
    columnas_examen = ["materia", "instrumento", "tipo_evaluacion", "categoria_evaluacion", "archivo_origen"]
    evaluacion = dimension(califs, columnas_examen, "id_evaluacion")
    califs = poner_clave(califs, evaluacion, columnas_examen, "id_evaluacion")

    # --- comision: las comisiones del padrón. Lleva el nombre de la materia porque
    # el mismo número de comisión podría repetirse en otra.
    comision = dimension(matric.dropna(subset=["comision"]), ["materia", "comision"], "id_comision")
    matric = poner_clave(matric, comision, ["materia", "comision"], "id_comision")

    # --- fecha: un día por fila, desde la primera fecha de los datos hasta la
    # última. Permite agrupar por semana, mes o día de la semana sin recalcular.
    traza["id_fecha"] = id_fecha(traza["fecha_hora"])
    partic["id_fecha_alta"] = id_fecha(partic["fecha_alta"])
    matric["id_fecha_inscripcion"] = id_fecha(matric["fecha_inscripcion"])
    fechas = pd.concat([
        traza["fecha_hora"], matric["fecha_inscripcion"], partic["fecha_alta"],
        partic["primera_interaccion"], partic["ultima_interaccion"],
    ]).dropna().dt.normalize()
    dias = pd.date_range(fechas.min(), fechas.max(), freq="D")
    fecha = pd.DataFrame({
        "id_fecha": dias.strftime("%Y%m%d").astype(int),
        "fecha": dias.date,
        "anio": dias.year,
        "mes": dias.month,
        "nombre_mes": [MESES[m - 1] for m in dias.month],
        "semana": dias.isocalendar().week.to_numpy(),      # semana del año (norma ISO)
        "dia": dias.day,
        "dia_semana": dias.dayofweek + 1,                  # lunes = 1 ... domingo = 7
        "nombre_dia": [DIAS[d] for d in dias.dayofweek],
        "es_fin_de_semana": dias.dayofweek >= 5,
    })

    # --- alumno: todos los IDs que aparecen en alguna fuente, sin repetir.
    # Apellido y nombre salen de la primera fuente que los tenga, en este orden:
    # participación ("Gómez", "Manuel"), trazabilidad, notas y, por último, el padrón.
    # El email solo figura en el reporte de participación.
    columnas_nombre = ["id_alumno", "apellido", "nombre"]
    nombres = pd.concat(
        [t[columnas_nombre] for t in (partic, traza, califs, matric)], ignore_index=True
    ).dropna(subset=["id_alumno"]).drop_duplicates("id_alumno")
    emails = partic[["id_alumno", "email"]].sort_values("email").drop_duplicates("id_alumno")
    alumno = nombres.sort_values("id_alumno").merge(emails, on="id_alumno", how="left")
    # Es alumno quien tiene ese perfil en algún aula, o quien no figura en ninguna
    # (aparece solo en las notas o en el padrón, que son fuentes de alumnos).
    en_aula = partic.groupby("id_alumno")["es_alumno"].any()
    alumno["es_alumno"] = alumno["id_alumno"].map(en_aula).astype("boolean").fillna(True).astype(bool)
    alumno = alumno.reset_index(drop=True)

    # Controles: nombres faltantes y formato del ID de los alumnos (ALU_####).
    sin_nombre = int(alumno["apellido"].isna().sum())
    if sin_nombre:
        avisos.append(f"{sin_nombre} usuarios sin apellido ni nombre en ninguna fuente")
    ids_alumnos = alumno.loc[alumno["es_alumno"], "id_alumno"]
    raros = [i for i in ids_alumnos if not re.fullmatch(r"ALU_\d+", i)]
    if raros:
        avisos.append(f"IDs de alumnos con formato distinto de ALU_####: {raros[:10]}")

    # Lo descriptivo ya vive en las dimensiones: se saca de los hechos para no
    # repetirlo. No se pierde nada, y leer_tabla() lo vuelve a pegar al abrir.
    persona = ["apellido", "nombre"]

    # Los hechos que ocurren en un aula apuntan a la tabla intermedia con una sola
    # clave foránea, id_materia_aula, en lugar de llevar id_materia e id_aula por
    # separado. Desde materia_aula se llega a la materia y al aula.
    par = ["id_materia", "id_aula"]
    traza = poner_clave(traza, materia_aula, par, "id_materia_aula").drop(columns=par)
    partic = poner_clave(partic, materia_aula, par, "id_materia_aula").drop(columns=par)
    califs = poner_clave(califs, materia_aula, par, "id_materia_aula").drop(columns=par)

    # Una interacción no tiene clave natural: el mismo alumno puede hacer dos veces
    # lo mismo en el mismo segundo (pasa 151 veces en estos datos, con distinta
    # descripción). Por eso recibe un número propio, id_interaccion.
    traza = numerar(traza, "id_interaccion")
    # Las otras tres tablas de hechos también reciben el suyo, para que todas
    # tengan la misma forma. Lo que no se puede repetir en cada una se sigue
    # controlando más abajo con COMBINACIONES_UNICAS.
    partic = numerar(partic, "id_participacion")
    califs = numerar(califs, "id_calificacion")
    matric = numerar(matric, "id_matricula")

    estrella = {
        "interacciones": claves_adelante(
            traza, persona + ["materia", "aula", "perfil", "es_alumno", "seccion", "accion"]),
        "participacion": claves_adelante(
            partic, persona + ["email", "materia", "aula", "perfil", "es_alumno"]),
        "calificaciones": claves_adelante(califs, persona + ["aula"] + columnas_examen),
        "matricula": claves_adelante(matric, persona + ["materia", "comision"]),
        "alumno": alumno,
        "materia": materia,
        "aula": aula,
        "materia_aula": materia_aula,
        "perfil": perfil,
        "evento": evento,
        "evaluacion": evaluacion,
        "comision": comision,
        "fecha": fecha,
    }

    # Control: ninguna clave primaria ni combinación única puede estar vacía o repetida.
    for grupo in (CLAVES_PRIMARIAS, COMBINACIONES_UNICAS):
        for nombre, clave in grupo.items():
            tabla = estrella[nombre]
            repetidas = int(tabla.duplicated(clave).sum())
            vacias = int(tabla[clave].isna().any(axis=1).sum())
            if repetidas or vacias:
                avisos.append(f"{nombre}: {clave} tiene {repetidas} filas repetidas y {vacias} vacías")
    return estrella


def guardar(modelo, reporte, carpeta_salida):
    """Escribe cada tabla como CSV en data/processed, más el reporte de la carga."""
    carpeta_salida = Path(carpeta_salida)
    carpeta_salida.mkdir(parents=True, exist_ok=True)  # crea la carpeta si no existe
    for nombre, tabla in modelo.items():
        # utf-8-sig: para que Excel muestre bien las tildes si alguien abre el CSV
        tabla.to_csv(carpeta_salida / f"{nombre}.csv", index=False, encoding="utf-8-sig")
    (carpeta_salida / "reporte_carga.txt").write_text(reporte, encoding="utf-8")


# Con qué dimensión se cruza cada clave de una tabla de hechos.
# El orden importa: si una columna está en dos dimensiones (es_alumno está en
# perfil y en alumno) vale la primera, o sea el perfil que tiene en ESA aula.
DIMENSIONES = {
    "id_materia_aula": "materia_aula",  # trae id_materia e id_aula, que se cruzan en los dos renglones siguientes
    "id_materia": "materia",
    "id_aula": "aula",
    "id_perfil": "perfil",
    "id_alumno": "alumno",
    "id_evento": "evento",
    "id_evaluacion": "evaluacion",
    "id_comision": "comision",
    "id_fecha": "fecha",              # día de la interacción
    "id_fecha_alta": "fecha",         # día del alta en el aula
    "id_fecha_inscripcion": "fecha",  # día de la inscripción
}


def leer_tabla(nombre, carpeta=None, solo_alumnos=True, con_dimensiones=True):
    """Abre una tabla ya procesada. Es la puerta de entrada para los dashboards.

    Si es una tabla de hechos, le pega las columnas de sus dimensiones: así
    leer_tabla("calificaciones") trae materia, instrumento, tipo_evaluacion,
    apellido, etc., lista para graficar. Con con_dimensiones=False devuelve la
    tabla tal como está en el CSV (claves y medidas).

    Por defecto devuelve solo las filas de alumnos. Con solo_alumnos=False
    devuelve también las de tutores, coordinadores e invitados.
    """
    carpeta = Path(carpeta or CARPETA_SALIDA)
    tabla = pd.read_csv(carpeta / f"{nombre}.csv")
    propias = list(tabla.columns)

    if nombre in TABLAS_DE_HECHOS:
        for clave, dim in DIMENSIONES.items():
            if clave in tabla.columns:
                d = pd.read_csv(carpeta / f"{dim}.csv")
                clave_dim = d.columns[0]  # la clave de una dimensión es su primera columna
                nuevas = [c for c in d.columns if c not in tabla.columns and c != clave_dim]
                tabla = tabla.merge(d[[clave_dim] + nuevas], left_on=clave, right_on=clave_dim, how="left")
                if clave_dim != clave:
                    tabla = tabla.drop(columns=clave_dim)

    if solo_alumnos and "es_alumno" in tabla.columns:
        tabla = tabla[tabla["es_alumno"].fillna(True).astype(bool)].reset_index(drop=True)
    return tabla if con_dimensiones else tabla[propias]


# =============================================================================
# ARRANQUE: lo que corre al escribir "python cargar_datos.py"
# =============================================================================

if __name__ == "__main__":
    # sys.argv es lo que se escribió en la terminal, separado en una lista:
    #   python cargar_datos.py                    -> ["cargar_datos.py"]
    #   python cargar_datos.py otra_carpeta sal   -> ["cargar_datos.py", "otra_carpeta", "sal"]
    # Si se pasaron carpetas se usan esas; si no, las del archivo .env (o data/raw y data/processed).
    datos = sys.argv[1] if len(sys.argv) > 1 else CARPETA_DATOS
    salida = sys.argv[2] if len(sys.argv) > 2 else CARPETA_SALIDA

    modelo, reporte = cargar(datos)    # PASOS 1 a 5
    guardar(modelo, reporte, salida)   # escribir los CSV
    print(reporte)                     # mostrar el reporte en la terminal
