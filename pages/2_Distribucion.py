import json
import pandas as pd
import streamlit as st

from src.data_loader import OCUPACION_AVALISTA1, OCUPACIONES_POR_AVALISTA, SEGMENTACION_PATH
from src.distribucion import (PAGE_STYLE, SEGMENT_ORDER, SIN_OCUPACION, format_n, format_pct,
                              load_distribution_data, year_filter)

st.set_page_config(page_title="Distribución: segmentos y ocupaciones", page_icon="📊", layout="wide")

from src.theme import apply_finanzauto_theme
apply_finanzauto_theme()

base, df = load_distribution_data()
st.markdown(PAGE_STYLE, unsafe_allow_html=True)

st.title("Distribución: segmentos y ocupaciones")
st.write(
    "Cantidad de créditos por segmento final y ocupaciones que lo componen. "
    "Las gráficas de distribución por variable están en la hoja **Distribucion graficas**."
)

apply_filters = year_filter(df, key="distribution_year")
filtered = apply_filters(df.copy())
filtered_base = apply_filters(base)

# Tarjetas por segmento; la de sin ocupación principal solo aparece si hay registros.
# Los porcentajes son sobre todos los registros del periodo, incluidos los sin ocupación.
counts = filtered_base["segmentacion"].value_counts()
cards = [(s, int(counts.get(s, 0))) for s in SEGMENT_ORDER]
if counts.get("Sin dato", 0):
    cards.append((SIN_OCUPACION, int(counts["Sin dato"])))
total = len(filtered_base)
for col, (label, n) in zip(st.columns(len(cards)), cards):
    col.metric(label, format_n(n), format_pct(n, total), delta_color="off")

st.caption(f"Registros según filtros: {format_n(len(filtered))} con segmento"
           + (f" y {format_n(counts['Sin dato'])} sin ocupación principal (fuera del análisis)." if counts.get("Sin dato", 0) else "."))

# Las ocupaciones se agrupan por el nombre escrito en config/segmentacion.json,
# sin importar mayúsculas o espacios.
with open(SEGMENTACION_PATH, encoding="utf-8") as f:
    canonical = {" ".join(k.split()).casefold(): k for k in json.load(f)}
canonical.update(OCUPACIONES_POR_AVALISTA)

def canonical_occupation(value):
    if pd.isna(value) or not str(value).strip():
        return pd.NA
    return canonical.get(" ".join(str(value).split()).casefold(), str(value).strip())

TITULARES_AVALISTA = list(OCUPACIONES_POR_AVALISTA.values())

st.markdown('<h3 class="section-title">Ocupaciones por segmento</h3>', unsafe_allow_html=True)
if "descripcion_ocupacion" in filtered.columns and not filtered.empty:
    occ = filtered.assign(ocupacion=filtered["descripcion_ocupacion"].map(canonical_occupation))
    occ_table = (occ.groupby(["segmentacion", "ocupacion"]).size()
                 .rename("Créditos").reset_index()
                 .sort_values(["segmentacion", "Créditos"], ascending=[True, False]))
    occ_table["% del segmento"] = (occ_table["Créditos"] / occ_table.groupby("segmentacion")["Créditos"].transform("sum") * 100).round(1)
    occ_table["% del total"] = (occ_table["Créditos"] / occ_table["Créditos"].sum() * 100).round(1)
    occ_table = occ_table.rename(columns={"segmentacion": "Segmento", "ocupacion": "Ocupación"})
    st.dataframe(occ_table, width="stretch", hide_index=True)
else:
    st.info("Sin datos para los filtros seleccionados.")
st.caption(
    "Las ocupaciones sin segmento propio (Ama de Casa, Universitario) se ubican en el segmento de la ocupación "
    "del avalista 1; si el avalista tampoco tiene segmento propio o no tiene dato, quedan en Independiente Informal."
)

st.markdown('<h3 class="section-title">Ocupación del avalista 1 para titulares Ama de Casa y Universitario</h3>', unsafe_allow_html=True)
aval_col = OCUPACION_AVALISTA1
if aval_col not in filtered.columns:
    # prepare_data solo crea la columna si la base trae el código de ocupación del avalista 1.
    similares = [str(c) for c in filtered.columns if "aval" in str(c).casefold() or "ocup" in str(c).casefold()]
    st.warning(
        "No se encontró en la base la columna `Avalista1Ocupacion`, así que no se pudo crear "
        f"`{OCUPACION_AVALISTA1}`. Columnas parecidas en la base: "
        + (", ".join(f"`{c}`" for c in similares) if similares else "ninguna")
    )
else:
    tit = filtered.assign(
        titular=filtered["descripcion_ocupacion"].map(canonical_occupation),
        avalista=filtered[aval_col].map(canonical_occupation).fillna("Sin avalista / sin dato"),
    )
    tit = tit[tit["titular"].isin(TITULARES_AVALISTA)]
    if tit.empty:
        st.info("Sin datos para los filtros seleccionados.")
    else:
        aval_table = (tit.groupby(["titular", "avalista"]).size()
                      .rename("Créditos").reset_index()
                      .sort_values(["titular", "Créditos"], ascending=[True, False]))
        aval_table["% dentro de la ocupación del titular"] = (
            aval_table["Créditos"] / aval_table.groupby("titular")["Créditos"].transform("sum") * 100).round(1)
        aval_table = aval_table.rename(columns={"titular": "Ocupación titular", "avalista": "Ocupación avalista 1"})
        st.dataframe(aval_table, width="stretch", hide_index=True)
        st.caption("'Sin avalista / sin dato' agrupa los créditos sin ocupación registrada para el avalista 1.")
