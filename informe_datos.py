"""Genera las figuras y los números del informe (secciones 4, 5 y 7) a partir del modelo.

Uso:  python informe_datos.py <carpeta_salida>

Deja figuras PNG y un resultados.json con todos los números que cita el
informe, así el texto se puede verificar contra los datos. Usa las mismas
funciones que los dashboards (corte.py, evaluador_condiciones.py, metricas.py),
así un número del informe y uno del tablero nunca difieren.
"""
import datetime as dt
import json
import logging
import sys
import warnings
from pathlib import Path

import pandas as pd
import plotly.express as px

# Fuera de Streamlit, st.cache_data avisa en cada llamada: no hace falta verlo.
warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)

import estilo
import metricas as M
from participacion_trazabilidad import clasificar_eventos
from corte import cargar_tablas, color_por_materia
from evaluador_condiciones import cargar_reglas_json

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
estilo.aplicar_tema()
tablas = cargar_tablas()
reglas = cargar_reglas_json(Path(__file__).parent / "reglas_materias.json")
CORTE = tablas["materia"]["fecha_max"].max().date()   # el último día con datos: 24/10/2025
colnom = color_por_materia(tablas)                     # {"Álgebra": "#...", ...}
orden_nom = list(colnom)
clave_de = dict(zip(tablas["materia"]["nombre_materia"], tablas["materia"]["materia"]))
umbrales = M.umbrales_pct(reglas, tablas["materia"]["materia"])
R = {"fecha_corte": CORTE.strftime("%d/%m/%Y")}


def guardar(fig, nombre, ancho=900, alto=420):
    fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
    if nombre in ("f1_entrega", "f4_riesgo_semanal", "f5_inactivos_semanal", "f6_actividad_semanal"):
        fig.update_xaxes(tickformat="%d/%m")  # fechas en formato local, no "Aug 24"
    for intento in range(5):  # el exportador de plotly (kaleido) falla de vez en cuando
        try:
            fig.write_image(OUT / f"{nombre}.png", width=ancho, height=alto, scale=2)
            return
        except Exception:
            if intento == 4:
                raise


# ---------------------------------------------------------------- tabla al corte
T = M.tabla_alumnos(tablas, reglas, CORTE)
sit = M.situacion_alumnos(tablas, CORTE)
part = tablas["participacion"]
mat_tab = tablas["matricula"]
cal = tablas["calificaciones"]
evs, faltantes = M.fechas_examenes(tablas)

por = {}
for nombre in orden_nom:
    m = clave_de[nombre]
    t = T[T["materia"] == m]
    s = sit[sit["materia"] == m]
    vig = set(t["id_alumno"])
    con_nota = set(cal.loc[cal["materia"] == m, "id_alumno"])
    padron = mat_tab[mat_tab["materia"] == m]
    ultima = padron[padron["es_ultima_inscripcion"].astype(bool)]
    por[nombre] = {
        "inscriptos": int(len(ultima)), "vigentes": int(len(vig)),
        "bajas": int((ultima["estado_inscripcion"] == "Baja").sum()),
        "alumnos_aula": int(s["en_aula"].sum()),
        "aula_fuera_padron": int((s["en_aula"] & (s["inscripcion"] != "Inscripto")).sum()),
        "con_nota_fuera_padron": int(len(con_nota - vig)),
        "acceso_pct": round(100 * (1 - t["nunca_entro"].mean()), 1),
        "nunca_entro": int(t["nunca_entro"].sum()),
        "inactivos_pct": round(100 * t["inactivo"].mean(), 1),
        "avance_mediano": float(t["avance_pct"].median()),
        "tiempo_uso_semana_mediano": round(float(t["tiempo_uso_semana"].median()), 1),
        "sesiones_semana_mediana": round(float(t["sesiones_semana"].median()), 2),
        "nota_mediana": round(float(t["nota_normalizada"].median()), 1),
        "examenes_tomados": int(t["examenes_tomados"].iloc[0]),
        "condicion_pct": {k: round(100 * v, 1) for k, v in t["condicion"].value_counts(normalize=True).items()},
        "grupos": {k: int(v) for k, v in t["grupo"].value_counts().items()},
        "umbral_regular_pct": round(umbrales[m][0], 1),
        "umbral_promocion_pct": round(umbrales[m][1], 1),
        "regla": reglas[m],
    }
for variable, campo in (("sesiones_semana", "rho_sesiones"), ("tiempo_uso_semana", "rho_tiempo_uso")):
    T_var = T if variable == "sesiones_semana" else M.tabla_alumnos(tablas, reglas, CORTE, variable=variable)
    for _, r in M.correlaciones(T_var, variable).iterrows():
        nombre = T.loc[T["materia"] == r["materia"], "nombre_materia"].iloc[0]
        por[nombre][campo] = r["rho"]
R["por_materia"] = por
R["total"] = {"vigentes": int(len(T)), "riesgo": int((T["grupo"] == "riesgo_abandono").sum()),
              "esfuerzo": int((T["grupo"] == "esfuerzo_sin_resultado").sum()),
              "inactivos": int(T["inactivo"].sum())}
R["faltantes"] = faltantes.assign(fecha_referencia=faltantes["fecha_referencia"].dt.strftime("%d/%m/%Y"),
                                  fecha_apertura=faltantes["fecha_apertura"].dt.strftime("%d/%m/%Y")).to_dict("records")
R["examenes"] = evs.assign(fecha_apertura=evs["fecha_apertura"].dt.strftime("%d/%m/%Y"),
                           fecha_referencia=evs["fecha_referencia"].dt.strftime("%d/%m/%Y")
                           )[["nombre_materia", "instrumento", "categoria_evaluacion", "fecha_apertura",
                              "fecha_referencia", "realizaciones"]].to_dict("records")

# Comparación de reglas: medir sobre el puntaje total del año y solo con lo rendido
# (la primera versión), contra la regla vigente (sobre lo tomado y con cero en lo no rendido).
comp = []
for nombre in orden_nom:
    m = clave_de[nombre]
    regla = reglas[m]
    u_reg, u_pro = umbrales[m]
    t = T[T["materia"] == m]
    c = cal[(cal["materia"] == m) & cal["id_alumno"].isin(t["id_alumno"])]
    c = c[c["categoria_evaluacion"] != "recuperatorio"]
    if regla["metodo_calculo"] == "suma":
        original = 100 * c.groupby("id_alumno")["nota"].sum() / regla["puntaje_maximo"]
    else:
        original = c.groupby("id_alumno")["nota_pct"].mean()
    comp.append({"materia": nombre,
                 "promociona_regla_original": round(100 * (original >= u_pro).mean(), 1),
                 "libre_regla_original": round(100 * (original < u_reg).mean(), 1),
                 "promociona_regla_vigente": round(100 * (t["condicion"] == "promociona").mean(), 1),
                 "libre_regla_vigente": round(100 * (t["condicion"] == "libre").mean(), 1)})
R["comparacion_reglas"] = comp

# ---------------------------------------------------------------- F1 entrega por examen
filas = []
for nombre in orden_nom:
    m = clave_de[nombre]
    vig = set(T.loc[T["materia"] == m, "id_alumno"])
    e = evs[(evs["materia"] == m) & (evs["categoria_evaluacion"] != "recuperatorio")].sort_values("fecha_referencia")
    for i, (_, x) in enumerate(e.iterrows(), start=1):
        c = cal[(cal["id_evaluacion"] == x["id_evaluacion"]) & cal["id_alumno"].isin(vig)]
        filas.append({"materia": nombre, "orden": i, "instrumento": x["instrumento"],
                      "fecha": x["fecha_referencia"], "entrega": round(100 * len(c) / len(vig), 1),
                      "aprobacion": round(100 * (c["observacion"] == "aprobada").mean(), 1) if len(c) else None})
F1 = pd.DataFrame(filas)
R["entrega"] = F1.assign(fecha=F1["fecha"].dt.strftime("%d/%m")).to_dict("records")
fig = px.line(F1, x="fecha", y="entrega", color="materia", markers=True, color_discrete_map=colnom,
              category_orders={"materia": orden_nom}, hover_data=["instrumento"],
              labels={"fecha": "Fecha del examen (mediana de las realizaciones)",
                      "entrega": "Inscriptos que lo rindieron (%)", "materia": ""})
fig.update_yaxes(range=[0, 100]); fig.update_traces(line_width=2.5)
guardar(fig, "f1_entrega")

# ---------------------------------------------------------------- F2 condición
c = pd.DataFrame([{"materia": n, "condicion": estilo.ETIQUETAS_CONDICION[k], "pct": v}
                  for n in orden_nom for k, v in por[n]["condicion_pct"].items() if k in estilo.ETIQUETAS_CONDICION])
fig = px.bar(c, y="materia", x="pct", color="condicion", orientation="h", text=c["pct"].map(lambda v: f"{v:.0f} %"),
             color_discrete_map={estilo.ETIQUETAS_CONDICION[k]: v for k, v in estilo.COLORES_CONDICION.items()},
             category_orders={"condicion": [estilo.ETIQUETAS_CONDICION[k] for k in estilo.ORDEN_CONDICION],
                              "materia": orden_nom[::-1]},
             labels={"pct": "% de inscriptos vigentes", "materia": "", "condicion": ""})
fig.update_traces(textposition="inside", insidetextfont_color="white")
guardar(fig, "f2_condicion", alto=320)

# ---------------------------------------------------------------- F3 cruce
t = T.copy(); t["g"] = t["grupo"].map(estilo.ETIQUETAS_RIESGO)
fig = px.scatter(t, x="sesiones_semana", y="nota_normalizada", color="g", facet_col="nombre_materia",
                 category_orders={"nombre_materia": orden_nom,
                                  "g": [estilo.ETIQUETAS_RIESGO[g] for g in estilo.ORDEN_RIESGO]},
                 color_discrete_map={estilo.ETIQUETAS_RIESGO[g]: v for g, v in estilo.COLORES_RIESGO.items()},
                 labels={"sesiones_semana": "Sesiones por semana", "nota_normalizada": "Nota al corte (%)",
                         "g": "", "nombre_materia": ""})
fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
for i, n in enumerate(orden_nom, start=1):
    g = t[t["nombre_materia"] == n]
    fig.add_vline(x=g["sesiones_semana"].median(), line_dash="dot", line_color=estilo.GRIS_TEXTO, col=i, row=1)
    fig.add_hline(y=g["umbral_regular_pct"].iloc[0], line_dash="dot", line_color=estilo.GRIS_TEXTO, col=i, row=1)
fig.update_xaxes(range=[-0.3, t["sesiones_semana"].quantile(0.98) * 1.05]); fig.update_yaxes(range=[-3, 103])
fig.update_layout(legend=dict(y=1.2), margin=dict(t=80))
guardar(fig, "f3_cruce", ancho=1000, alto=420)

# ---------------------------------------------------------------- F4 y F5 evolución semanal
ev = []
for corte_ in pd.date_range("2025-08-29", CORTE, freq="7D").date:
    tt = M.tabla_alumnos(tablas, reglas, corte_)
    for n in orden_nom:
        x = tt[tt["nombre_materia"] == n]
        x_ok = x[x["grupo"] != "sin_datos"]
        ev.append({"corte": pd.Timestamp(corte_), "materia": n,
                   "vigentes": int(len(x)),
                   "riesgo": round(100 * (x_ok["grupo"] == "riesgo_abandono").mean(), 1) if len(x_ok) else None,
                   "inactivos": round(100 * x["inactivo"].mean(), 1) if len(x) else None,
                   "nota_mediana": round(float(x_ok["nota_normalizada"].median()), 1) if len(x_ok) else None})
EV = pd.DataFrame(ev)
R["evolucion"] = EV.assign(corte=EV["corte"].dt.strftime("%d/%m")).to_dict("records")
for campo, nombre, eje in [("riesgo", "f4_riesgo_semanal", "En riesgo de abandono (%)"),
                           ("inactivos", "f5_inactivos_semanal", "Inactivos: 14 días sin entrar (%)")]:
    fig = px.line(EV.dropna(subset=[campo]), x="corte", y=campo, color="materia", markers=True,
                  color_discrete_map=colnom, category_orders={"materia": orden_nom},
                  labels={"corte": "Fecha de corte", campo: eje, "materia": ""})
    fig.update_yaxes(rangemode="tozero"); fig.update_traces(line_width=2.5)
    guardar(fig, nombre, alto=380)

# ---------------------------------------------------------------- F6 actividad semanal
s = M.sesiones(tablas, CORTE).merge(T[["id_alumno", "materia", "nombre_materia"]], on=["id_alumno", "materia"])
s["semana"] = s["inicio"].dt.to_period("W-SUN").dt.start_time
sem = s.groupby(["semana", "nombre_materia"]).size().reset_index(name="sesiones")
fig = px.line(sem, x="semana", y="sesiones", color="nombre_materia", color_discrete_map=colnom,
              category_orders={"nombre_materia": orden_nom},
              labels={"semana": "Semana", "sesiones": "Sesiones de inscriptos", "nombre_materia": ""})
fig.update_traces(line_width=2.5)
for _, e in evs[evs["categoria_evaluacion"] == "parcial"].iterrows():
    fig.add_vline(x=e["fecha_referencia"], line_dash="dot", line_color=colnom[e["nombre_materia"]])
    fig.add_annotation(x=e["fecha_referencia"], y=1.02, yref="paper",
                       text=f"{e['instrumento']} ({e['nombre_materia'].split()[0]})",
                       showarrow=False, font=dict(size=11, color=estilo.GRIS_TEXTO))
guardar(fig, "f6_actividad_semanal", alto=380)

# ---------------------------------------------------------------- sensibilidad de reglas (sección 4, anexo E)
h = s.sort_values(["id_alumno", "materia", "inicio"]).groupby(["id_alumno", "materia"])["inicio"].diff()
h = (h.dt.total_seconds() / 86400).dropna()
R["huecos_entre_sesiones_dias"] = {"p50": round(h.quantile(.5), 1), "p90": round(h.quantile(.9), 1),
                                   "p95": round(h.quantile(.95), 1), "p99": round(h.quantile(.99), 1),
                                   "mayores_7": round(100 * (h > 7).mean(), 1),
                                   "mayores_14": round(100 * (h > 14).mean(), 1)}
R["sensibilidad_inactividad"] = {
    d: {k: round(100 * v, 1) for k, v in M.tabla_alumnos(tablas, reglas, CORTE, dias_inactividad=d)
        .groupby("nombre_materia")["inactivo"].mean().items()} for d in (7, 14, 21, 28)}
traza = tablas["interacciones"].sort_values(["id_alumno", "materia", "fecha_hora"])
gap = traza.groupby(["id_alumno", "materia"])["fecha_hora"].diff().dt.total_seconds() / 60
R["huecos_entre_eventos_min"] = {"p50": round(gap.quantile(.5), 1), "p75": round(gap.quantile(.75), 1),
                                 **{f"mayores_{u}": round(100 * (gap > u).mean(), 1) for u in (10, 30, 60)}}
R["sensibilidad_sesion"] = {
    u: {k: round(v, 2) for k, v in M.tabla_alumnos(tablas, reglas, CORTE, minutos=u)
        .groupby("nombre_materia")["sesiones_semana"].median().items()} for u in (10, 30, 60)}
ses = M.sesiones(tablas, CORTE)
R["sesiones"] = {"total": int(len(ses)), "duracion_mediana_min": round(float(ses["duracion_min"].median()), 1),
                 "eventos_mediana": float(ses["eventos"].median())}

# ---------------------------------------------------------------- mezcla de actividad (I09)
tr = tablas["interacciones"][tablas["interacciones"]["fecha_hora"] < M.limite_del_corte(CORTE)].copy()
# Solo inscriptos vigentes, como el dashboard 3 por defecto, con la tabla de equivalencias de Lauti.
tr = clasificar_eventos(tr.merge(T[["id_alumno", "materia"]], on=["id_alumno", "materia"]))
mez = (tr.groupby(["nombre_materia", "categoria"]).size() / tr.groupby("nombre_materia").size() * 100).round(1)
R["mezcla"] = {n: mez[n].to_dict() for n in orden_nom}

Path(OUT / "resultados.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("ok")
