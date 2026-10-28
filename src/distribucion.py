"""Datos, filtro y estilos compartidos por las dos hojas de Distribución."""
import streamlit as st

from src.data_loader import load_data, prepare_data

# Paleta verde corporativa inspirada en Finanzauto.
GREEN_PALETTE = ["#064B39", "#008F65", "#35B779", "#A4CE39", "#2F6B4F", "#70C1A1", "#C5DF8B"]
GRID = "#E5EFEA"
TEXT = "#153C32"

SEGMENT_ORDER = ["Empleado", "Independiente Formal", "Independiente Informal", "Transportador"]
SIN_OCUPACION = "Sin ocupación principal"
# Año elegido, compartido entre las dos hojas para que al cambiar de hoja se conserve.
YEAR_STATE = "distribucion_anio"

PAGE_STYLE = """
<style>
.block-container {padding-top: 1.1rem; padding-bottom: 1rem; max-width: 1800px;}
h1, h2, h3 {color: #153C32;}
.section-title {border-left: 5px solid #16866A; padding-left: 10px; margin: 0.3rem 0 0.8rem 0;}
[data-testid="stMetric"] {background:#F3F8F5; border:1px solid #DCEBE3; padding:12px; border-radius:10px;}
div[data-testid="stDataFrame"] {border:1px solid #E1ECE6; border-radius:8px;}
</style>
"""

def format_n(n):
    return f"{int(n):,}".replace(",", ".")

def format_pct(part, total):
    return f"{part / total * 100:.1f}%".replace(".", ",") if total else "0,0%"

def load_distribution_data():
    """Devuelve (base, df): base conserva los registros sin ocupación principal ('Sin dato')
    para contarlos; df es la población de análisis, solo con segmento."""
    base = prepare_data(load_data(), incluir_sin_dato=True)
    df = base[base["segmentacion"].ne("Sin dato")].copy()
    # Excluir perfiles nulos/erróneos y la categoría "Otros".
    invalid_profile_values = {"otros", "otro", "nan", "none", "null", ""}
    df["perfil_label"] = df["perfil_label"].astype("string").str.strip()
    df = df[df["perfil_label"].notna()]
    df = df[~df["perfil_label"].str.casefold().isin(invalid_profile_values)]
    return base, df

def year_filter(df, key):
    """Filtro de Año. Devuelve una función que aplica el año elegido a cualquier DataFrame."""
    years = sorted(df["fecha_desembolso"].dropna().dt.year.unique().tolist()) if "fecha_desembolso" in df else []
    options = ["Todos"] + years
    current = st.session_state.get(YEAR_STATE, "Todos")
    with st.container(border=True):
        st.markdown("**Filtros de datos**")
        selected = st.selectbox("Año", options, index=options.index(current) if current in options else 0, key=key)
    st.session_state[YEAR_STATE] = selected

    def apply(data):
        if selected == "Todos":
            return data
        return data[data["fecha_desembolso"].dt.year == int(selected)]
    return apply
