"""Carga automática de los datos del LMS (modelo v1 del TFI de BI).

QUÉ HACE, EN UNA LÍNEA
    Entran 26 planillas de Excel desprolijas del campus; salen 6 tablas limpias
    (CSV) que usan todos los dashboards.

EJEMPLO QUE SE SIGUE EN LOS COMENTARIOS
    En la planilla original del 1° Parcial de Álgebra, el alumno aparece así:

        Fecha de exportación: 24/10/2025      <- títulos que hay que saltear
        Calificación: 1° Parcial              <- de acá sale el nombre del examen
        ...
        Usuario    Apellido  Nombre   Nota
        ALU_1001   Gómez     Manuel   24.00/25.00

    y en data/processed/hechos_calificaciones.csv termina así:

        id_alumno  materia  instrumento  nota  nota_maxima
        ALU_1001   algebra  1° Parcial   24    25

LOS 5 PASOS
    PASO 1. Abrir la carpeta y ver qué hay ............ descubrir()
    PASO 2. Saltear los títulos y encontrar la tabla .. leer_con_encabezado()
    PASO 3. Limpiar cada tipo de archivo .............. leer_trazabilidad(), leer_participacion(),
                                                        leer_calificaciones(), leer_matriculados()
    PASO 4. Armar la fila limpia ...................... (dentro de cada lector)
    PASO 5. Juntar todo y guardar ..................... cargar() y guardar()

POR QUÉ ES ESCALABLE
    El programa no sabe qué materias existen: lo descubre mirando la carpeta.
    Una carpeta nueva (por ejemplo "Química") se procesa sola, sin tocar el código.

Uso:
    python cargar_datos.py [carpeta_datos] [carpeta_salida]
    (por defecto data/raw y data/processed)
"""
import html
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# =============================================================================
# CONFIGURACIÓN: lo único que habría que cambiar si el campus cambia sus nombres
# =============================================================================

# Carpeta que NO es una materia: tiene el padrón oficial, un archivo por materia.
CARPETA_MATRICULADOS = "matriculados"

# Tabla de reconocimiento: "si el nombre del archivo empieza con esto, es de este tipo".
# Ejemplo: calificaciones_alumnos_20251024_114944.xlsx -> es un archivo de notas.
PREFIJOS = {
    "reporte_trazabilidad_": "trazabilidad",    # cada clic y cada acceso
    "reporte_participacion_": "participacion",  # resumen por alumno
    "calificaciones_alumnos_": "calificaciones",  # un archivo por examen
}

# Tipos de archivo que se leen como planilla.
EXTENSIONES = (".xlsx", ".xls", ".csv")

# En el campus hay alumnos, tutores, coordinadores e invitados: solo nos quedamos con alumnos.
PERFIL_ALUMNO = "Alumnos"

# Carpetas por defecto (se pueden cambiar al correr el programa, ver el final del archivo).
CARPETA_DATOS = Path("data/raw")
CARPETA_SALIDA = Path("data/processed")

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

        # Solo las planillas: deja afuera, por ejemplo, desktop.ini.
        planillas = [a for a in sub.iterdir() if a.suffix.lower() in EXTENSIONES]

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
            if archivo.suffix.lower() in EXTENSIONES:
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
    """Registro de actividad: una fila por cada clic o acceso."""
    df, meta = leer_con_encabezado(ruta, "Usuario")

    # PASO 4: columnas con nombres prolijos (los del campus tienen tildes y mayúsculas).
    df = pd.DataFrame({
        "id_alumno": normalizar_id(df["Usuario"]),
        "materia": materia,
        "fecha_hora": pd.to_datetime(df["Fecha"], errors="coerce"),  # texto -> fecha
        "ip": df.get("IP Usuario"),
        "perfil": df["Perfil"].astype("string").str.strip(),
        "seccion": df["Sección"].astype("string").str.strip(),
        "accion": df["Acción"].astype("string").str.strip(),
        "descripcion": df["Descripción"].astype("string").str.strip(),
    })

    # PASO 3: limpieza, contando cuánto se descarta en cada etapa para el reporte.
    filas = len(df)
    fechas_invalidas = int(df["fecha_hora"].isna().sum())
    df = df[df["fecha_hora"].notna()]               # sin fecha no sirve para nada
    no_alumnos = int((df["perfil"] != PERFIL_ALUMNO).sum())
    df = df[df["perfil"] == PERFIL_ALUMNO]          # saca docentes, tutores y coordinadores
    duplicados = int(df.duplicated().sum())
    df = df.drop_duplicates().drop(columns="perfil")  # saca filas repetidas exactas

    reporte.append(
        f"  trazabilidad {ruta.name}: {filas} filas leídas, {no_alumnos} de docentes u otros perfiles "
        f"descartadas, {duplicados} duplicados exactos descartados, {fechas_invalidas} fechas inválidas, "
        f"{len(df)} filas finales"
    )
    return df, meta


def leer_participacion(ruta, materia, reporte):
    """Resumen por alumno: avance, interacciones, tiempo de uso, primer y último ingreso."""
    df, meta = leer_con_encabezado(ruta, "Usuario", filas_encabezado=2)

    # PASO 4: "Encuestas - Cantidad" -> "encuestas_cantidad"
    df.columns = [a_snake(c) for c in df.columns]
    df = df.rename(columns={"usuario": "id_alumno"})
    df["id_alumno"] = normalizar_id(df["id_alumno"])
    df.insert(1, "materia", materia)

    # PASO 3: solo alumnos, y sin datos personales que no se usan.
    filas = len(df)
    perfiles = df["perfil"].value_counts().to_dict()
    df = df[df["perfil"] == PERFIL_ALUMNO].drop(columns=["perfil", "apellido", "nombre", "email", "aula"])

    # Textos -> fechas ("05/08/2025" se lee como día/mes/año)
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"], format="%d/%m/%Y", errors="coerce")
    for col in ("primera_interaccion", "ultima_interaccion"):
        df[col] = pd.to_datetime(df[col], format="%d/%m/%Y %H:%M:%S", errors="coerce")

    # "86" -> 86; "no aplica" -> vacío
    df["avance_pct"] = pd.to_numeric(df.pop("avance"), errors="coerce")
    # "10:07" -> 607 minutos
    df["tiempo_uso_min"] = hhmm_a_minutos(df.pop("tiempo_estimado_de_uso"))
    # Todo lo que no es ID, materia o fecha se pasa a número
    numericas = [c for c in df.columns if c not in
                 ("id_alumno", "materia", "fecha_alta", "primera_interaccion", "ultima_interaccion")]
    df[numericas] = df[numericas].apply(pd.to_numeric, errors="coerce")

    duplicados = int(df["id_alumno"].duplicated().sum())
    df = df.drop_duplicates("id_alumno")  # un alumno, una fila por materia
    reporte.append(
        f"  participacion {ruta.name}: {filas} filas, perfiles {perfiles}, "
        f"{duplicados} alumnos repetidos, {len(df)} alumnos finales"
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
        "instrumento": instrumento,                              # 1° Parcial
        "tipo_evaluacion": a_snake(instrumento),                 # 1_parcial
        "categoria_evaluacion": categoria_evaluacion(instrumento),  # parcial
        "nota": puntaje,                                         # 24
        "nota_maxima": maximo,                                   # 25
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

    # PASO 4: la fila limpia.
    df = pd.DataFrame({
        "id_alumno": normalizar_id(df["Identificación"]),
        "materia": materia,
        "comision": df["Comisión"].astype("string"),
        "estado_inscripcion": df["Estado Insc."].astype("string").str.strip(),  # Aceptada o Baja
        "instancia": df["Instancia"].astype("string").str.strip(),
        "fecha_inscripcion": pd.to_datetime(df["Fecha inscripción"], format="%d/%m/%Y %H:%M:%S", errors="coerce"),
    })

    # PASO 3: un alumno puede tener varias inscripciones (se dio de baja y se volvió
    # a inscribir). Se ordena por fecha y se queda con la última.
    filas = len(df)
    df["registros_inscripcion"] = df.groupby("id_alumno")["id_alumno"].transform("size")
    df = df.sort_values("fecha_inscripcion").drop_duplicates("id_alumno", keep="last")
    reporte.append(
        f"  matriculados {ruta.name}: {filas} filas, {filas - len(df)} inscripciones repetidas resueltas "
        f"por la más reciente, estados finales {df['estado_inscripcion'].value_counts().to_dict()}"
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
    trazas, partics, califs, matrics, dim_materia, avisos = [], [], [], [], [], []

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
            filtro = meta.get("Filtro aplicado", "")
            aula = re.search(r"Aula:\s*([^|]+)", filtro)  # "Aula: TUCD-MD-Álgebra 2025"
            fila_materia["aula"] = aula.group(1).strip() if aula else None
        for ruta in archivos["calificaciones"]:
            califs.append(leer_calificaciones(ruta, materia, reporte))  # uno por examen
        if nombre in matriculados:
            matrics.append(leer_matriculados(matriculados[nombre], materia, reporte))
        else:
            avisos.append(f"{nombre}: no tiene archivo en la carpeta de matriculados")

        dim_materia.append(fila_materia)
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
        "hechos_interacciones": pd.concat(trazas, ignore_index=True),
        "alumnos_aula": pd.concat(partics, ignore_index=True),
        "hechos_calificaciones": pd.concat(califs, ignore_index=True),
        "matricula": pd.concat(matrics, ignore_index=True),
    }

    # Tabla de materias, con la primera y la última fecha de actividad de cada una.
    # Sirve para saber entre qué fechas se puede mover el selector de fecha de corte.
    traza = modelo["hechos_interacciones"]
    dim = pd.DataFrame(dim_materia)
    rango = traza.groupby("materia")["fecha_hora"].agg(fecha_min="min", fecha_max="max").reset_index()
    modelo["dim_materia"] = dim.merge(rango, on="materia", how="left")

    # Tabla de alumnos: todos los IDs que aparecen en alguna fuente, sin repetir.
    ids = pd.concat([t["id_alumno"] for t in modelo.values() if "id_alumno" in t]).dropna().unique()
    modelo["dim_alumno"] = pd.DataFrame({"id_alumno": sorted(ids)})

    # Control del formato del ID: avisa si aparece alguno que no sea ALU_####.
    raros = [i for i in modelo["dim_alumno"]["id_alumno"] if not re.fullmatch(r"ALU_\d+", i)]
    if raros:
        avisos.append(f"IDs con formato distinto de ALU_####: {raros[:10]}")

    # Cierre del reporte: avisos y resumen de las tablas.
    reporte.append("AVISOS" if avisos else "Sin avisos.")
    reporte.extend(f"  - {a}" for a in avisos)
    reporte.append("")
    reporte.append("TABLAS")
    reporte.extend(f"  {n}: {len(t)} filas, columnas {list(t.columns)}" for n, t in modelo.items())
    return modelo, "\n".join(reporte)


def guardar(modelo, reporte, carpeta_salida):
    """Escribe cada tabla como CSV en data/processed, más el reporte de la carga."""
    carpeta_salida = Path(carpeta_salida)
    carpeta_salida.mkdir(parents=True, exist_ok=True)  # crea la carpeta si no existe
    for nombre, tabla in modelo.items():
        # utf-8-sig: para que Excel muestre bien las tildes si alguien abre el CSV
        tabla.to_csv(carpeta_salida / f"{nombre}.csv", index=False, encoding="utf-8-sig")
    (carpeta_salida / "reporte_carga.txt").write_text(reporte, encoding="utf-8")


# =============================================================================
# ARRANQUE: lo que corre al escribir "python cargar_datos.py"
# =============================================================================

if __name__ == "__main__":
    # sys.argv es lo que se escribió en la terminal, separado en una lista:
    #   python cargar_datos.py                    -> ["cargar_datos.py"]
    #   python cargar_datos.py otra_carpeta sal   -> ["cargar_datos.py", "otra_carpeta", "sal"]
    # Si se pasaron carpetas se usan esas; si no, las de siempre (data/raw y data/processed).
    datos = sys.argv[1] if len(sys.argv) > 1 else CARPETA_DATOS
    salida = sys.argv[2] if len(sys.argv) > 2 else CARPETA_SALIDA

    modelo, reporte = cargar(datos)    # PASOS 1 a 5
    guardar(modelo, reporte, salida)   # escribir los CSV
    print(reporte)                     # mostrar el reporte en la terminal
