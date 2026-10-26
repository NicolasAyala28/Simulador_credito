import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import load_data, prepare_data, ROOT
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Matrices", page_icon="▦", layout="wide")
apply_finanzauto_theme()

DATA = prepare_data(load_data()).reset_index(drop=True)
MATRIX_DIR = ROOT / "config" / "matrices"
MATRIX_DIR.mkdir(parents=True, exist_ok=True)

TEXT = "#0A2F4A"
CATEGORIES = ["AA", "A", "AE"]
MORA_THRESHOLDS = [60, 90]
# Antigüedad mínima desde el desembolso (meses de vida) para comparar créditos maduros.
MIN_AGE_OPTIONS = {"Todos": 0, "≥ 12 meses": 12, "≥ 15 meses": 15}
CATEGORY_COLORS = {"AA": "#68D39A", "A": "#FFD65B", "AE": "#FF7373"}
CATEGORY_BG = {"AA": "#EAF8F0", "A": "#FFF9E4", "AE": "#FFF0F0"}

# Matrices de la primera hoja del Excel: rangos y asignaciones tal como están definidos.
SCORE_ACIERTA = ["0-430", "430-600", "600-675", "675-715", "715-740",
                 "740-760", "760-780", "780-810", "810-840", "840-1000"]
SCORE_FRANK = ["0-340", "340-470", "470-560", "560-635", "635-690",
               "690-745", "745-790", "790-835", "835-885", "885-1000"]
SCORE_RULES = [
    ["AE","AE","AE","AE","AE","AE","AE","AE","AE","AE"],
    ["AE","AE","AE","AE","AE","AE","AE","AE","AE","AE"],
    ["AE","AE","AE","A","A","A","A","A","A","A"],
    ["AE","AE","A","A","A","A","A","A","A","A"],
    ["AE","AE","A","A","A","A","A","A","A","A"],
    ["AE","AE","A","A","A","A","A","AA","AA","AA"],
    ["AE","AE","A","A","A","AA","AA","AA","AA","AA"],
    ["AE","AE","A","A","A","AA","AA","AA","AA","AA"],
    ["AE","A","A","A","AA","AA","AA","AA","AA","AA"],
    ["AE","A","A","A","AA","AA","AA","AA","AA","AA"],
]
# Exposición: filas cuota inicial (%), columnas valor del vehículo en millones.
EXPOS_ROWS = ["0%-10%", "10%-20%", "20%-30%", "30%-40%", "40%-50%", "50%-70%", ">70%"]
EXPOS_PARTICULAR_COLS = ["≤60 M", "60-85 M", "85-120 M", "120-170 M", ">170 M"]
EXPOS_PUBLICO_COLS = ["≤80 M", "80-130 M", "130-170 M", "170-220 M", ">220 M"]
EXPOS_PARTICULAR_RULES = [
    ["AE","AE","AE","AE","AE"],
    ["A","A","AE","AE","AE"],
    ["AA","A","A","AE","AE"],
    ["AA","AA","A","A","AE"],
    ["AA","AA","AA","A","AE"],
    ["AA","AA","AA","AA","A"],
    ["AA","AA","AA","AA","AA"],
]
EXPOS_PUBLICO_RULES = [
    ["AE","AE","AE","AE","AE"],
    ["A","A","AE","AE","AE"],
    ["AA","A","A","AE","AE"],
    ["AA","AA","A","A","AE"],
    ["AA","AA","A","A","AE"],
    ["AA","AA","AA","AA","A"],
    ["AA","AA","AA","AA","AA"],
]
RISK_LEVELS = list(range(8))
RISK_RULES = ["AE","AE","AE","A","A","A","AA","AA"]

def slug(value):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip().casefold())
    return value.strip("_") or "sin_perfil"

def matrix_path(key):
    return MATRIX_DIR / f"{key}.json"

def load_matrix(key, default):
    path = matrix_path(key)
    if path.exists():
        try:
            saved = pd.read_json(path)
            if list(saved.columns) == list(default.columns) and saved.shape == default.shape:
                return saved
        except Exception:
            pass
    return default.copy()

def save_matrix(key, frame):
    frame.to_json(matrix_path(key), orient="records", force_ascii=False, indent=2)

def matrix_frame(rows, cols, rules, row_name):
    result = pd.DataFrame(rules, columns=cols)
    result.insert(0, row_name, rows)
    return result

def edges_from_labels(labels):
    edges = [float(x.split("-")[0]) for x in labels]
    edges.append(float(labels[-1].split("-")[1]))
    return edges

def bin_numeric(series, labels):
    edges = edges_from_labels(labels)
    values = pd.to_numeric(series, errors="coerce")
    return pd.cut(values, bins=edges, labels=labels, include_lowest=True, right=True, ordered=True)

def bin_exposure(series, thresholds, labels):
    values = pd.to_numeric(series, errors="coerce")
    return pd.cut(values, bins=thresholds, labels=labels, include_lowest=True, right=True, ordered=True)

def format_int(n):
    return f"{int(n):,}".replace(",", ".")

def assign_score_category(data, matrix):
    out = data.copy()
    out["_row_bin"] = bin_numeric(out["acierta"], SCORE_ACIERTA)
    out["_col_bin"] = bin_numeric(out["Frank"], SCORE_FRANK)
    lookup = {(str(r["Acierta (filas)"]), str(c)): str(r[c])
              for _, r in matrix.iterrows() for c in SCORE_FRANK}
    out["categoria_matriz"] = [
        lookup.get((str(row), str(col))) if pd.notna(row) and pd.notna(col) else None
        for row, col in zip(out["_row_bin"], out["_col_bin"])
    ]
    return out.dropna(subset=["_row_bin", "_col_bin"])

def assign_exposure_category(data, matrix, license_type):
    out = data.copy()
    if license_type == "Público":
        value_thresholds = [-np.inf, 80e6, 130e6, 170e6, 220e6, np.inf]
        value_labels = EXPOS_PUBLICO_COLS
        mask = out["licencia_vehiculo"].astype("string").str.upper().eq("PUB")
    else:
        value_thresholds = [-np.inf, 60e6, 85e6, 120e6, 170e6, np.inf]
        value_labels = EXPOS_PARTICULAR_COLS
        mask = out["licencia_vehiculo"].astype("string").str.upper().eq("PAR")
    out = out[mask].copy()
    # cuota_inicial ya está expresada como porcentaje en la base (0-100).
    out["_row_bin"] = bin_exposure(out["cuota_inicial"], [-np.inf,10,20,30,40,50,70,np.inf], EXPOS_ROWS)
    out["_col_bin"] = bin_exposure(out["ValorVh"], value_thresholds, value_labels)
    row_name = "Cuota inicial (%)"
    lookup = {(str(r[row_name]), str(c)): str(r[c])
              for _, r in matrix.iterrows() for c in value_labels}
    out["categoria_matriz"] = [
        lookup.get((str(row), str(col))) if pd.notna(row) and pd.notna(col) else None
        for row, col in zip(out["_row_bin"], out["_col_bin"])
    ]
    return out.dropna(subset=["_row_bin", "_col_bin"])

def concentration_matrix(data, row_col, col_col, rows, cols):
    if data.empty:
        return pd.DataFrame(0.0, index=list(reversed(rows)), columns=cols)
    temp = data[[row_col, col_col]].dropna()
    counts = pd.crosstab(temp[row_col].astype(str), temp[col_col].astype(str))
    counts = counts.reindex(index=rows, columns=cols, fill_value=0)
    if len(temp):
        counts = counts / len(temp)
    return counts.loc[list(reversed(rows)), cols]

def render_heatmap(frame, key, height=340):
    vals = frame.to_numpy(dtype=float)
    labels = np.array([[f"{v*100:.1f}%" if np.isfinite(v) else "—" for v in row] for row in vals])
    maxval = float(np.nanmax(vals)) if np.isfinite(vals).any() else .01
    fig = go.Figure(go.Heatmap(
        z=vals, x=list(frame.columns), y=list(frame.index),
        text=labels, texttemplate="%{text}",
        colorscale=[[0,"#F3FAF6"],[.25,"#D6F0DF"],[.5,"#91DDB2"],[.75,"#43BD83"],[1,"#087A55"]],
        zmin=0, zmax=max(maxval,.01), showscale=False, xgap=1.5, ygap=1.5,
        textfont={"size":9,"color":TEXT},
        hovertemplate="Fila %{y}<br>Columna %{x}<br>Concentración: %{text}<extra></extra>",
    ))
    fig.update_layout(title=None,height=height,margin=dict(l=8,r=8,t=8,b=5),
        paper_bgcolor="rgba(0,0,0,0)",font={"color":TEXT,"size":9},
        xaxis={"side":"top","title":None,"showgrid":False,"tickfont":{"size":8}},
        yaxis={"title":None,"autorange":"reversed","showgrid":False,"tickfont":{"size":8}})
    st.plotly_chart(fig,width="stretch",config={"displayModeBar":False},key=key)

def show_cards(data, key):
    values = data["categoria_matriz"].astype("string") if "categoria_matriz" in data else pd.Series(dtype="string")
    values = values[values.isin(CATEGORIES)]
    total = len(values)
    counts = values.value_counts()
    cols = st.columns(3, gap="small")
    for col, cat in zip(cols, CATEGORIES):
        n = int(counts.get(cat,0))
        pct = n/total*100 if total else 0
        with col:
            st.markdown(f"""<div class="fa-summary-card" style="background:{CATEGORY_BG[cat]};border:1px solid {CATEGORY_COLORS[cat]}66;border-left:4px solid {CATEGORY_COLORS[cat]}">
            <div style="font-size:12px;font-weight:800;color:#315849">{cat}</div>
            <div style="font-size:17px;font-weight:800;color:#0A2F4A">{format_int(n)}</div>
            <div style="font-size:11px;color:#45675A">({pct:.1f}%)</div></div>""",unsafe_allow_html=True)

def render_matrix_editor(default, key, row_name, columns, height=350):
    editable = load_matrix(key, default)
    editor = st.data_editor(editable,key=f"editor_{slug(key)}",width="stretch",
        hide_index=True,num_rows="fixed",height=height,
        column_config={row_name:st.column_config.TextColumn(row_name,disabled=True),
        **{c:st.column_config.SelectboxColumn(c,options=CATEGORIES,required=True) for c in columns}})
    b1,b2=st.columns([1,1])
    with b1:
        if st.button("Restablecer valores por defecto",key=f"reset_{slug(key)}",width="stretch"):
            path=matrix_path(key)
            if path.exists(): path.unlink()
            st.session_state[f"editor_{slug(key)}"]=default.copy()
            st.rerun()
    with b2:
        if st.button("Guardar matriz",key=f"save_{slug(key)}",type="primary",width="stretch"):
            save_matrix(key,editor)
            st.success("Matriz guardada para el perfil y configuración seleccionados.")
    return editor

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Matrices de score, exposición y riesgo</h1>
  <p>Configuración basada en la hoja «Matrices» del archivo asignacion_decision.xlsx.</p>
</div>
""",unsafe_allow_html=True)

profiles = DATA.get("perfil_label", pd.Series(["Sin perfil"]*len(DATA))).astype("string").str.strip()
invalid_profiles = {"","otros","otro","nan","none","null"}
valid_profile_mask = profiles.notna() & ~profiles.str.casefold().isin(invalid_profiles)
DATA = DATA[valid_profile_mask].copy()
DATA["perfil_label"] = profiles[valid_profile_mask].astype(str)
profile_options = sorted(DATA["perfil_label"].unique().tolist())
c_profile,c_condition,c_age = st.columns(3,gap="medium")
with c_profile:
    selected_profile = st.selectbox("Perfil",["Todos"]+profile_options,key="matrices_profile_filter")
with c_condition:
    mora_days = st.radio("Condición: días de mora mayor a",MORA_THRESHOLDS,horizontal=True,
        format_func=lambda d: f"{d} días",key="matrices_mora_condition")
with c_age:
    min_age_label = st.radio("Antigüedad mínima",list(MIN_AGE_OPTIONS),horizontal=True,key="matrices_min_age",
        help="Meses desde el desembolso hasta la fecha de corte. Los créditos cancelados antes se conservan.")
if MIN_AGE_OPTIONS[min_age_label] and "meses_vida" in DATA:
    DATA = DATA[DATA["meses_vida"].ge(MIN_AGE_OPTIONS[min_age_label]).fillna(False)]
# Mora máxima en los primeros 15 meses (o hasta el corte si el crédito es más joven).
mora = pd.to_numeric(DATA.get("mora_max_15m",pd.Series(np.nan,index=DATA.index)),errors="coerce")
DATA["condicion_mora"] = mora.gt(mora_days).astype(int)
CONDITION_TITLE = f"con condición (mora &gt; {mora_days} días)"
DATA = DATA if selected_profile=="Todos" else DATA[DATA["perfil_label"]==selected_profile]
profile_key = slug(selected_profile)

tab_score,tab_exposure,tab_risk = st.tabs(["Score","Exposición","Riesgo"])

with tab_score:
    st.markdown('<div class="fa-section">Matriz principal: Acierta vs. Frank</div>',unsafe_allow_html=True)
    st.caption("Rangos y categorías replicados de la primera hoja del Excel.")
    score_default = matrix_frame(SCORE_ACIERTA,SCORE_FRANK,SCORE_RULES,"Acierta (filas)")
    score_key = f"score__perfil_{profile_key}"
    score_editor = render_matrix_editor(score_default,score_key,"Acierta (filas)",SCORE_FRANK,height=385)

    scored = assign_score_category(DATA,score_editor)
    general = concentration_matrix(scored,"_row_bin","_col_bin",SCORE_ACIERTA,SCORE_FRANK)
    conditioned = scored[scored["condicion_mora"]==1]
    conditional_grid = concentration_matrix(conditioned,"_row_bin","_col_bin",SCORE_ACIERTA,SCORE_FRANK)
    left,right = st.columns(2,gap="medium")
    with left:
        with st.container(border=True):
            st.markdown('<div class="fa-section">Matriz de concentración general</div>',unsafe_allow_html=True)
            render_heatmap(general,f"score_general_{profile_key}")
            show_cards(scored,f"score_general_cards_{profile_key}")
    with right:
        with st.container(border=True):
            st.markdown(f'<div class="fa-section">Matriz de concentración {CONDITION_TITLE}</div>',unsafe_allow_html=True)
            render_heatmap(conditional_grid,f"score_condition_{profile_key}")
            show_cards(conditioned,f"score_condition_cards_{profile_key}")

with tab_exposure:
    st.markdown('<div class="fa-section">Matriz principal: cuota inicial vs. valor del vehículo</div>',unsafe_allow_html=True)
    license_type = st.radio("Tipo de licencia",["Particular","Público"],horizontal=True,key=f"exposure_license_{profile_key}")
    if license_type=="Público":
        exp_cols,exp_rules = EXPOS_PUBLICO_COLS,EXPOS_PUBLICO_RULES
    else:
        exp_cols,exp_rules = EXPOS_PARTICULAR_COLS,EXPOS_PARTICULAR_RULES
    exp_default = matrix_frame(EXPOS_ROWS,exp_cols,exp_rules,"Cuota inicial (%)")
    exp_key = f"exposicion_{slug(license_type)}__perfil_{profile_key}"
    exp_editor = render_matrix_editor(exp_default,exp_key,"Cuota inicial (%)",exp_cols,height=340)
    exposed = assign_exposure_category(DATA,exp_editor,license_type)
    exp_general = concentration_matrix(exposed,"_row_bin","_col_bin",EXPOS_ROWS,exp_cols)
    exp_conditioned = exposed[exposed["condicion_mora"]==1]
    exp_conditional = concentration_matrix(exp_conditioned,"_row_bin","_col_bin",EXPOS_ROWS,exp_cols)
    left,right = st.columns(2,gap="medium")
    with left:
        with st.container(border=True):
            st.markdown('<div class="fa-section">Matriz de concentración general</div>',unsafe_allow_html=True)
            render_heatmap(exp_general,f"exposure_general_{profile_key}_{slug(license_type)}",height=300)
            show_cards(exposed,f"exposure_general_cards_{profile_key}_{slug(license_type)}")
    with right:
        with st.container(border=True):
            st.markdown(f'<div class="fa-section">Matriz de concentración {CONDITION_TITLE}</div>',unsafe_allow_html=True)
            render_heatmap(exp_conditional,f"exposure_condition_{profile_key}_{slug(license_type)}",height=300)
            show_cards(exp_conditioned,f"exposure_condition_cards_{profile_key}_{slug(license_type)}")

with tab_risk:
    st.markdown('<div class="fa-section">Matriz principal: RIE</div>',unsafe_allow_html=True)
    st.caption("Categorías RIE y clasificación AA/A/AE tomadas de la hoja «Matrices».")
    risk_default = pd.DataFrame({"RIE":RISK_LEVELS,"Categoría":RISK_RULES})
    risk_key = f"riesgo__perfil_{profile_key}"
    risk_editor = st.data_editor(load_matrix(risk_key,risk_default),key=f"editor_risk_{profile_key}",
        width="stretch",hide_index=True,num_rows="fixed",height=320,
        column_config={"RIE":st.column_config.NumberColumn("RIE",disabled=True),"Categoría":st.column_config.SelectboxColumn("Categoría",options=CATEGORIES,required=True)})
    r1,r2=st.columns(2)
    with r1:
        if st.button("Restablecer valores por defecto",key=f"reset_risk_{profile_key}",width="stretch"):
            path=matrix_path(risk_key)
            if path.exists(): path.unlink()
            st.session_state[f"editor_risk_{profile_key}"]=risk_default.copy()
            st.rerun()
    with r2:
        if st.button("Guardar matriz",key=f"save_risk_{profile_key}",type="primary",width="stretch"):
            save_matrix(risk_key,risk_editor)
            st.success("Matriz RIE guardada para el perfil seleccionado.")
    if "RIE" in DATA.columns:
        risk_data=DATA.copy()
        risk_data["RIE"]=pd.to_numeric(risk_data["RIE"],errors="coerce")
        risk_data=risk_data[risk_data["RIE"].isin(RISK_LEVELS)].copy()
        lookup=dict(zip(risk_editor["RIE"].astype(int),risk_editor["Categoría"].astype(str)))
        risk_data["categoria_matriz"]=risk_data["RIE"].map(lookup)
    else:
        # No inventamos el dato RIE: mostramos matriz y condición, y señalamos que falta en la base.
        risk_data=pd.DataFrame(columns=["RIE","categoria_matriz","condicion_mora"])
    risk_summary = pd.DataFrame({"Categoría":CATEGORIES,
        "Cantidad":[int((risk_data.get("categoria_matriz",pd.Series(dtype=str))==c).sum()) for c in CATEGORIES]})
    left,right=st.columns(2,gap="medium")
    with left:
        with st.container(border=True):
            st.markdown('<div class="fa-section">Concentración general</div>',unsafe_allow_html=True)
            st.dataframe(risk_summary,width="stretch",hide_index=True)
            show_cards(risk_data,f"risk_general_cards_{profile_key}")
    with right:
        with st.container(border=True):
            st.markdown(f'<div class="fa-section">Concentración {CONDITION_TITLE}</div>',unsafe_allow_html=True)
            risk_conditioned=risk_data[risk_data.get("condicion_mora",pd.Series(dtype=int))==1] if not risk_data.empty else risk_data
            st.dataframe(pd.DataFrame({"Categoría":CATEGORIES,"Cantidad":[int((risk_conditioned.get("categoria_matriz",pd.Series(dtype=str))==c).sum()) for c in CATEGORIES]}),width="stretch",hide_index=True)
            show_cards(risk_conditioned,f"risk_condition_cards_{profile_key}")
            if "RIE" not in DATA.columns:
                st.info("La base no contiene una columna RIE. La clasificación está configurada, pero no se calcula concentración hasta disponer de esa variable.")
