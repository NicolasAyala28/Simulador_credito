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

def _to_number(series):
    # Los montos llegan como texto con comas de miles o como Decimal.
    s = series.astype("string").str.strip().str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")

# Columnas descartadas en la auditoría de calidad: traslado es constante;
# IngresoTotalMensual y ValorCuotaCST se reemplazan por ingresos y ValorCuotaSectorTelcos.
DROP_COLUMNS = ["traslado", "IngresoTotalMensual", "ValorCuotaCST"]
INGRESO_MIN = 1_000_000
INGRESO_MAX = 100_000_000

def clean_data(df):
    """Reglas de calidad acordadas en la auditoría de la base de desembolsos."""
    df = df.copy()
    for col in ["valor_garantia_inicial", "ValorVh", "MontoCtaInicial", "ingresos"]:
        if col in df.columns:
            df[col] = _to_number(df[col])
    # ValorVh viene en 0 en ~28 % de la base; el valor oficial es valor_garantia_inicial.
    if {"ValorVh", "valor_garantia_inicial"} <= set(df.columns):
        garantia = df["valor_garantia_inicial"]
        df["ValorVh"] = garantia.where(garantia > 0, df["ValorVh"])
    # La cuota inicial (%) se recalcula como MontoCtaInicial / valor del vehículo.
    if {"MontoCtaInicial", "ValorVh"} <= set(df.columns):
        cuota = df["MontoCtaInicial"].div(df["ValorVh"].where(df["ValorVh"] > 0)).mul(100)
        # Una cuota inicial de 100 % o más no es válida.
        df["cuota_inicial"] = cuota.where(cuota < 100)
    # Ingreso válido para PTI/DTI/EI: entre 1 y 100 millones mensuales.
    if "ingresos" in df.columns:
        df["ingresos"] = df["ingresos"].where(df["ingresos"].between(INGRESO_MIN, INGRESO_MAX))
    return df.drop(columns=[c for c in DROP_COLUMNS if c in df.columns])

def prepare_data(df):
    df = clean_data(df)
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
