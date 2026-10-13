from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "data_desembolsos_2024_2025.csv"

@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_csv(DATA_PATH, sep=";", encoding="utf-8-sig", low_memory=False)
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]
    return df

def prepare_data(df):
    df = df.copy()
    if "id_fecha_desembolso" in df.columns:
        raw = df["id_fecha_desembolso"].astype("string").str.replace(r"\.0$", "", regex=True)
        df["fecha_desembolso"] = pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
    if "mes_desem" in df.columns:
        df["mes_desem"] = pd.to_numeric(df["mes_desem"], errors="coerce").astype("Int64")
    if "licencia_vehiculo" in df.columns:
        df["licencia_label"] = df["licencia_vehiculo"].map({"PAR":"Particular", "PUB":"Público"}).fillna(df["licencia_vehiculo"].astype(str))
    if "condicion_vehiculo" in df.columns:
        df["condicion_label"] = df["condicion_vehiculo"].map({"N":"Nuevo", "U":"Usado"}).fillna(df["condicion_vehiculo"].astype(str))
    # La segmentación de los gráficos se hace exclusivamente con perfil_label.
    if "ocupacion_agg" in df.columns:
        df["perfil_label"] = df["ocupacion_agg"].fillna("Sin dato").astype(str)
    elif "descripcion_ocupacion" in df.columns:
        df["perfil_label"] = df["descripcion_ocupacion"].fillna("Sin dato").astype(str)
    else:
        df["perfil_label"] = "Sin perfil"
    return df
