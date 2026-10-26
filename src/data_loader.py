import json
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "data_desembolsos_2024_2025.csv"
SEGMENTACION_PATH = ROOT / "config" / "segmentacion.json"

@st.cache_data(show_spinner=False)
def load_data():
    # El archivo conserva extensión .csv pero puede venir en formato parquet.
    with open(DATA_PATH, "rb") as f:
        is_parquet = f.read(4) == b"PAR1"
    if is_parquet:
        df = pd.read_parquet(DATA_PATH)
    else:
        df = pd.read_csv(DATA_PATH, sep=";", encoding="utf-8-sig", low_memory=False)
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]
    return df

def _norm(value):
    return " ".join(str(value).split()).casefold()

def load_segmentacion():
    with open(SEGMENTACION_PATH, encoding="utf-8") as f:
        mapping = json.load(f)
    return {_norm(k): v for k, v in mapping.items()}

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
    if "descripcion_ocupacion" in df.columns:
        mapping = load_segmentacion()
        df["segmentacion"] = df["descripcion_ocupacion"].map(
            lambda x: mapping.get(_norm(x), "Sin dato") if pd.notna(x) else "Sin dato"
        )
    else:
        df["segmentacion"] = "Sin perfil"
    # Los gráficos segmentan por perfil_label, que corresponde a la segmentación.
    df["perfil_label"] = df["segmentacion"]
    return df
