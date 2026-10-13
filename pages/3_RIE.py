import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import load_data, prepare_data
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="RIE · Componentes y reglas", page_icon="◈", layout="wide")
apply_finanzauto_theme()

DATA = prepare_data(load_data()).copy()
GREEN = "#087A55"
DARK = "#064B39"
MID = "#43BD83"
LIGHT = "#BFE6CD"
TEXT = "#0A2F4A"

st.markdown("""
<style>
.rie-banner{padding:16px 20px;border-radius:13px;background:linear-gradient(105deg,#064B39 0%,#087A55 72%,#15966A 100%);color:white;margin:8px 0 12px 0;box-shadow:0 2px 8px #064b391c}
.rie-banner h2{color:white!important;margin:0;font-size:1.35rem}
.rie-banner p{margin:3px 0 0 0;color:#eefaf4;font-size:.9rem}
.rie-card{background:linear-gradient(140deg,#f2faf6,#e5f3ec);border:1px solid #d9e9e0;border-radius:12px;padding:16px;height:100%;}
.rie-card-label{font-size:12px;font-weight:700;color:#42675a}
.rie-card-number{font-size:30px;font-weight:800;color:#064B39;line-height:1.2;margin-top:5px}
.rie-card-pct{font-size:13px;color:#42675a;font-weight:700}
.rie-note{font-size:12px;color:#526b63;margin-top:8px}
</style>
""", unsafe_allow_html=True)

st.title("RIE – Componentes y reglas")
st.caption("Evalúa Respaldo, Ingresos y Experiencia. La puntuación de resultados aplica las ponderaciones y tablas de Motor_decision.pptx. Los editores de rangos son herramientas exploratorias.")

# Utilidades de normalización para columnas que llegan como texto o con separadores.
def num(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    s = series.astype("string").str.strip().str.replace("$", "", regex=False).str.replace(" ", "", regex=False)
    # En esta base las comas de campos monetarios suelen ser separadores de miles.
    s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")

def field(name):
    if name not in DATA:
        return pd.Series(np.nan, index=DATA.index, dtype=float)
    return num(DATA[name])

def format_n(n):
    return f"{int(n):,}".replace(",", ".")

def missing_card(mask, title, reason):
    mask = pd.Series(mask).fillna(False).astype(bool)
    n = int(mask.sum())
    total = len(mask)
    pct = n / total * 100 if total else 0
    st.markdown(f"""<div class="rie-card"><div class="rie-card-label">▧ &nbsp; Registros sin información ({title})</div><div class="rie-card-number">{format_n(n)}</div><div class="rie-card-pct">({pct:.1f}%)</div><div class="rie-note">{reason}</div></div>""", unsafe_allow_html=True)

def banner(title, subtitle, icon):
    st.markdown(f'<div class="rie-banner"><h2>{icon} &nbsp; {title}</h2><p>{subtitle}</p></div>', unsafe_allow_html=True)

def density_chart(series, title, xlabel, thresholds, key, license_label=None):
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    values = values[(values >= values.quantile(.005)) & (values <= values.quantile(.995))] if len(values) > 20 else values
    fig = go.Figure()
    if len(values) >= 2 and values.nunique() > 1:
        # Histograma calculado explícitamente para aplicar degradado de verdes por intervalo.
        hist, edges = np.histogram(values.to_numpy(dtype=float), bins=35, density=True)
        palette = ["#DDF3E5", "#BFE6CD", "#8BD5AA", "#43BD83", "#15966A", "#087A55", "#064B39"]
        centers = (edges[:-1] + edges[1:]) / 2
        colors = [palette[min(len(palette)-1, int(i / max(1, len(hist)-1) * (len(palette)-1)))] for i in range(len(hist))]
        fig.add_trace(go.Bar(x=centers, y=hist, width=(edges[1]-edges[0]) * 0.96,
            marker=dict(color=colors, line=dict(color=GREEN, width=0.35)), opacity=0.88,
            name="Densidad", hovertemplate=f"{xlabel}: %{{x:.2f}}<br>Densidad: %{{y:.4f}}<extra></extra>"))
        # Curva suavizada de densidad con una aproximación kernel gaussiana sin dependencias extra.
        x = values.to_numpy(dtype=float)
        grid = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 180)
        sd = float(np.std(x, ddof=1))
        bandwidth = max(1.06 * sd * (len(x) ** (-1/5)), (grid[-1]-grid[0])/150 if len(grid)>1 else 1e-6, 1e-9)
        density = np.zeros_like(grid)
        for start in range(0, len(x), 1500):
            z = (grid[:, None] - x[None, start:start+1500]) / bandwidth
            density += np.exp(-0.5*z*z).sum(axis=1)
        density /= (len(x) * bandwidth * np.sqrt(2*np.pi))
        fig.add_trace(go.Scatter(x=grid, y=density, mode="lines", line=dict(color=DARK, width=2),
            fill="tozeroy", fillcolor="rgba(67,189,131,0.12)", name="Curva de densidad", hoverinfo="skip"))
    elif len(values):
        fig.add_trace(go.Histogram(x=values, histnorm="probability density", nbinsx=8,
            marker_color=MID, name="Densidad"))
    for threshold in sorted(set(float(t) for t in thresholds if t is not None and np.isfinite(t))):
        fig.add_vline(x=threshold, line_width=1.5, line_dash="dash", line_color=GREEN,
            annotation_text=f"{threshold:g}", annotation_position="top")
    fig.update_layout(title=None, height=280, margin=dict(l=8,r=8,t=30,b=35),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT,size=10), showlegend=False,
        xaxis=dict(title=xlabel, showgrid=False, zeroline=False),
        yaxis=dict(title="Densidad", gridcolor="#e5eee9", zeroline=False))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar":False}, key=key)
    st.caption(f"{format_n(len(values))} registros con valor calculable" + (f" · {license_label}" if license_label else ""))

def editable_ranges(key, rows, min_vals, max_vals, labels, help_text="Edita los límites; las calificaciones son fijas."):
    # Cada tabla de rangos tiene su propio botón de restablecimiento.
    c1, c2 = st.columns([3, 1])
    with c1:
        st.caption(help_text)
    with c2:
        if st.button("↺ Restablecer", key=f"{key}_reset", width="stretch"):
            st.session_state.pop(key, None)
            st.rerun()
    frame = pd.DataFrame({"Rango mínimo": min_vals, "Rango máximo": max_vals,
                          "Calificación RIE": labels})
    edited = st.data_editor(frame, key=key, width="stretch", hide_index=True,
        num_rows="fixed", column_config={
            "Rango mínimo": st.column_config.NumberColumn("Rango mínimo", min_value=0.0, max_value=1000000000.0, step=0.1, format="%.2f", required=True),
            "Rango máximo": st.column_config.NumberColumn("Rango máximo", min_value=0.0, max_value=1000000000.0, step=0.1, format="%.2f", required=True),
            "Calificación RIE": st.column_config.NumberColumn("Calificación RIE", disabled=True),
        })
    mins = pd.to_numeric(edited["Rango mínimo"], errors="coerce").to_numpy(dtype=float)
    maxs = pd.to_numeric(edited["Rango máximo"], errors="coerce").to_numpy(dtype=float)
    valid = np.all(np.isfinite(mins)) and np.all(np.isfinite(maxs)) and np.all(mins < maxs) and np.all(mins[1:] >= maxs[:-1])
    if not valid:
        st.warning("Revisa los límites: cada mínimo debe ser menor que su máximo y los rangos no deben superponerse.")
    return mins, maxs, valid

def classify_ranges(series, mins, maxs, scores, valid=True):
    values = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=values.index, dtype=float)
    if not valid:
        return result
    for lo, hi, score in zip(mins, maxs, scores):
        mask = values.notna() & (values >= lo) & (values <= hi)
        # Evita asignar dos calificaciones en límites compartidos: se asigna al rango superior salvo el último.
        result.loc[mask] = score
    return result

# Perfil global. Las modificaciones no se guardan fuera de la sesión.
# El botón borra el estado de los editores para volver a los rangos predeterminados.
profile_options = ["Todos"] + sorted(DATA["perfil_label"].dropna().astype(str).unique().tolist())
profile = st.selectbox("Perfil", profile_options, key="rie_profile")
VIEW = DATA if profile == "Todos" else DATA[DATA["perfil_label"].astype(str).eq(profile)]

# ---------------- Respaldo / LTV ----------------
banner("Respaldo – LTV", "Relación entre el valor a financiar y el valor del vehículo (garantía).", "◈")
license_ltv = st.radio("Tipo de licencia", ["Particular", "Público"], horizontal=True, key="rie_ltv_license")
ltv_part = license_ltv == "Particular"
ltv_defaults = ([70.0,75.0,85.0,100.0] if ltv_part else [75.0,80.0,90.0,100.0])
ltv_min_default = [0.0] + ltv_defaults[:-1]
ltv_max_default = ltv_defaults
with st.container(border=True):
    left, center, right = st.columns([1.05,1.55,.72], gap="medium")
    with left:
        with st.expander("Fórmula e información del LTV", expanded=False):
            st.latex(r"LTV = \frac{Valor\ a\ financiar}{ValorVh} \times 100")
            st.caption("Valor a financiar = ValorVh − MontoCtaInicial")
            st.caption("Equivalente: ValorVh × ((100 − cuota inicial %) / 100), si la cuota inicial está expresada como porcentaje.")
        st.markdown("**Reglas LTV (%)**")
        ltv_mins, ltv_maxs, ltv_valid = editable_ranges(f"rie_ltv_ranges_{license_ltv}", [0,1,2,3], ltv_min_default, ltv_max_default, [3,2,1,0])
    with center:
        st.markdown(f"**Distribución de LTV · {license_ltv}**")
        vehicle_value = field("ValorVh")
        down_payment = field("MontoCtaInicial")
        financing = vehicle_value - down_payment
        ltv = financing.div(vehicle_value.where(vehicle_value > 0)).mul(100)
        license_mask = VIEW["licencia_vehiculo"].astype("string").str.upper().eq("PAR" if ltv_part else "PUB")
        ltv_view = ltv.loc[VIEW.index][license_mask]
        ltv_mapped = pd.Series(np.nan,index=ltv_view.index,dtype=float)
        if ltv_valid:
            for lo, hi, score in zip(ltv_mins,ltv_maxs,[3,2,1,0]):
                mask=(ltv_view>=lo)&(ltv_view<=hi)
                ltv_mapped.loc[mask]=score
        density_chart(ltv_view, "Distribución LTV", "LTV (%)", ltv_mins[1:], f"rie_ltv_density_{license_ltv}", license_ltv)
    with right:
        missing_ltv = vehicle_value.isna() | down_payment.isna() | (vehicle_value <= 0) | (down_payment < 0) | (down_payment > vehicle_value)
        missing_card(missing_ltv.loc[VIEW.index], "LTV", "No se calcula por valor del vehículo o cuota inicial nulos o inconsistentes.")

# ---------------- Ingresos ----------------
banner("Ingresos – PTI, DTI y EI", "Capacidad de pago a partir de la cuota del crédito, endeudamiento y monto financiado.", "▤")
indicator = st.radio("Indicador", ["PTI", "DTI", "EI"], horizontal=True, key="rie_income_indicator")
# El plazo no está disponible como campo en la base; se pide como parámetro de sesión para la fórmula de cuota.
with st.expander("Fórmula y parámetros de la cuota mensual", expanded=False):
    term_months = st.number_input("Plazo de financiación (meses)", min_value=1, max_value=120, value=60, step=1, key="rie_term_months")
    st.markdown("**Fórmula financiera de cuota fija (sistema francés)**")
    st.latex(r"C = P \cdot \frac{i(1+i)^n}{(1+i)^n-1}")
    st.markdown("Donde:")
    st.markdown("- **C:** cuota mensual calculada.\n- **P:** valor a financiar = `ValorVh - MontoCtaInicial`.\n- **i:** tasa de interés mensual = `tasa_nominal / 100` (la tasa nominal de la base ya es mensual).\n- **n:** plazo en meses; por ahora, **60 meses por defecto**.")
    st.caption("La tasa_nominal se interpreta como tasa mensual. Si la tasa es 0 %, la cuota se calcula como P / n. El plazo se mantiene editable durante esta etapa y se reemplazará por la variable del conjunto de datos cuando esté disponible.")
principal = (field("ValorVh") - field("MontoCtaInicial")).where(field("ValorVh") > 0)
monthly_rate = field("tasa_nominal") / 100.0
# PMT = P*r / (1-(1+r)^(-n)); para tasa cero, P/n.
payment = pd.Series(np.nan, index=DATA.index, dtype=float)
valid_payment = principal.notna() & (principal > 0) & monthly_rate.notna() & (monthly_rate >= 0)
nonzero = valid_payment & monthly_rate.gt(0)
zero = valid_payment & monthly_rate.eq(0)
payment.loc[nonzero] = principal.loc[nonzero] * monthly_rate.loc[nonzero] / (1 - (1 + monthly_rate.loc[nonzero]) ** (-term_months))
payment.loc[zero] = principal.loc[zero] / term_months
income = field("IngresoTotalMensual")
pti = payment.div(income.where(income > 0)).mul(100)
dti = (payment + field("ValorCuotaSectorTelcos")).div(income.where(income > 0)).mul(100)
ei = principal.div(income.where(income > 0))
metric_map = {"PTI": pti, "DTI": dti, "EI": ei}
metric = metric_map[indicator]
if indicator == "EI":
    defaults_min, defaults_max = [0,12,18], [12,18,1000000]
    scores = [2,1,0]
    unit = "Veces"
    description = "EI = Valor a financiar / IngresoTotalMensual"
elif indicator == "PTI":
    defaults_min, defaults_max = [0,30,40,50], [30,40,50,1000]
    scores = [0,1,2,3]
    unit = "%"
    description = "PTI = Cuota mensual calculada / IngresoTotalMensual × 100"
else:
    defaults_min, defaults_max = [0,30,40,50], [30,40,50,1000]
    scores = [0,1,2,3]
    unit = "%"
    description = "DTI = (Cuota mensual calculada + ValorCuotaSectorTelcos) / IngresoTotalMensual × 100"
with st.container(border=True):
    left, center, right = st.columns([1.05,1.55,.72], gap="medium")
    with left:
        st.markdown(f"**Reglas {indicator}**")
        st.caption(description)
        mins, maxs, valid_ranges = editable_ranges(f"rie_{indicator.lower()}_ranges", list(range(len(scores))), defaults_min, defaults_max, scores)
    with center:
        st.markdown(f"**Distribución de {indicator}**")
        thresholds = mins[1:] if valid_ranges else []
        density_chart(metric.loc[VIEW.index], f"Distribución de {indicator}", f"{indicator} ({unit})", thresholds, f"rie_{indicator.lower()}_density")
    with right:
        if indicator == "PTI":
            missing = payment.isna() | income.isna() | (income <= 0)
            reason = "No se calcula por falta de valor a financiar, tasa, plazo válido o ingreso mensual."
        elif indicator == "DTI":
            telco = field("ValorCuotaSectorTelcos")
            missing = payment.isna() | telco.isna() | income.isna() | (income <= 0)
            reason = "No se calcula por falta de cuota mensual, cuota de experiencia o ingreso mensual."
        else:
            missing = principal.isna() | income.isna() | (income <= 0)
            reason = "No se calcula por falta de valor a financiar o ingreso mensual válido."
        missing_card(missing.loc[VIEW.index], indicator, reason)

# ---------------- Experiencia ----------------
banner("Experiencia", "Historial crediticio: monto máximo solicitado, antigüedad y calificación.", "◉")
exp_license = st.radio("Tipo de licencia", ["Particular", "Público"], horizontal=True, key="rie_exp_license")
with st.container(border=True):
    left, center, right = st.columns([1.05,1.55,.72], gap="medium")
    with left:
        st.markdown("**Reglas de Experiencia**")
        pct_max = st.number_input("Monto máximo sobre valor a financiar (%)", min_value=0.0, max_value=100.0, value=30.0, step=1.0, key="rie_experience_pct")
        exp_rules = pd.DataFrame({"Criterio":["Monto máximo solicitado", "Antigüedad de la obligación", "Calificación del monto máximo"],
            "Calificación RIE":[1,1,2],
            "Regla":[f"Monto máximo > {pct_max:.1f}% del valor a financiar", "Diferencia entre fecha de solicitud e inicio de obligación ≥ 1 año", "Calificación del monto máximo < 4 (categoría B)"]})
        st.dataframe(exp_rules, width="stretch", hide_index=True)
        st.caption("Solo el porcentaje del monto máximo es editable. Calificaciones y demás criterios permanecen fijos.")
    with center:
        st.markdown(f"**Distribución del monto máximo · {exp_license}**")
        max_amount = field("MontoMaxSolicGeneral")
        exp_ratio = max_amount.div(principal.where(principal > 0)).mul(100)
        exp_license_mask = VIEW["licencia_vehiculo"].astype("string").str.upper().eq("PAR" if exp_license == "Particular" else "PUB")
        exp_view = exp_ratio.loc[VIEW.index][exp_license_mask]
        density_chart(exp_view, "Distribución del monto máximo", "% del valor a financiar", [pct_max], f"rie_experience_density_{exp_license}", exp_license)
    with right:
        date_request = pd.to_datetime(DATA.get("FechaProceso", pd.Series(pd.NaT,index=DATA.index)), format="mixed", errors="coerce")
        date_open = pd.to_datetime(DATA.get("FechaAperturaMontoMax", pd.Series(pd.NaT,index=DATA.index)), format="mixed", errors="coerce")
        # Supuesto temporal solicitado: las fechas de apertura faltantes se reemplazan por la fecha de hoy.
        today = pd.Timestamp.today().normalize()
        date_open = date_open.mask(date_open.isna() | (date_open.dt.year <= 1901), today)
        invalid_open = pd.Series(False, index=DATA.index)
        amount_missing = max_amount.isna() | principal.isna() | (principal <= 0)
        age_missing = date_request.isna() | invalid_open
        rating = field("CalificacionMontoMax")
        rating_missing = rating.isna()
        # Para Experiencia se considera sin información si falta cualquiera de los tres datos necesarios.
        missing_exp = amount_missing | age_missing | rating_missing
        missing_card(missing_exp.loc[VIEW.index], "Experiencia", "No se puede evaluar por monto máximo, fecha de apertura o calificación ausentes/no válidos.")

st.markdown("---")
banner("Resultados del RIE", "Puntaje combinado mediante la normalización 3/7, con distribución por licencia.", "▦")

# Construcción del puntaje RIE siguiendo las ponderaciones de Motor_decision.pptx:
# Respaldo: LTV 100% (0-3); Ingresos: PTI/DTI/EI 33,3% cada uno (0-3);
# Experiencia: 100% (0 o 1). Total máximo = 7.
all_licenses = DATA["licencia_vehiculo"].astype("string").str.upper()
vehicle_all = field("ValorVh")
financing_all = principal
ltv_all = financing_all.div(vehicle_all.where(vehicle_all > 0))  # ratio 0-1, no porcentaje

# LTV según tabla de página 10 de la presentación.
ltv_score_all = pd.Series(np.nan, index=DATA.index, dtype=float)
for code, bounds in [("PAR", [(0.0, .70, 3), (.70, .75, 2), (.75, .85, 1), (.85, 1.0, 0)]),
                     ("PUB", [(0.0, .75, 3), (.75, .80, 2), (.80, .90, 1), (.90, 1.0, 0)])]:
    lic_mask = all_licenses.eq(code)
    for lo, hi, score_l in bounds:
        # Los intervalos comparten extremos; se conserva el puntaje del intervalo superior.
        mask = lic_mask & ltv_all.ge(lo) & ltv_all.le(hi)
        ltv_score_all.loc[mask] = score_l

# PTI y DTI: umbrales por licencia y estado civil, páginas 11-12.
# Los ratios se calculan en escala 0-1 (porcentaje / 100).
marital = DATA.get("estado_civil", pd.Series("", index=DATA.index)).astype("string").str.upper().fillna("")
married = marital.str.contains("CASAD|UNION|UNIÓN|LIBRE", regex=True)
particular = all_licenses.eq("PAR")
public = all_licenses.eq("PUB")

# Calificación 0 = tramo de mayor ratio; 1 = intermedio; 2 = menor ratio.
def income_score_by_threshold(values, thresholds):
    out = pd.Series(np.nan, index=DATA.index, dtype=float)
    for mask, (high, mid) in thresholds:
        vals = values.loc[mask]
        out.loc[mask & values.gt(high)] = 0
        out.loc[mask & values.le(high) & values.gt(mid)] = 1
        out.loc[mask & values.le(mid)] = 2
    return out

pti_ratio = pti / 100.0
dti_ratio = dti / 100.0
pti_thresholds = [
    (particular & married, (.50, .25)),
    (particular & ~married, (.45, .20)),
    (public & married, (.55, .35)),
    (public & ~married, (.50, .30)),
]
dti_thresholds = [
    (particular & married, (.55, .40)),
    (particular & ~married, (.50, .35)),
    (public & married, (.70, .50)),
    (public & ~married, (.65, .45)),
]
pti_score = income_score_by_threshold(pti_ratio, pti_thresholds)
dti_score = income_score_by_threshold(dti_ratio, dti_thresholds)
# EI tabla página 12: >18 => 0; 12 < EI <=18 => 1; <=12 => 2.
ei_score = pd.Series(np.nan, index=DATA.index, dtype=float)
ei_score.loc[ei.gt(18)] = 0
ei_score.loc[ei.le(18) & ei.gt(12)] = 1
ei_score.loc[ei.le(12) & ei.ge(0)] = 2

# Ponderación explícita de 33,3% por subítem y reescalado del promedio 0-2 al
# componente Ingresos 0-3, como define la tabla general RIE (página 9).
income_scores = pd.concat([pti_score, dti_score, ei_score], axis=1)
income_component = (income_scores.mean(axis=1, skipna=False) * 1.5)

# Experiencia: según página 13, deben cumplirse los criterios de monto >30% del
# valor a financiar, antigüedad >=1 año y calificación <4. Por instrucción del usuario,
# se asume provisionalmente que la garantía 1 tiene licencia Pública; por tanto, el
# requisito adicional de garantía pública se considera cumplido para el segmento Público.
max_amount_all = field("MontoMaxSolicGeneral")
exp_ratio_all = max_amount_all.div(principal.where(principal > 0)).mul(100)
date_request_all = pd.to_datetime(DATA.get("FechaProceso", pd.Series(pd.NaT,index=DATA.index)), format="mixed", errors="coerce")
date_open_all = pd.to_datetime(DATA.get("FechaAperturaMontoMax", pd.Series(pd.NaT,index=DATA.index)), format="mixed", errors="coerce")
# Supuesto temporal solicitado: imputar la fecha de hoy cuando la fecha de apertura falta o no es válida.
today = pd.Timestamp.today().normalize()
date_open_all = date_open_all.mask(date_open_all.isna() | (date_open_all.dt.year <= 1901), today)
rating_all = field("CalificacionMontoMax")
exp_amount_ok = exp_ratio_all.gt(float(st.session_state.get("rie_experience_pct", 30.0)))
exp_age_ok = date_request_all.notna() & date_open_all.notna() & date_open_all.dt.year.gt(1901) & ((date_request_all - date_open_all).dt.days >= 365)
exp_rating_ok = rating_all.lt(4)
exp_eval = exp_ratio_all.notna() & date_request_all.notna() & date_open_all.notna() & date_open_all.dt.year.gt(1901) & rating_all.notna() & principal.gt(0)
exp_pass = exp_amount_ok & exp_age_ok & exp_rating_ok
experience_component = pd.Series(np.where(exp_eval, exp_pass.astype(float), np.nan), index=DATA.index, dtype=float)

score_total = ltv_score_all + income_component + experience_component
score_total = score_total.where(score_total.between(0, 7) & score_total.notna()).round()
score_total = score_total.astype("Int64")
# Tabla de normalización literal de página 9: 0-1=>0, 2-3=>1, 4-5=>2, 6-7=>3.
normalization_map = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 3}
normalized = score_total.map(normalization_map).astype("Int64")
category = normalized.map({0: "AE", 1: "A", 2: "AA", 3: "AA"})
results = pd.DataFrame({"Puntaje": score_total, "Normalización": normalized, "Categoría": category, "Licencia": all_licenses})
results = results.loc[VIEW.index]

result_rows = []
for score in range(8):
    norm = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 3}[score]
    cat = {0: "AE", 1: "A", 2: "AA", 3: "AA"}[norm]
    row = {"Puntaje": score, "Normalización": norm, "Categoría": cat}
    total_n = 0
    total_denominator = 0
    for lic, code in [("Particular", "PAR"), ("Público", "PUB")]:
        subset = results[results["Licencia"].eq(code)]
        valid_subset = subset[subset["Puntaje"].notna()]
        n = int(valid_subset[valid_subset["Puntaje"].eq(score)].shape[0])
        denominator = len(valid_subset)
        total_n += n
        total_denominator += denominator
        row[f"Cantidad ({lic})"] = n
        row[f"% ({lic})"] = (n / denominator * 100) if denominator else 0.0
    row["Total"] = total_n
    row["% Total"] = (total_n / total_denominator * 100) if total_denominator else 0.0
    result_rows.append(row)

# Fila de totales: suma de evaluables por licencia y sobre el total del perfil seleccionado.
particular_total = int(results.loc[results["Licencia"].eq("PAR"), "Puntaje"].notna().sum())
public_total = int(results.loc[results["Licencia"].eq("PUB"), "Puntaje"].notna().sum())
all_total = particular_total + public_total
result_rows.append({"Puntaje": "Total", "Normalización": "–", "Categoría": "–",
    "Cantidad (Particular)": particular_total, "% (Particular)": 100.0 if particular_total else 0.0,
    "Cantidad (Público)": public_total, "% (Público)": 100.0 if public_total else 0.0,
    "Total": all_total, "% Total": 100.0 if all_total else 0.0})

st.markdown("**Resultado del RIE por puntaje y categoría**")
st.caption("Cantidades y porcentajes calculados desde la base para el perfil seleccionado. Los registros sin puntaje calculable se excluyen de los denominadores.")
result_table = pd.DataFrame(result_rows)
# La fila Total mezcla etiquetas con números; homogeneizar estas columnas evita ArrowInvalid.
result_table["Puntaje"] = result_table["Puntaje"].astype(str)
result_table["Normalización"] = result_table["Normalización"].astype(str)
st.dataframe(result_table, width="stretch", hide_index=True,
    column_config={
        "% (Particular)": st.column_config.NumberColumn("% (Particular)", format="%.2f%%"),
        "% (Público)": st.column_config.NumberColumn("% (Público)", format="%.2f%%"),
        "% Total": st.column_config.NumberColumn("% Total", format="%.2f%%"),
    })
valid_particular = results[results["Licencia"].eq("PAR")]["Puntaje"].notna().sum()
valid_public = results[results["Licencia"].eq("PUB")]["Puntaje"].notna().sum()
col1, col2, col3 = st.columns(3)
col1.metric("Registros con puntaje calculable", format_n(int(results["Puntaje"].notna().sum())))
col2.metric("Particular evaluables", format_n(int(valid_particular)))
col3.metric("Público evaluables", format_n(int(valid_public)))
st.caption("Los porcentajes de la tabla se calculan dentro de cada tipo de licencia y sobre los registros con puntaje RIE calculable. Los registros sin información suficiente se excluyen del denominador.")
if all_licenses.eq("PUB").any():
    st.info("Supuesto provisional: se considera que la garantía 1 tiene licencia Pública, por lo que el requisito de garantía pública para Experiencia se toma como cumplido.")
st.caption("Notas: las fechas faltantes o no válidas de FechaAperturaMontoMax se reemplazan temporalmente por la fecha de hoy para calcular Experiencia; por ello, esos registros no cumplirán el requisito de antigüedad mínima de un año. Los cambios de rangos y parámetros son temporales durante la sesión. Las calificaciones de PTI/DTI/EI aplican los umbrales de la PPT por licencia y estado civil. La normalización sigue la tabla de la PPT: puntajes 0–1→0, 2–3→1, 4–5→2 y 6–7→3. El plazo de financiación se mantiene en 60 meses por defecto hasta incorporar la variable al conjunto de datos.")
