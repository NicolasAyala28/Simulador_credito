import json
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import load_data, prepare_data, ROOT
from src.rie import DEFAULT_EXPERIENCE_PCT, DEFAULT_TERM_MONTHS, rie_scores
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Árbol", page_icon="🌳", layout="wide")
apply_finanzauto_theme()

DATA = prepare_data(load_data()).reset_index(drop=True)

TEXT = "#0A2F4A"
# Antigüedad mínima desde el desembolso (meses de vida) para comparar créditos maduros.
MIN_AGE_OPTIONS = {"Todos": 0, "≥ 12 meses": 12, "≥ 15 meses": 15}

# Árbol: Segmento -> RIE -> Licencia -> Condición, con la mora máxima a 15 meses en rangos de 30 días.
SEGMENT_ORDER = ["Empleado", "Independiente Formal", "Independiente Informal", "Transportador"]
# El RIE del árbol agrupa la normalización 0-3 del puntaje: 0 y 1 forman "0-1".
RIE_GROUPS = {0: "0-1", 1: "0-1", 2: "2", 3: "3"}
RIE_ORDER = ["0-1", "2", "3"]
LICENSE_ORDER = ["Particular", "Público"]
CONDITION_ORDER = ["Nuevo", "Usado"]
MORA_BINS = [-np.inf, 30, 60, 90, 120, 150, np.inf]
MORA_LABELS = ["0–30", "31–60", "61–90", "91–120", "121–150", "150+"]
MORA_SIN_DATO = "Sin dato de mora"
TREE_LEVELS = ["Segmento", "RIE", "Licencia", "Condición"]
LEVEL_COLORS = ["#064B39", "#087A55", "#43BD83", "#A4CE39"]
# Filtro opcional: solo aparece activo si la base trae la columna.
PERIODICIDAD_COL = "periodicidad_pago"
PERIODICIDAD_SIN_DATO = "Sin dato"
# Decisión asignada a cada rama del árbol; se guarda por rama en config/arbol_decision.json.
DECISION_COL = "Decisión"
DECISION_OPTIONS = ["Aprobado", "Condiciones", "A estudio"]
DECISION_PATH = ROOT / "config" / "arbol_decision.json"
DECISION_STATE = "arbol_decisiones"

def slug(value):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip().casefold())
    return value.strip("_") or "sin_perfil"

def format_int(n):
    return f"{int(n):,}".replace(",", ".")

# Escala de color de la mora > 30: blanco (0) -> amarillo -> rojo (máximo), para ubicar la mayor degradación.
MORA_SCALE = [(0.0, (255, 255, 255)), (0.5, (255, 214, 91)), (1.0, (232, 76, 61))]

def mora_color(value, vmax):
    if pd.isna(value) or not vmax:
        return ""
    t = min(max(float(value) / vmax, 0.0), 1.0)
    for (t0, c0), (t1, c1) in zip(MORA_SCALE, MORA_SCALE[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            rgb = [round(a + (b - a) * f) for a, b in zip(c0, c1)]
            return f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); color: #0A2F4A"
    return ""

def branch_key(row):
    return " | ".join(str(row[l]) for l in TREE_LEVELS)

def load_decisions():
    if DECISION_PATH.exists():
        try:
            with open(DECISION_PATH, encoding="utf-8") as f:
                return {k: v for k, v in json.load(f).items() if v in DECISION_OPTIONS}
        except (OSError, ValueError):
            pass
    return {}

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Árbol: segmento, RIE, licencia y condición</h1>
  <p>Ramas del árbol de decisión (hoja 1 de arbol.xlsx) con la concentración de la mora máxima a 15 meses.</p>
</div>
""",unsafe_allow_html=True)

profiles = DATA.get("perfil_label", pd.Series(["Sin perfil"]*len(DATA))).astype("string").str.strip()
invalid_profiles = {"","otros","otro","nan","none","null"}
valid_profile_mask = profiles.notna() & ~profiles.str.casefold().isin(invalid_profiles)
DATA = DATA[valid_profile_mask].copy()
DATA["perfil_label"] = profiles[valid_profile_mask].astype(str)
profile_options = sorted(DATA["perfil_label"].unique().tolist())
# periodicidad_pago no siempre viene en la base; se busca sin importar mayúsculas.
period_col = next((c for c in DATA.columns if str(c).strip().casefold() == PERIODICIDAD_COL), None)
c_profile,c_age,c_period = st.columns(3,gap="medium")
with c_profile:
    selected_profile = st.selectbox("Perfil",["Todos"]+profile_options,key="matrices_profile_filter")
with c_age:
    min_age_label = st.radio("Antigüedad mínima",list(MIN_AGE_OPTIONS),horizontal=True,key="matrices_min_age",
        help="Meses desde el desembolso hasta la fecha de corte. Los créditos cancelados antes se conservan.")
with c_period:
    if period_col:
        periodicidad = DATA[period_col].astype("string").str.strip().fillna(PERIODICIDAD_SIN_DATO)
        selected_periods = st.multiselect("Periodicidad de pago", sorted(periodicidad.unique().tolist()),
                                          placeholder="Todas", key="arbol_periodicidad")
        if selected_periods:
            DATA = DATA[periodicidad.isin(selected_periods)]
    else:
        st.multiselect("Periodicidad de pago", [], placeholder="No disponible", disabled=True, key="arbol_periodicidad",
                       help=f"La base no trae la columna {PERIODICIDAD_COL}.")
if MIN_AGE_OPTIONS[min_age_label] and "meses_vida" in DATA:
    DATA = DATA[DATA["meses_vida"].ge(MIN_AGE_OPTIONS[min_age_label]).fillna(False)]
DATA = DATA if selected_profile=="Todos" else DATA[DATA["perfil_label"]==selected_profile]
profile_key = slug(selected_profile)

# ---------------- Árbol ----------------
def tree_branch(series, order):
    values = series.astype("string").str.strip()
    return values.where(values.isin(order))

# RIE con los mismos parámetros que la hoja RIE en esta sesión (plazo y % de Experiencia).
rie = rie_scores(DATA,
    term_months=st.session_state.get("rie_term_months", DEFAULT_TERM_MONTHS),
    experience_pct=st.session_state.get("rie_experience_pct", DEFAULT_EXPERIENCE_PCT))
TREE = pd.DataFrame({
    "Segmento": tree_branch(DATA["perfil_label"], SEGMENT_ORDER),
    "RIE": rie["Normalización"].map(RIE_GROUPS),
    "Licencia": tree_branch(DATA.get("licencia_label", pd.Series(pd.NA, index=DATA.index)), LICENSE_ORDER),
    "Condición": tree_branch(DATA.get("condicion_label", pd.Series(pd.NA, index=DATA.index)), CONDITION_ORDER),
})

mora_15m = pd.to_numeric(DATA.get("mora_max_15m", pd.Series(np.nan, index=DATA.index)), errors="coerce")
TREE["Mora"] = pd.cut(mora_15m, bins=MORA_BINS, labels=MORA_LABELS, right=True).astype("string").fillna(MORA_SIN_DATO)
total_tree = len(TREE)
no_rie = int(TREE["RIE"].isna().sum())
no_branch = int((TREE["RIE"].notna() & TREE[["Segmento", "Licencia", "Condición"]].isna().any(axis=1)).sum())
TREE = TREE.dropna(subset=TREE_LEVELS)

st.markdown('<div class="fa-section">Árbol: Segmento → RIE → Licencia → Condición</div>', unsafe_allow_html=True)
pct_no_rie = no_rie / total_tree * 100 if total_tree else 0
st.info(f"Créditos con RIE no calculable: {format_int(no_rie)} ({pct_no_rie:.1f}%) de {format_int(total_tree)}. "
        "No se incluyen en el árbol ni en la tabla porque les falta información para el puntaje RIE (ver hoja RIE)."
        + (f" Además, {format_int(no_branch)} créditos sin licencia o condición válida quedan fuera." if no_branch else ""))

def sankey_tree(data):
    """Diagrama de izquierda a derecha; cada nodo es una rama propia del árbol."""
    labels, colors, ids = [], [], {}
    def node(path):
        if path not in ids:
            ids[path] = len(labels)
            labels.append(path[-1] if len(path) > 1 else path[0])
            colors.append(LEVEL_COLORS[len(path) - 1])
        return ids[path]
    sources, targets, values, hovers = [], [], [], []
    for depth in range(1, len(TREE_LEVELS)):
        grouped = data.groupby(TREE_LEVELS[:depth + 1], observed=True).size()
        for path, n in grouped.items():
            sources.append(node(tuple(path[:-1])))
            targets.append(node(tuple(path)))
            values.append(int(n))
            hovers.append(" → ".join(path))
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=[f"RIE {l}" if l in RIE_ORDER else l for l in labels], color=colors, pad=6, thickness=14,
                  line=dict(color="white", width=0.5), hovertemplate="%{label}: %{value:,} créditos<extra></extra>"),
        link=dict(source=sources, target=targets, value=values, customdata=hovers,
                  color="rgba(67,189,131,0.25)", hovertemplate="%{customdata}: %{value:,} créditos<extra></extra>"),
    ))
    fig.update_layout(height=760, margin=dict(l=8, r=8, t=8, b=8), font=dict(color=TEXT, size=10),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig

if TREE.empty:
    st.warning("No hay créditos con RIE calculable para los filtros seleccionados.")
else:
    with st.container(border=True):
        st.plotly_chart(sankey_tree(TREE), width="stretch", config={"displayModeBar": False}, key=f"arbol_sankey_{profile_key}")
        st.caption("El grosor de cada rama es la cantidad de créditos. Pasa el cursor sobre una rama para ver su recorrido completo.")

    # Tabla: una fila por rama con el % de créditos con mora > 30 días y cómo se reparte esa mora por rango.
    st.markdown('<div class="fa-section">Concentración de la mora máxima a 15 meses por rama</div>', unsafe_allow_html=True)
    # Filtros de la tabla; vacío equivale a todos los valores del nivel.
    level_orders = dict(zip(TREE_LEVELS, [SEGMENT_ORDER, RIE_ORDER, LICENSE_ORDER, CONDITION_ORDER]))
    for level, col in zip(TREE_LEVELS, st.columns(len(TREE_LEVELS), gap="small")):
        with col:
            chosen = st.multiselect(level, [v for v in level_orders[level] if TREE[level].eq(v).any()],
                                    placeholder="Todos", key=f"arbol_tabla_{slug(level)}")
        if chosen:
            TREE = TREE[TREE[level].isin(chosen)]
    if TREE.empty:
        st.warning("No hay ramas para los filtros de la tabla seleccionados.")
        st.stop()
    mora_cols = MORA_LABELS + ([MORA_SIN_DATO] if TREE["Mora"].eq(MORA_SIN_DATO).any() else [])
    for level, order in level_orders.items():
        TREE[level] = pd.Categorical(TREE[level], categories=order, ordered=True)
    counts = pd.crosstab([TREE[l] for l in TREE_LEVELS], TREE["Mora"]).reindex(columns=mora_cols, fill_value=0)
    counts.loc[("Total", "", "", ""), :] = counts.sum()
    total_rama = counts.sum(axis=1)
    over_30 = MORA_LABELS[1:]
    n_over_30 = counts[over_30].sum(axis=1)
    MORA_30 = "Mora > 30 (%)"
    # Los rangos 31–60 a 150+ se expresan sobre los créditos con mora > 30 de la rama (suman 100%).
    table = counts[over_30].div(n_over_30.where(n_over_30 > 0), axis=0).mul(100)
    table.insert(0, MORA_30, n_over_30.div(total_rama).mul(100))
    table.insert(0, "Créditos", total_rama.astype(int))
    if MORA_SIN_DATO in counts:
        table[MORA_SIN_DATO] = counts[MORA_SIN_DATO].div(total_rama).mul(100)
    table = table.reset_index().astype({l: str for l in TREE_LEVELS})
    # Decisión editable por rama; la fila Total no lleva decisión.
    if DECISION_STATE not in st.session_state:
        st.session_state[DECISION_STATE] = load_decisions()
    decisions = st.session_state[DECISION_STATE]
    keys = table.apply(branch_key, axis=1)
    is_total = table["Segmento"].eq("Total")
    table.insert(len(TREE_LEVELS), DECISION_COL, [None if t else decisions.get(k) for k, t in zip(keys, is_total)])
    # Color solo en los rangos 31–60 a 150+, sobre 100%.
    pct_cols = [MORA_30] + mora_cols[1:]
    range_cols = [c for c in MORA_LABELS[1:] if c in table]
    styled = (table.style
        .map(lambda v: mora_color(v, 100), subset=range_cols)
        .format("{:.1f}%", subset=pct_cols, na_rep=""))
    edited = st.data_editor(styled, width="stretch", hide_index=True, num_rows="fixed",
        height=min(38 + 35 * len(table), 720), key="arbol_tabla_editor_" + "_".join(
            slug(",".join(st.session_state.get(f"arbol_tabla_{slug(l)}", []))) for l in TREE_LEVELS),
        disabled=[c for c in table.columns if c != DECISION_COL],
        column_config={DECISION_COL: st.column_config.SelectboxColumn(DECISION_COL, options=DECISION_OPTIONS),
                       "Créditos": st.column_config.NumberColumn("Créditos", format="localized"),
                       **{c: st.column_config.NumberColumn(c, format="%.1f%%") for c in pct_cols}})
    for k, t, v in zip(keys, is_total, edited[DECISION_COL]):
        if t:
            continue
        if v in DECISION_OPTIONS:
            decisions[k] = v
        else:
            decisions.pop(k, None)
    c_save, c_reset = st.columns(2)
    with c_save:
        if st.button("Guardar decisiones", type="primary", width="stretch", key="arbol_guardar_decisiones"):
            with open(DECISION_PATH, "w", encoding="utf-8") as f:
                json.dump(decisions, f, ensure_ascii=False, indent=2)
            st.success(f"Decisiones guardadas ({len(decisions)} ramas).")
    with c_reset:
        if st.button("Descartar cambios sin guardar", width="stretch", key="arbol_descartar_decisiones"):
            st.session_state[DECISION_STATE] = load_decisions()
            for k in [k for k in st.session_state if str(k).startswith("arbol_tabla_editor_")]:
                del st.session_state[k]
            st.rerun()
    st.caption(f"{MORA_30}: créditos de la rama con mora máxima en los primeros 15 meses (mora_max_15m) mayor a 30 días, "
               "sobre el total de créditos de la rama. Los rangos 31–60 a 150+ muestran cómo se reparten esos créditos "
               "con mora > 30 (suman 100%; quedan vacíos si la rama no tiene mora > 30). Sin dato de mora es el % sobre "
               "el total de la rama. Los rangos incluyen el límite superior; 150+ es más de 150 días. "
               "RIE agrupa la normalización del puntaje: 0-1, 2 y 3. "
               f"{DECISION_COL}: elige Aprobado, Condiciones o A estudio por rama; se conserva al cambiar los filtros "
               "y queda guardada con «Guardar decisiones». Colores (blanco → amarillo → rojo) en los rangos 31–60 a 150+: "
               "el rojo es 100% de la mora > 30 de la rama concentrada en el rango.")

    # Tarjetas por decisión: créditos de las ramas de la tabla según su decisión, sobre el total de la tabla.
    st.markdown(f'<div class="fa-section">Créditos por {DECISION_COL.lower()}</div>', unsafe_allow_html=True)
    branch_credits = table.loc[~is_total, "Créditos"].to_numpy()
    branch_decisions = [decisions.get(k) for k in keys[~is_total]]
    total_table = int(table.loc[is_total, "Créditos"].sum())
    for col, (label, option) in zip(st.columns(len(DECISION_OPTIONS), gap="medium"),
                                    [("Aprobados", "Aprobado"), ("Condiciones", "Condiciones"), ("A estudio", "A estudio")]):
        n = int(sum(c for c, d in zip(branch_credits, branch_decisions) if d == option))
        col.metric(label, format_int(n), f"{n / total_table * 100:.1f}%" if total_table else "0.0%",
                   delta_color="off", border=True)
    n_none = total_table - int(sum(c for c, d in zip(branch_credits, branch_decisions) if d in DECISION_OPTIONS))
    st.caption(f"Porcentajes sobre los {format_int(total_table)} créditos de la tabla (fila Total, con los filtros aplicados)."
               + (f" {format_int(n_none)} créditos están en ramas sin decisión asignada." if n_none else ""))
