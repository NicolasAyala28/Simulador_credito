"""Evaluación de una solicitud digitada: aplica las mismas reglas que las hojas RIE, Apetito y
Mitigantes (versión de parámetros activa) y muestra la decisión final."""
import json
from datetime import date

import pandas as pd
import streamlit as st

from src.apetito import PRODUCTIVO_ORDER, VEHICULO_ORDER, combinacion_key, vehiculo_key
from src.common import financed_amount, monthly_payment
from src.data_loader import (CODIGOS_SOLICITUD_PATH, MAX_FINANCIACION, MIN_FINANCIACION, OCUPACION_AVAL_PATH,
    prepare_data)
from src.escenarios import aplicar_cortes, cortes_escenario, escenario_aplicable, escenario_filtros, sembrar
from src.filtros import base_filtrable, filtros_desembolso, nota_desembolsos, selector_base
from src.decision import A_ESTUDIO, APROBADO, CONDICIONES, RIE_GROUPS, SEGMENT_ORDER, meets
from src.parametros import apetito_escenarios, mitigante_conditions, rie_params, version_sidebar
from src.rie import rie_scores
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Evaluar solicitud", page_icon="🧪", layout="wide")
apply_finanzauto_theme()

SIN_DECISION = "Sin decisión"
DECISION_COLORS = {APROBADO: "#087A55", CONDICIONES: "#F29A2E", A_ESTUDIO: "#D9534F", SIN_DECISION: "#9AA9B5"}
LICENCIAS = {"Particular": "PAR", "Público": "PUB"}
CONDICIONES_VEH = {"Nuevo": "N", "Usado": "U"}
DESTINOS = {"Productivo": "1", "Consumo": "0"}

def format_n(n):
    return f"{n:,.0f}".replace(",", ".")

with open(OCUPACION_AVAL_PATH, encoding="utf-8") as f:
    OCUPACIONES = json.load(f)  # código -> nombre
with open(CODIGOS_SOLICITUD_PATH, encoding="utf-8") as f:
    _codigos = json.load(f)
CALIFICACIONES = _codigos["CalificacionMontoMax"]  # código -> letra (diccionario Variables Frank)
ESTADOS_CIVILES = list(_codigos["EstadoCivil"].values())  # Casado(a), Soltero(a), Union Libre, Separado/Viudo/Divorciado

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Evaluar una solicitud</h1>
  <p>Digita los datos de una solicitud y obtén su decisión con los parámetros de la versión activa: RIE, perfil,
  vehículo, matriz de decisión y mitigantes.</p>
</div>
""", unsafe_allow_html=True)

# Base de referencia: con ella se ubica el puntaje en su decil (dentro del segmento) y el valor a financiar en
# su quintil, igual que en la hoja Apetito.
# La base de referencia se elige con los mismos filtros de base y de desembolso de las hojas RIE y Apetito.
BASE_COMPLETA = base_filtrable()
st.markdown("**Base de referencia** · decil del puntaje y quintil del valor a financiar")
c_base, c_n = st.columns([1, 2], gap="medium")
base_ref = selector_base("prueba_base", c_base)
BASE, elegidos_ref = filtros_desembolso(BASE_COMPLETA, base_ref, "prueba")
c_n.metric("Con los filtros actuales", format_n(len(BASE)),
           help=f"Registros de la base {base_ref} con los que se ubican el decil y el quintil de la solicitud.")
if base_ref == "Desembolsos":
    st.caption(nota_desembolsos(BASE_COMPLETA))
sembrar(apetito_escenarios(), SEGMENT_ORDER)
# Escenario de apetito de estos filtros (o su respaldo), con sus niveles y sus rangos y deciles: los mismos que
# aplican Apetito y Mitigantes a una solicitud con esos filtros.
ESC_CLAVE, levels = escenario_aplicable(apetito_escenarios(), escenario_filtros(base_ref, elegidos_ref))
CORTES = levels.get("cortes") or cortes_escenario(levels["filtros"])
st.caption(f"Escenario de apetito aplicado: **{ESC_CLAVE}**"
           + ("" if levels.get("cortes") else " (rangos y deciles calculados con los datos actuales)") + ".")
conditions = mitigante_conditions()

# ---------------- Formulario ----------------
with st.form("prueba_form"):
    st.markdown("**Vehículo y crédito**")
    c1, c2, c3, c4 = st.columns(4)
    valor_vh = c1.number_input("Valor del vehículo", min_value=0.0, value=80_000_000.0, step=1_000_000.0, format="%.0f")
    cuota_ini = c2.number_input("Monto cuota inicial", min_value=0.0, value=20_000_000.0, step=1_000_000.0, format="%.0f")
    tasa = c3.number_input("Tasa MV (%)", min_value=0.0, max_value=10.0, value=1.80, step=0.01, format="%.2f")
    plazo = c4.selectbox("Plazo (meses)", list(range(12, 73, 12)), index=4)
    c1, c2, c3, c4 = st.columns(4)
    licencia = c1.selectbox("Licencia", list(LICENCIAS))
    condicion = c2.selectbox("Condición", list(CONDICIONES_VEH))
    destino = c3.selectbox("Destino", list(DESTINOS))

    st.markdown("**Cliente**")
    c1, c2, c3, c4 = st.columns(4)
    ingresos = c1.number_input("Ingresos mensuales", min_value=0.0, value=6_000_000.0, step=100_000.0, format="%.0f")
    cuota_telcos = c2.number_input("Valor cuota sin telcos (ValorCuotaSectorTelcos)", min_value=0.0, value=500_000.0,
                                   step=50_000.0, format="%.0f")
    puntaje = c3.number_input("Puntaje (Acierta)", min_value=0, max_value=1000, value=700, step=1,
                              help="Se ubica en su decil (P10 a P100) dentro del segmento, con la base del simulador.")
    ocupacion = c4.selectbox("Ocupación", list(OCUPACIONES.values()))
    c1, c2, c3, c4 = st.columns(4)
    ocupacion_aval = c1.selectbox("Ocupación del avalista", ["Sin avalista"] + list(OCUPACIONES.values()),
                                  help="Define el segmento de Ama de casa y Universitario.")
    estado_civil = c2.selectbox("Estado civil", ESTADOS_CIVILES,
                                help="Casado(a) y unión libre usan los umbrales de PTI y DTI de «Casado / unión libre».")

    st.markdown("**Experiencia crediticia**")
    c1, c2, c3, _ = st.columns(4)
    monto_max = c1.number_input("Monto máximo solicitado", min_value=0.0, value=30_000_000.0, step=1_000_000.0, format="%.0f")
    fecha_max = c2.date_input("Fecha de desembolso del monto máximo", value=date(2020, 1, 1), max_value=date.today())
    calificacion = c3.selectbox("Calificación del monto máximo", list(CALIFICACIONES),
                                format_func=lambda k: CALIFICACIONES[k])

    st.markdown("**Mitigantes** (se suponen idóneos cuando están en 1)")
    c1, c2, c3, _ = st.columns(4)
    avalista = c1.selectbox("Avalista", [1, 0], index=1, help="1: tiene un avalista idóneo.")
    garantia = c2.selectbox("Garantía", [1, 0], index=1,
                            help="1: tiene garantía idónea que supera el 50 % del valor a financiar.")
    fga = c3.selectbox("FGA", [1, 0], index=1, help="1: se puede tomar FGA.")
    evaluar = st.form_submit_button("Evaluar solicitud", type="primary")

if not evaluar:
    st.info("Completa el formulario y pulsa «Evaluar solicitud».")
    version_sidebar()
    st.stop()

# ---------------- Evaluación ----------------
aval_code = next((k for k, v in OCUPACIONES.items() if v == ocupacion_aval), None)
solicitud = pd.DataFrame([{
    "ValorVh": valor_vh, "MontoCtaInicial": cuota_ini, "tasa_nominal": tasa, "PlazoMeses": plazo,
    "ValorCuotaSectorTelcos": cuota_telcos, "ingresos": ingresos, "MontoMaxSolicGeneral": monto_max,
    "FechaAperturaMontoMax": pd.Timestamp(fecha_max), "FechaProceso": pd.Timestamp(date.today()),
    "CalificacionMontoMax": int(calificacion), "descripcion_ocupacion": ocupacion,
    "Avalista1Ocupacion": aval_code, "licencia_vehiculo": LICENCIAS[licencia],
    "condicion_vehiculo": CONDICIONES_VEH[condicion], "productivo": DESTINOS[destino],
    "estado_civil": estado_civil,
}])
financiar = float(financed_amount(solicitud).iloc[0]) if valor_vh > 0 else float("nan")
if not valor_vh or not financiar > 0:
    st.error("El valor del vehículo debe ser mayor que la cuota inicial.")
    version_sidebar()
    st.stop()
if financiar > MAX_FINANCIACION or financiar < MIN_FINANCIACION:
    st.warning(f"El valor a financiar ({format_n(financiar)}) está fuera del rango del estudio "
               f"({format_n(MIN_FINANCIACION)} a {format_n(MAX_FINANCIACION)}): la solicitud está "
               "fuera del alcance del estudio y el simulador no la evalúa.")
    version_sidebar()
    st.stop()

prep = prepare_data(solicitud, incluir_sin_dato=True)
segmento = prep["segmentacion"].iloc[0]
rie = rie_scores(prep, rie_params(), detail=True).iloc[0]
rie_grupo = RIE_GROUPS.get(int(rie["Normalización"])) if pd.notna(rie["Normalización"]) else None
# Decil del puntaje (en su segmento) y rango del valor a financiar con los cortes del escenario.
decil, valor_q = aplicar_cortes(pd.DataFrame({"acierta": [puntaje], "perfil_label": [segmento], "ValorVh": [valor_vh],
                                              "MontoCtaInicial": [cuota_ini]}), CORTES)
decil = decil.iloc[0] if pd.notna(decil.iloc[0]) else None
valor_q = valor_q.iloc[0] if pd.notna(valor_q.iloc[0]) else None
vehiculo = f"{licencia}/{condicion}"
nivel_perfil = levels["perfil"].get(f"{segmento} | {rie_grupo} | {decil}")
nivel_vehiculo = levels["vehiculo"].get(vehiculo_key(segmento, destino, valor_q, vehiculo))
combo = combinacion_key([destino, nivel_perfil, nivel_vehiculo])
decision_matriz = levels["matriz"].get(combo) if nivel_perfil and nivel_vehiculo else None

# Mitigantes: lo exigido al detalle (licencia/condición y RIE) tiene precedencia sobre lo exigido a la combinación.
need = conditions.get(combinacion_key([destino, nivel_perfil, nivel_vehiculo, vehiculo, rie_grupo])) or conditions.get(combo, {})
flags = pd.DataFrame([{"avalista_idoneo": bool(avalista), "garantia_idonea": bool(garantia), "fga": bool(fga)}])
cumple = meets(flags, need).iloc[0] if decision_matriz == CONDICIONES else pd.NA
cumple = None if pd.isna(cumple) else bool(cumple)
if decision_matriz in (APROBADO, A_ESTUDIO):
    final = decision_matriz
elif decision_matriz == CONDICIONES and cumple is not None:
    final = APROBADO if cumple else A_ESTUDIO
else:
    final = SIN_DECISION

# ---------------- Resultado ----------------
st.markdown('<div class="fa-section">Resultado</div>', unsafe_allow_html=True)
cuota = float(monthly_payment(prep, rie_params()["plazo_meses"]).iloc[0])
ingreso_ok = pd.to_numeric(prep["ingresos"], errors="coerce").iloc[0]
c = st.columns(5)
c[0].metric("Valor a financiar", format_n(financiar))
c[1].metric("Cuota mensual", format_n(cuota) if pd.notna(cuota) else "–")
c[2].metric("LTV", f"{financiar / valor_vh * 100:.1f}%")
c[3].metric("PTI", f"{cuota / ingreso_ok * 100:.1f}%" if pd.notna(ingreso_ok) and ingreso_ok else "Ingreso no válido")
c[4].metric("DTI", f"{(cuota + cuota_telcos) / ingreso_ok * 100:.1f}%" if pd.notna(ingreso_ok) and ingreso_ok else "–")

c = st.columns(4)
with c[0], st.container(border=True):
    st.markdown("**Perfil**")
    st.write(f"Segmento: **{segmento}**")
    st.write(f"RIE: **{rie['Puntaje'] if pd.notna(rie['Puntaje']) else '–'}** de 7 → grupo **{rie_grupo or 'no calculable'}**")
    st.write(f"Decil del puntaje: **{decil or '–'}**")
    st.write(f"Nivel perfil: **{nivel_perfil or 'Sin nivel'}**")
with c[1], st.container(border=True):
    st.markdown("**Vehículo**")
    st.write(f"Destino: **{destino}**")
    st.write(f"Valor a financiar: **{valor_q or '–'}** · Licencia/condición: **{vehiculo}**")
    st.write(f"Nivel vehículo: **{nivel_vehiculo or 'Sin nivel'}**")
with c[2], st.container(border=True):
    st.markdown("**Matriz de decisión**")
    st.write(f"{destino} · perfil {nivel_perfil or '–'} · vehículo {nivel_vehiculo or '–'}")
    st.write(f"Decisión de la celda: **{decision_matriz or SIN_DECISION}**")
with c[3], st.container(border=True):
    st.markdown("**Mitigantes**")
    if decision_matriz != CONDICIONES:
        st.write("No aplica: la celda no está en Condiciones.")
    elif int(need.get("desistir", 0)):
        st.write("La fila está marcada para desistir: va a estudio.")
    else:
        exigidos = [n for n, k in [("Avalista", "avalista"), ("Garantía", "garantia"), ("FGA", "fga")] if int(need.get(k, 0))]
        st.write(f"Exigidos: **{', '.join(exigidos) or 'ninguno'}**")
        st.write("Cumple: **" + ("Sí" if cumple is True else "No" if cumple is False else "sin mitigante exigido") + "**")

# ---------------- Factores del RIE ----------------
st.markdown('<div class="fa-section">Factores del RIE</div>', unsafe_allow_html=True)
params = rie_params()
lic_nombre = licencia  # Particular / Público: llaves de los parámetros
estado_key = "Casado / unión libre" if bool(rie["casado"]) else "Otro"

def num_txt(v, fmt="{:.1f}", suf=""):
    return (fmt.format(v) + suf).replace(".", ",") if pd.notna(v) else "–"

def nota(v, maximo):
    return f"{int(v)} de {maximo}" if pd.notna(v) else "No calculable"

def cumple_txt(ok):
    return "Cumple" if bool(ok) else "No cumple"

ltv_rangos = "; ".join(f"{lo:g}–{hi:g} %: {p}" for (lo, hi), p in zip(params["ltv"][lic_nombre], [3, 2, 1, 0]))
umbral = lambda ind: params[ind][lic_nombre][estado_key]
filas = [
    ("Respaldo", "LTV (valor a financiar / valor del vehículo)", num_txt(rie["LTV"], suf=" %"), nota(rie["score_ltv"], 3),
     f"{licencia}: {ltv_rangos}"),
    ("Ingresos", "PTI (cuota / ingreso)", num_txt(rie["PTI"], suf=" %"), nota(rie["score_pti"], 2),
     f"2 si ≤ {umbral('pti')['medio']:g} %; 1 si ≤ {umbral('pti')['alto']:g} %; 0 si es mayor ({licencia}, {estado_key})"),
    ("Ingresos", "DTI ((cuota + cuota sin telcos) / ingreso)", num_txt(rie["DTI"], suf=" %"), nota(rie["score_dti"], 2),
     f"2 si ≤ {umbral('dti')['medio']:g} %; 1 si ≤ {umbral('dti')['alto']:g} %; 0 si es mayor ({licencia}, {estado_key})"),
    ("Ingresos", "EI (valor a financiar / ingreso)", num_txt(rie["EI"], suf=" veces"), nota(rie["score_ei"], 2),
     f"2 si ≤ {params['ei']['medio']:g}; 1 si ≤ {params['ei']['alto']:g}; 0 si es mayor"),
    ("Ingresos", "Componente Ingresos (promedio de PTI, DTI y EI × 1,5)", "",
     num_txt(rie["score_ingresos"], "{:.2f}", " de 3") if pd.notna(rie["score_ingresos"]) else "No calculable", ""),
    ("Experiencia", "Monto máximo / valor a financiar", num_txt(rie["exp_ratio"], suf=" %"), cumple_txt(rie["exp_monto_ok"]),
     f"Mayor a {params['experiencia_pct']:g} %"),
    ("Experiencia", "Antigüedad del monto máximo", num_txt(rie["exp_antiguedad_dias"], "{:.0f}", " días"),
     cumple_txt(rie["exp_antiguedad_ok"]), "Al menos 1 año (365 días)"),
    ("Experiencia", "Calificación del monto máximo", CALIFICACIONES[calificacion], cumple_txt(rie["exp_calificacion_ok"]),
     "AA, A o BB (código menor a 4)"),
    ("Experiencia", "Garantía de servicio público", "Se asume cumplido" if licencia == "Público" else "No aplica",
     cumple_txt(rie["exp_publica_ok"]), "Solo licencia pública"),
    ("Experiencia", "Componente Experiencia", "", nota(rie["score_experiencia"], 1), "1 si cumple todos los criterios"),
    ("Total", "Puntaje RIE (Respaldo + Ingresos + Experiencia, redondeado)",
     num_txt(rie["puntaje_sin_redondeo"], "{:.2f}"), nota(rie["Puntaje"], 7),
     "Grupo: 0–3 → 0-1; 4–5 → 2; 6–7 → 3" + (f" → {rie_grupo}" if rie_grupo else "")),
]
st.dataframe(pd.DataFrame(filas, columns=["Componente", "Factor", "Valor", "Calificación", "Regla"]),
             width="stretch", hide_index=True)
st.caption("Umbrales de la versión de parámetros activa (hoja RIE). La cuota usa el plazo y la tasa digitados. "
           "El ingreso solo es válido entre 1 y 100 millones; fuera de ese rango PTI, DTI y EI no se calculan.")

color = DECISION_COLORS[final]
st.markdown(f"""<div style="margin-top:14px;padding:18px 22px;border-radius:12px;background:{color};color:white">
  <div style="font-size:13px;opacity:.9">Decisión final</div>
  <div style="font-size:30px;font-weight:800">{final}</div></div>""", unsafe_allow_html=True)
notas = []
if not rie_grupo:
    notas.append("el RIE no es calculable con los datos digitados (revisa ingresos entre 1 y 100 millones, tasa y valores)")
if segmento == "Sin dato":
    notas.append("la ocupación no tiene segmento")
if final == SIN_DECISION and decision_matriz == CONDICIONES:
    notas.append("la combinación está en Condiciones sin mitigante exigido en la hoja Mitigantes")
st.caption("Se usan los parámetros de la versión activa (barra lateral) con los cambios de la sesión. En licencia pública se asume cumplido el requisito de garantía de servicio público de "
           "la experiencia." + (" Sin decisión porque " + "; ".join(notas) + "." if notas and final == SIN_DECISION else ""))

version_sidebar()
