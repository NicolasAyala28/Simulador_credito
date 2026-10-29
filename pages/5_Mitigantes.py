import numpy as np
import pandas as pd
import streamlit as st

from src.common import load_config
from src.data_loader import load_data, prepare_data
from src.decision import (A_ESTUDIO, APROBADO, CONDICIONES,
    GARANTIA_MAX_ANTIGUEDAD, GARANTIA_MIN_COBERTURA, RIE_ORDER, SEGMENT_ORDER, LICENSE_ORDER, CONDITION_ORDER,
    TREE_LEVELS, branch_key, credit_mitigants, final_decisions)
from src.parametros import arbol_decisions, mitigante_conditions, version_sidebar
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Mitigantes", page_icon="◫", layout="wide")
apply_finanzauto_theme()

CUMPLE, NO_CUMPLE = "Decisión - Cumple", "Decisión - No cumple"

def format_n(n):
    return f"{int(n):,}".replace(",", ".")

def format_pct(part, total):
    return f"{part / total * 100:.1f}%" if total else "0.0%"

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Mitigantes: avalistas y garantías</h1>
  <p>Créditos con avalistas y garantías idóneos, y cumplimiento de las ramas del árbol con decisión "Condiciones".</p>
</div>
""", unsafe_allow_html=True)

# ---------------- Idoneidad por crédito ----------------
aval_cfg = load_config("avalista")
gar_cfg = load_config("garantia")
DATA = credit_mitigants(prepare_data(load_data()).reset_index(drop=True), aval_cfg, gar_cfg)

# ---------------- Tarjetas ----------------
segment_options = ["Todos"] + [s for s in SEGMENT_ORDER if DATA["Segmento"].eq(s).any()]
# Las tarjetas van antes del filtro pero dependen de él: se lee el valor elegido en la sesión.
selected_segment = st.session_state.get("mit_segmento", "Todos")
if selected_segment not in segment_options:
    selected_segment = "Todos"
VIEW = DATA if selected_segment == "Todos" else DATA[DATA["Segmento"].eq(selected_segment)]
total = len(VIEW)
cards = [
    ("Créditos con avalista(s) idóneo(s)", VIEW["avalista_idoneo"]),
    ("Créditos con garantía(s) idónea(s)", VIEW["garantia_idonea"]),
    ("Créditos con avalista(s) y garantía(s) idóneos", VIEW["avalista_idoneo"] & VIEW["garantia_idonea"]),
]
for col, (label, mask) in zip(st.columns(3, gap="medium"), cards):
    n = int(mask.sum())
    col.metric(label, format_n(n), format_pct(n, total), delta_color="off", border=True)
st.caption(f"Porcentajes sobre {format_n(total)} créditos del segmento seleccionado. "
           f"Avalista idóneo: Acierta ≥ {aval_cfg['acierta']:g} y capacidad de pago (ingreso / cuota) ≥ "
           f"{aval_cfg['capacidad_pago']:g}. Garantía idónea: no prendada, máximo {GARANTIA_MAX_ANTIGUEDAD} años y valor "
           f"superior al {gar_cfg['valor'] * 100:g}% del valor del vehículo; el crédito la tiene si sus garantías idóneas "
           f"suman más del {GARANTIA_MIN_COBERTURA * 100:g}% del valor a financiar (ValorVh − MontoCtaInicial).")

# ---------------- Filtro ----------------
st.selectbox("Segmento", segment_options, index=segment_options.index(selected_segment), key="mit_segmento")

# ---------------- Ramas con "Condiciones" ----------------
st.markdown('<div class="fa-section">Ramas del árbol con decisión "Condiciones"</div>', unsafe_allow_html=True)
decisions = arbol_decisions()
conditions = mitigante_conditions()
# Decisión final de cada crédito con rama completa: la de su rama en Árbol; en las ramas con
# "Condiciones", Aprobado si tiene los mitigantes exigidos y A estudio si no.
BRANCHED = final_decisions(VIEW, decisions, conditions)

branches = [k.split(" | ") for k, v in decisions.items() if v == CONDICIONES]
table = pd.DataFrame(branches, columns=TREE_LEVELS)
if selected_segment != "Todos":
    table = table[table["Segmento"].eq(selected_segment)]
if table.empty:
    st.info('No hay ramas con decisión "Condiciones" para este segmento. Asígnalas en la columna Decisión de la hoja Árbol.')
else:
    order = {level: {v: i for i, v in enumerate(values)} for level, values in
             zip(TREE_LEVELS, [SEGMENT_ORDER, RIE_ORDER, LICENSE_ORDER, CONDITION_ORDER])}
    table = table.sort_values(TREE_LEVELS, key=lambda s: s.map(order[s.name])).reset_index(drop=True)
    keys = table.apply(branch_key, axis=1)
    table["Avalista"] = [int(conditions.get(k, {}).get("avalista", 0)) for k in keys]
    table["Garantía"] = [int(conditions.get(k, {}).get("garantia", 0)) for k in keys]
    # Cumple: % de créditos de la rama con los mitigantes exigidos; las ramas 0/0 no se evalúan.
    rate = BRANCHED.groupby("rama")["cumple"].agg(lambda c: c.astype(float).mean() * 100 if c.notna().any() else np.nan)
    table[CUMPLE] = keys.map(rate).astype(float)
    table[NO_CUMPLE] = 100 - table[CUMPLE]

    edited = st.data_editor(table, width="stretch", hide_index=True, num_rows="fixed",
        height=min(38 + 35 * len(table), 720), key=f"mit_condiciones_editor_{selected_segment}",
        disabled=TREE_LEVELS + [CUMPLE, NO_CUMPLE],
        column_config={"Avalista": st.column_config.SelectboxColumn("Avalista", options=[1, 0], required=True),
                       "Garantía": st.column_config.SelectboxColumn("Garantía", options=[1, 0], required=True),
                       CUMPLE: st.column_config.NumberColumn(CUMPLE, format="%.1f%%"),
                       NO_CUMPLE: st.column_config.NumberColumn(NO_CUMPLE, format="%.1f%%")})
    changed = False
    for key, aval, gar in zip(keys, edited["Avalista"], edited["Garantía"]):
        new = {"avalista": int(aval), "garantia": int(gar)}
        if conditions.get(key, {"avalista": 0, "garantia": 0}) != new:
            conditions[key] = new
            changed = True
    # Al editar Avalista o Garantía se recalculan las columnas de cumplimiento y las tarjetas.
    if changed:
        st.rerun()

    st.caption("Avalista y Garantía (1/0) definen el mitigante exigido a cada rama: con un 1 se exige ese mitigante y con "
               "ambos en 1 se exigen los dos. Decisión - Cumple es el % de créditos de la rama que tienen los mitigantes "
               "exigidos y Decisión - No cumple el resto. Las ramas con ambos en 0 no se evalúan. Se guardan con "
               "«Guardar como nueva versión» en la barra lateral.")

# ---------------- Decisión final ----------------
st.markdown('<div class="fa-section">Decisión final</div>', unsafe_allow_html=True)
final = {label: BRANCHED["decision_final"].eq(label) for label in [APROBADO, A_ESTUDIO]}
total_branched = len(BRANCHED)
for col, (label, mask) in zip(st.columns(2, gap="medium"), final.items()):
    n = int(mask.sum())
    col.metric(label, format_n(n), format_pct(n, total_branched), delta_color="off", border=True)
n_rest = total_branched - int(final["Aprobado"].sum() + final["A estudio"].sum())
st.caption(f"Porcentajes sobre {format_n(total_branched)} créditos del segmento con rama completa en el árbol (RIE calculable). "
           "Aprobado: ramas con decisión Aprobado en Árbol más los créditos de ramas con Condiciones que cumplen los "
           "mitigantes exigidos. A estudio: ramas con decisión A estudio más los que no cumplen."
           + (f" {format_n(n_rest)} créditos quedan fuera: ramas sin decisión o con Condiciones en 0/0." if n_rest else ""))

version_sidebar()
