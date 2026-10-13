import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from src.data_loader import ROOT

CONFIG_DIR = ROOT / "config"
CONFIG_DIR.mkdir(exist_ok=True)
MATRIX_DIR = CONFIG_DIR / "matrices"
MATRIX_DIR.mkdir(exist_ok=True)

def filtered_data(df, key_prefix="flt"):
    st.subheader("Filtros")
    c1, c2, c3 = st.columns(3)
    profiles = sorted(df["perfil_label"].dropna().astype(str).unique().tolist()) if "perfil_label" in df else []
    with c1:
        profile = st.selectbox("Perfil", ["Todos"] + profiles, key=f"{key_prefix}_profile")
    with c2:
        conditions = sorted(df["condicion_label"].dropna().astype(str).unique().tolist()) if "condicion_label" in df else []
        condition = st.selectbox("Condición", ["Todos"] + conditions, key=f"{key_prefix}_condition")
    with c3:
        licenses = sorted(df["licencia_label"].dropna().astype(str).unique().tolist()) if "licencia_label" in df else []
        license_ = st.selectbox("Licencia", ["Todos"] + licenses, key=f"{key_prefix}_license")
    out = df.copy()
    if profile != "Todos": out = out[out["perfil_label"].astype(str) == profile]
    if condition != "Todos" and "condicion_label" in out: out = out[out["condicion_label"].astype(str) == condition]
    if license_ != "Todos" and "licencia_label" in out: out = out[out["licencia_label"].astype(str) == license_]
    st.caption(f"Población filtrada: {len(out):,} registros".replace(",", "."))
    return out

def concentration_table(df, category_col, condition_col=None, condition_value=None):
    data = df.copy()
    if condition_col and condition_value and condition_value != "Todos":
        if condition_col not in data: return pd.DataFrame()
        data = data[data[condition_col].astype(str) == condition_value]
    if category_col not in data or data.empty: return pd.DataFrame()
    s = data[category_col].fillna("Sin dato").astype(str)
    counts = s.value_counts(dropna=False)
    result = pd.DataFrame({"Categoría": counts.index, "Registros": counts.values})
    total = int(result["Registros"].sum())
    result["Concentración (%)"] = (result["Registros"] / total * 100).round(2) if total else 0
    return result

def show_concentrations(df, category_col, condition_col="condicion_label", condition_value="Todos"):
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### Matriz de concentración general")
        t = concentration_table(df, category_col)
        if t.empty: st.warning("No hay datos disponibles para esta concentración.")
        else:
            st.dataframe(t, width="stretch", hide_index=True)
            st.bar_chart(t.set_index("Categoría")["Registros"])
    with right:
        st.markdown("#### Matriz de concentración con condición")
        st.caption("Puedes definir la condición que limita los registros de esta matriz.")
        available = sorted(df[condition_col].dropna().astype(str).unique().tolist()) if condition_col in df else []
        chosen = st.selectbox("Condición de concentración", ["Todos"] + available, key=f"concentration_condition_{category_col}")
        t2 = concentration_table(df, category_col, condition_col, chosen)
        if t2.empty: st.warning("No hay datos disponibles para esta condición.")
        else:
            st.dataframe(t2, width="stretch", hide_index=True)
            st.bar_chart(t2.set_index("Categoría")["Registros"])

def load_matrix(name, default_df):
    path = MATRIX_DIR / f"{name}.json"
    if path.exists():
        try:
            saved = pd.read_json(path)
            if list(saved.columns) == list(default_df.columns) and saved.shape == default_df.shape:
                return saved
        except Exception:
            pass
    return default_df.copy()

def matrix_editor(name, title, default_df, help_text=""):
    st.markdown(f"#### {title}")
    if help_text: st.caption(help_text)
    current = load_matrix(name, default_df)
    edited = st.data_editor(current, width="stretch", hide_index=True, num_rows="fixed", key=f"editor_{name}")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Restablecer valores por defecto", key=f"reset_{name}", width="stretch"):
            path = MATRIX_DIR / f"{name}.json"
            if path.exists(): path.unlink()
            st.session_state[f"editor_{name}"] = default_df.copy()
            st.success("Se restauraron los valores por defecto.")
            st.rerun()
    with b2:
        if st.button("Guardar valores de la matriz", key=f"save_{name}", type="primary", width="stretch"):
            path = MATRIX_DIR / f"{name}.json"
            edited.to_json(path, orient="records", force_ascii=False, indent=2)
            st.success(f"Matriz guardada en {path.relative_to(ROOT)}")
    return edited

def numeric_columns(df):
    return [c for c in df.select_dtypes(include="number").columns if df[c].nunique(dropna=True) > 1]

def category_column_selector(df, key, default=None):
    candidates = [c for c in ["perfil_label", "ocupacion_agg", "condicion_label", "licencia_label", "FrankDecision", "clase_fasecolda", "productivo", "FGA"] if c in df.columns]
    if not candidates:
        candidates = [c for c in df.columns if df[c].nunique(dropna=True) < 30]
    if not candidates:
        st.warning("No se encontraron variables categóricas.")
        return None
    ix = candidates.index(default) if default in candidates else 0
    return st.selectbox("Variable para concentración", candidates, index=ix, key=key)

def quantile_categories(series, labels=("AA","A","AE")):
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna()
    result = pd.Series(index=series.index, dtype="object")
    if valid.sum() < len(labels):
        result.loc[valid] = labels[0]
        return result
    try:
        result.loc[valid] = pd.qcut(numeric[valid].rank(method="first"), q=len(labels), labels=labels).astype(str)
    except Exception:
        result.loc[valid] = labels[0]
    return result


def show_category_summary_cards(df, category_col, title="Concentración por categoría", categories=("AA", "A", "AE")):
    """Muestra únicamente tres tarjetas compactas: categoría, cantidad y porcentaje."""
    st.markdown(f"#### {title}")
    if category_col not in df.columns or df.empty:
        st.info("No hay registros disponibles para calcular la concentración.")
        return
    values = df[category_col].astype("string").str.strip()
    values = values[values.notna()]
    counts = values.value_counts()
    denominator = int(counts.sum())
    cols = st.columns(3, gap="small")
    palette = {
        "AA": ("#087A55", "#EFF7F2", "#CFE5D8"),
        "A": ("#D9A400", "#FFF9E5", "#F3E5A8"),
        "AE": ("#E65353", "#FFF0F0", "#F5CDCD"),
    }
    for i, category in enumerate(categories):
        count = int(counts.get(category, 0))
        pct = count / denominator * 100 if denominator else 0.0
        accent, background, border = palette.get(category, ("#087A55", "#EFF7F2", "#CFE5D8"))
        with cols[i]:
            st.markdown(
                f"""
                <div style="
                    min-height:68px; padding:8px 10px; border-radius:8px;
                    background:{background}; border:1px solid {border};
                    border-left:4px solid {accent}; text-align:center;
                    display:flex; flex-direction:column; justify-content:center;
                    line-height:1.2;">
                  <div style="font-size:12px; font-weight:700; color:#153C32; margin-bottom:3px;">{category}</div>
                  <div style="font-size:17px; font-weight:750; color:#092F26;">{count:,}</div>
                  <div style="font-size:12px; color:#365D50;">({pct:.1f}%)</div>
                </div>
                """.replace(",", "."),
                unsafe_allow_html=True,
            )
