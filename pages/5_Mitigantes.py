import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common import financed_amount, load_config, monthly_payment, save_config
from src.data_loader import load_data, prepare_data
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Mitigantes", page_icon="◫", layout="wide")
apply_finanzauto_theme()

DATA = prepare_data(load_data()).reset_index(drop=True)
GREEN = "#087A55"
TEXT = "#0A2F4A"
AVALISTAS = [1, 2, 3]
GARANTIAS = [1, 2, 3]
# Reglas fijas de idoneidad de la garantía (no editables).
GARANTIA_MAX_ANTIGUEDAD = 10
CURRENT_YEAR = pd.Timestamp.today().year
GROUP_ORDER = ["Sin mitigante", "Solo avalista", "Solo garantía", "Avalista y garantía"]

def format_n(n):
    return f"{int(n):,}".replace(",", ".")

def format_pct(part, total):
    return f"{part / total * 100:.1f}%" if total else "0.0%"

def threshold_histogram(series, xlabel, threshold, key, x_max=None):
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    total_values = len(values)
    if x_max is not None:
        values = values[values <= x_max]
        note = f"{format_n(len(values))} de {format_n(total_values)} registros; {format_n(total_values - len(values))} mayores a {x_max:g} no se muestran."
    else:
        # Se recorta el 1 % superior para que los valores extremos no aplasten la distribución.
        if len(values) > 20:
            values = values[values <= values.quantile(.99)]
        note = f"{format_n(len(values))} registros con valor calculable (sin el 1 % superior)."
    bins = dict(xbins=dict(start=0, end=x_max, size=x_max / 40)) if x_max is not None else dict(nbinsx=40)
    fig = go.Figure(go.Histogram(x=values, **bins, marker_color="#43BD83",
        marker_line=dict(color=GREEN, width=0.4), opacity=0.9,
        hovertemplate=f"{xlabel}: %{{x}}<br>Registros: %{{y}}<extra></extra>"))
    fig.add_vline(x=threshold, line_width=1.5, line_dash="dash", line_color=TEXT,
        annotation_text=f"Mínimo {threshold:g}", annotation_position="top")
    fig.update_layout(height=270, margin=dict(l=8, r=8, t=30, b=35), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT, size=10),
        xaxis=dict(title=xlabel, showgrid=False, range=[0, x_max] if x_max is not None else None),
        yaxis=dict(title="Registros", gridcolor="#e5eee9"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)
    st.caption(note)

def config_editor(name, fields):
    """Campos editables de config/<name>.json; los cambios aplican en sesión hasta guardarlos."""
    saved = load_config(name)
    values = {}
    for field, (label, kwargs) in fields.items():
        values[field] = st.number_input(label, value=type(kwargs["step"])(saved[field]), key=f"mit_{name}_{field}", **kwargs)
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Restablecer", key=f"mit_{name}_reset", width="stretch"):
            for field in fields:
                st.session_state.pop(f"mit_{name}_{field}", None)
            st.rerun()
    with b2:
        if st.button("Guardar", key=f"mit_{name}_save", type="primary", width="stretch"):
            save_config(name, values)
            st.success(f"Valores guardados en config/{name}.json")
    return values

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Mitigantes: avalistas y garantías</h1>
  <p>Evalúa qué créditos cuentan con un avalista o una garantía que cumple los criterios definidos en config/avalista.json y config/garantia.json.</p>
</div>
""", unsafe_allow_html=True)

profile_options = sorted(DATA["perfil_label"].dropna().astype(str).unique().tolist())
c_profile, c_term = st.columns(2, gap="medium")
with c_profile:
    selected_profile = st.selectbox("Perfil", ["Todos"] + profile_options, key="mit_profile")
with c_term:
    # Mismo supuesto que en RIE: el plazo no viene en la base.
    term_months = st.number_input("Plazo de financiación para la cuota (meses)", min_value=1, max_value=120,
        value=60, step=1, key="mit_term_months")
VIEW = DATA if selected_profile == "Todos" else DATA[DATA["perfil_label"].eq(selected_profile)]
VIEW = VIEW.copy()
VIEW["valor_financiar"] = financed_amount(VIEW)
VIEW["cuota_calculada"] = monthly_payment(VIEW, term_months)
total = len(VIEW)

# ---------------- Avalistas ----------------
st.markdown('<div class="fa-section">Avalistas</div>', unsafe_allow_html=True)
left, right = st.columns([1, 2.4], gap="medium")
with left:
    with st.container(border=True):
        st.markdown("**Criterios del avalista**")
        aval_cfg = config_editor("avalista", {
            "acierta": ("Acierta mínimo", dict(min_value=0, max_value=1000, step=1)),
            "capacidad_pago": ("Capacidad de pago mínima (ingreso / cuota)", dict(min_value=0.0, max_value=100.0, step=0.05, format="%.2f")),
        })
        st.caption("Capacidad de pago = ingreso del avalista / cuota calculada del crédito. "
                   "Un avalista cumple si alcanza ambos mínimos; el crédito queda mitigado si al menos uno cumple.")

# Una fila por avalista registrado.
aval_frames = []
for i in AVALISTAS:
    acierta = pd.to_numeric(VIEW[f"Avalista{i}Acierta"], errors="coerce")
    income = pd.to_numeric(VIEW[f"Avalista{i}IngresoTotalMensual"].astype("string"), errors="coerce")
    present = acierta.notna() | income.notna()
    aval_frames.append(pd.DataFrame({
        "credito_idx": VIEW.index[present], "avalista": i,
        "acierta": acierta[present].to_numpy(), "ingreso": income[present].to_numpy(),
        "cuota": VIEW.loc[present, "cuota_calculada"].to_numpy(),
    }))
avales = pd.concat(aval_frames, ignore_index=True)
avales["capacidad_pago"] = avales["ingreso"].div(avales["cuota"].where(avales["cuota"] > 0))
avales["cumple_acierta"] = avales["acierta"].ge(aval_cfg["acierta"]).fillna(False).astype(bool)
avales["cumple_capacidad"] = avales["capacidad_pago"].ge(aval_cfg["capacidad_pago"]).fillna(False).astype(bool)
avales["cumple"] = avales["cumple_acierta"] & avales["cumple_capacidad"]
VIEW["tiene_avalista"] = VIEW.index.isin(avales["credito_idx"])
VIEW["avalista_cumple"] = VIEW.index.isin(avales.loc[avales["cumple"], "credito_idx"])

with right:
    m1, m2, m3, m4 = st.columns(4)
    n_with = int(VIEW["tiene_avalista"].sum())
    m1.metric("Créditos con avalista", format_n(n_with), format_pct(n_with, total), delta_color="off")
    m2.metric("Avalistas que cumplen Acierta", format_n(avales["cumple_acierta"].sum()), format_pct(avales["cumple_acierta"].sum(), len(avales)), delta_color="off")
    m3.metric("Avalistas que cumplen capacidad", format_n(avales["cumple_capacidad"].sum()), format_pct(avales["cumple_capacidad"].sum(), len(avales)), delta_color="off")
    n_ok = int(VIEW["avalista_cumple"].sum())
    m4.metric("Créditos con avalista que cumple", format_n(n_ok), format_pct(n_ok, n_with), delta_color="off")
    st.caption(f"{format_n(len(avales))} avalistas registrados. Los porcentajes de avalistas son sobre ese total; "
               "el de créditos que cumplen es sobre los créditos con avalista.")
    g1, g2 = st.columns(2, gap="medium")
    with g1:
        st.markdown("**Acierta del avalista**")
        threshold_histogram(avales["acierta"], "Acierta", aval_cfg["acierta"], "mit_hist_acierta")
    with g2:
        st.markdown("**Capacidad de pago (ingreso / cuota)**")
        threshold_histogram(avales["capacidad_pago"], "Ingreso avalista / cuota", aval_cfg["capacidad_pago"], "mit_hist_capacidad", x_max=1)

# ---------------- Garantías ----------------
st.markdown('<div class="fa-section">Garantías</div>', unsafe_allow_html=True)
left, right = st.columns([1, 2.4], gap="medium")
with left:
    with st.container(border=True):
        st.markdown("**Criterio de la garantía**")
        gar_cfg = config_editor("garantia", {
            "valor": ("Valor mínimo (garantía / valor a financiar)", dict(min_value=0.0, max_value=100.0, step=0.05, format="%.2f")),
        })
        st.caption("Valor = suma de las garantías idóneas (RPV1–RPV3) / valor a financiar del crédito. "
                   "El crédito queda mitigado si alcanza el mínimo.")
        st.markdown("**Reglas fijas de idoneidad**")
        st.caption(f"Prendado = NO y antigüedad de máximo {GARANTIA_MAX_ANTIGUEDAD} años ({CURRENT_YEAR} − año modelo). "
                   "Si falta el estado de prenda o el año modelo, la garantía no es idónea.")

registered = pd.Series(0.0, index=VIEW.index)
eligible = pd.Series(0.0, index=VIEW.index)
for i in GARANTIAS:
    value = pd.to_numeric(VIEW[f"RPV{i}Valor"].astype("string"), errors="coerce").fillna(0)
    model_year = pd.to_numeric(VIEW[f"RPV{i}Modelo"], errors="coerce")
    # Un campo vacío no permite verificar la regla: la garantía no es idónea.
    not_pledged = VIEW[f"RPV{i}Prendado"].astype("string").str.strip().str.upper().eq("NO").fillna(False)
    recent = (CURRENT_YEAR - model_year).le(GARANTIA_MAX_ANTIGUEDAD).fillna(False)
    registered += value
    eligible += value.where(not_pledged & recent, 0)
VIEW["tiene_garantia"] = registered.gt(0)
VIEW["garantia_idonea"] = eligible.gt(0)
VIEW["cobertura_garantia"] = eligible.where(VIEW["garantia_idonea"]).div(VIEW["valor_financiar"].where(VIEW["valor_financiar"] > 0))
VIEW["garantia_cumple"] = VIEW["cobertura_garantia"].ge(gar_cfg["valor"]).fillna(False).astype(bool)

with right:
    m1, m2, m3 = st.columns(3)
    n_gar = int(VIEW["tiene_garantia"].sum())
    m1.metric("Créditos con garantía", format_n(n_gar), format_pct(n_gar, total), delta_color="off")
    n_gar_idonea = int(VIEW["garantia_idonea"].sum())
    m2.metric("Créditos con garantía idónea", format_n(n_gar_idonea), format_pct(n_gar_idonea, n_gar), delta_color="off")
    n_gar_ok = int(VIEW["garantia_cumple"].sum())
    m3.metric("Créditos con garantía que cumple", format_n(n_gar_ok), format_pct(n_gar_ok, n_gar), delta_color="off")
    st.caption("Los porcentajes de garantía idónea y que cumple son sobre los créditos con garantía registrada.")
    st.markdown("**Valor de la garantía / valor a financiar**")
    threshold_histogram(VIEW["cobertura_garantia"], "Garantía / valor a financiar", gar_cfg["valor"], "mit_hist_garantia", x_max=1)

# ---------------- Resumen ----------------
st.markdown('<div class="fa-section">Resumen de mitigantes</div>', unsafe_allow_html=True)
aval_ok, gar_ok = VIEW["avalista_cumple"], VIEW["garantia_cumple"]
VIEW["grupo_mitigante"] = np.select([aval_ok & gar_ok, aval_ok, gar_ok],
    ["Avalista y garantía", "Solo avalista", "Solo garantía"], "Sin mitigante")
mora = pd.to_numeric(VIEW["mora_max_15m"], errors="coerce")
summary = (VIEW.assign(mora_60=mora.gt(60), mora_90=mora.gt(90))
    .groupby("grupo_mitigante").agg(Créditos=("credito", "size"), mora_60=("mora_60", "mean"), mora_90=("mora_90", "mean"))
    .reindex(GROUP_ORDER).fillna(0))
summary["% créditos"] = summary["Créditos"] / total * 100 if total else 0.0
summary[["mora_60", "mora_90"]] *= 100
summary = summary.rename(columns={"mora_60": "% mora > 60 días", "mora_90": "% mora > 90 días"}).reset_index(names="Mitigante")
st.dataframe(summary[["Mitigante", "Créditos", "% créditos", "% mora > 60 días", "% mora > 90 días"]],
    width="stretch", hide_index=True, column_config={
        "Créditos": st.column_config.NumberColumn(format="%d"),
        "% créditos": st.column_config.NumberColumn(format="%.2f%%"),
        "% mora > 60 días": st.column_config.NumberColumn(format="%.2f%%"),
        "% mora > 90 días": st.column_config.NumberColumn(format="%.2f%%"),
    })
st.caption("Solo cuentan los mitigantes que cumplen los criterios. La mora corresponde a la mora máxima en los "
           "primeros 15 meses (o hasta el corte), para todos los créditos del perfil seleccionado.")
