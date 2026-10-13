from pathlib import Path

import pandas as pd
import streamlit as st

from src.data_loader import load_data, prepare_data, ROOT
from src.common import quantile_categories
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Decisión", page_icon="▦", layout="wide")
apply_finanzauto_theme()

st.title("7. Decisión")
st.caption(
    "Consulta las combinaciones de Score, Exposición y Riesgo y edita su decisión. "
    "Los indicadores resumen los registros del perfil seleccionado."
)

# Filtro de perfil: los conteos y porcentajes se calculan dentro de la población elegida.
df = prepare_data(load_data())
profiles = sorted(df["perfil_label"].dropna().astype(str).unique().tolist()) if "perfil_label" in df else []
selected_profile = st.selectbox("Perfil", ["Todos"] + profiles, key="decision_profile")
data = df.copy()
if selected_profile != "Todos":
    data = data[data["perfil_label"].astype(str) == selected_profile]

population = len(data)
st.caption(f"Población del perfil seleccionado: {population:,} registros".replace(",", "."))
if data.empty:
    st.warning("No hay registros para el perfil seleccionado.")
    st.stop()

# Lee la metodología inicial de Excel hasta la columna Decisión.
workbook = ROOT / "data" / "asignacion_decision.xlsx"
try:
    methodology = pd.read_excel(workbook, sheet_name="Metodologia", usecols="A:D")
    methodology.columns = ["Scores", "Exposición", "Riesgo", "Decisión"]
    methodology = methodology.ffill()
    methodology = methodology.dropna(subset=["Scores", "Exposición", "Riesgo"])
    for col in ["Scores", "Exposición", "Riesgo", "Decisión"]:
        methodology[col] = methodology[col].astype("string").str.strip()
    methodology = methodology.drop_duplicates(subset=["Scores", "Exposición", "Riesgo"], keep="first")
except Exception as exc:
    st.error(f"No fue posible leer la hoja Metodologia: {exc}")
    st.stop()

# Clasificación de registros vigente en esta versión (provisional).
for source, target in [("acierta", "cat_Scores"), ("cuota_inicial", "cat_Exposición")]:
    data[target] = quantile_categories(data[source]) if source in data.columns else pd.NA
if "EndeudamientoSaldoSin" in data.columns:
    values = pd.to_numeric(data["EndeudamientoSaldoSin"], errors="coerce")
    valid_risk = values.notna()
    data["cat_Riesgo"] = pd.NA
    try:
        if valid_risk.sum() >= 3:
            data.loc[valid_risk, "cat_Riesgo"] = pd.qcut(
                values[valid_risk].rank(method="first"), q=3, labels=["AA", "A", "AE"]
            ).astype(str)
    except (ValueError, TypeError):
        pass
else:
    data["cat_Riesgo"] = pd.NA

st.warning(
    "La clasificación de Score y Exposición se calcula provisionalmente por cuantiles. "
    "Riesgo utiliza EndeudamientoSaldoSin como aproximación porque la base no contiene una variable RIE explícita. "
    "Valida estas reglas antes de usar los resultados para decisiones crediticias reales."
)

# Decisiones temporales: no se implementa persistencia en esta etapa.
key_cols = ["Scores", "Exposición", "Riesgo"]
valid_decisions = ["AA", "A", "AE"]

# Cuenta registros por combinación antes de mostrar la única tabla editable.
valid = data.dropna(subset=["cat_Scores", "cat_Exposición", "cat_Riesgo"]).copy()
valid = valid.rename(columns={
    "cat_Scores": "Scores",
    "cat_Exposición": "Exposición",
    "cat_Riesgo": "Riesgo",
})
counts = valid.groupby(key_cols, observed=False).size().rename("Cantidad (#)").reset_index()
result = methodology.merge(counts, on=key_cols, how="left")
result["Cantidad (#)"] = result["Cantidad (#)"].fillna(0).astype(int)
result["Porcentaje (%)"] = (result["Cantidad (#)"] / population * 100).round(2)
result = result[key_cols + ["Decisión", "Cantidad (#)", "Porcentaje (%)"]]

st.subheader("Matriz de decisión")
st.caption("Edita la columna Decisión. Cantidad y porcentaje se calculan automáticamente para cada combinación; el porcentaje usa como denominador la población del perfil seleccionado.")
edited = st.data_editor(
    result,
    key="decision_matrix_editor",
    width="stretch",
    hide_index=True,
    num_rows="fixed",
    disabled=key_cols + ["Cantidad (#)", "Porcentaje (%)"],
    column_config={
        "Decisión": st.column_config.SelectboxColumn(
            "Decisión (editable)", options=valid_decisions, required=True
        ),
        "Cantidad (#)": st.column_config.NumberColumn(format="%d"),
        "Porcentaje (%)": st.column_config.NumberColumn(format="%.2f%%"),
    },
)

# Tarjetas resumen: los valores se calculan en tiempo real a partir de la tabla editable.
chart_data = edited.copy()
chart_data["Decisión"] = chart_data["Decisión"].astype("string").str.strip()
chart_data = chart_data[chart_data["Decisión"].isin(valid_decisions)]
summary = chart_data.groupby("Decisión", as_index=False).agg(Registros=("Cantidad (#)", "sum"))
summary_map = summary.set_index("Decisión")["Registros"].to_dict() if not summary.empty else {}

approved_count = int(summary_map.get("A", 0))
study_count = int(summary_map.get("AE", 0))
approved_pct = (approved_count / population * 100) if population else 0
study_pct = (study_count / population * 100) if population else 0

st.subheader("Resumen de decisiones")
card_a, card_ae = st.columns(2, gap="medium")
with card_a:
    with st.container(border=True):
        st.markdown("<div style='color:#064B39;font-weight:650;font-size:1rem'>Aprobados (A)</div>", unsafe_allow_html=True)
        metric_count, metric_pct = st.columns(2)
        with metric_count:
            st.metric("Cantidad (#)", f"{approved_count:,}".replace(",", "."))
        with metric_pct:
            st.metric("Porcentaje (%)", f"{approved_pct:.2f}%")
with card_ae:
    with st.container(border=True):
        st.markdown("<div style='color:#15966A;font-weight:650;font-size:1rem'>A Estudio (AE)</div>", unsafe_allow_html=True)
        metric_count, metric_pct = st.columns(2)
        with metric_count:
            st.metric("Cantidad (#)", f"{study_count:,}".replace(",", "."))
        with metric_pct:
            st.metric("Porcentaje (%)", f"{study_pct:.2f}%")
