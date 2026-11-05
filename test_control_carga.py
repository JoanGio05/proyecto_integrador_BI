import pandas as pd
from control_carga import ejecutar_control_de_carga
from evaluador_condiciones import cargar_reglas_json

# 1. Cargar reglas JSON existentes
reglas = cargar_reglas_json("reglas_materias.json")

# 2. Mock de lista de archivos en la carpeta (incluye uno corrupto/desconocido)
archivos_en_carpeta = [
    "calificaciones_alumnos_algebra.csv",
    "reporte_trazabilidad_algebra.csv",
    "matriculados_algebra.csv",
    "notas_viejas_borrador.xlsx",  # Archivo no reconocido
]

# 3. Mock de calificaciones (incluye alumno no matriculado y materia no configurada)
calificaciones_mock = pd.DataFrame([
    {"id_alumno": "1001", "materia": "algebra", "tipo_evaluacion": "parcial_1", "nota": 15},
    {"id_alumno": "9999", "materia": "algebra", "tipo_evaluacion": "parcial_1", "nota": 20},  # Alumno 9999 NO está matriculado
    {"id_alumno": "1001", "materia": "quimica_general", "tipo_evaluacion": "parcial_1", "nota": 8},  # Materia no configurada
])

# 4. Mock del padrón oficial de matriculados
matriculados_mock = pd.DataFrame([
    {"id_alumno": "1001", "materia": "algebra"},
    {"id_alumno": "1002", "materia": "algebra"},
    {"id_alumno": "1003", "materia": "algebra"},
])

# 5. Ejecutar control de carga
reporte = ejecutar_control_de_carga(
    archivos_carpeta=archivos_en_carpeta,
    df_calificaciones=calificaciones_mock,
    df_matriculados=matriculados_mock,
    reglas_dict=reglas,
)

# --- IMPRIMIR DIAGNÓSTICO ---
print("=== INFORME DE CONTROL DE CARGA ===")
print(f"¿Carga 100% Válida?: {reporte['es_valido']}\n")

if reporte["archivos_no_reconocidos"]:
    print("📂 ARCHIVOS NO RECONOCIDOS:")
    for arch in reporte["archivos_no_reconocidos"]:
        print(f"  - {arch}")
    print()

if reporte["alertas_estructura"]:
    print("📐 ALERTAS DE ESTRUCTURA:")
    for al in reporte["alertas_estructura"]:
        print(f"  - {al}")
    print()

if reporte["alertas_configuracion"]:
    print("⚙️ ALERTAS DE CONFIGURACIÓN:")
    for al in reporte["alertas_configuracion"]:
        print(f"  - {al}")
    print()

if reporte["alertas_matricula"]:
    print("🚨 ALERTAS DE MATRÍCULA:")
    for al in reporte["alertas_matricula"]:
        print(f"  - {al}")
    print()