import json
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "data_desembolsos_2024_2025.csv"
SEGMENTACION_PATH = ROOT / "config" / "segmentacion.json"
OCUPACION_AVAL_PATH = ROOT / "config" / "ocupacion_aval.json"
AVALISTA1_OCUPACION_CODIGO = "Avalista1Ocupacion"
OCUPACION_AVALISTA1 = "Ocupacion_avalista1"
# Nombres canónicos de columnas que la fuente ha entregado con distinto uso de mayúsculas.
CANONICAL_COLUMNS = ["Frank", "FGA", "FrankDecision", "PlanFinanciacion"]
MORA_MAX_15M = "mora_max_15m"
MORA_MAX_15M_ALIASES = {"mora_max_15m", "max_mora_15m"}

@st.cache_data(show_spinner=False)
def load_data():
    # El archivo conserva extensión .csv pero puede venir en formato parquet.
    with open(DATA_PATH, "rb") as f:
        is_parquet = f.read(4) == b"PAR1"
    if is_parquet:
        df = pd.read_parquet(DATA_PATH)
    else:
        # La base se ha entregado separada por ';' y por ','; se toma el que domine en el encabezado.
        with open(DATA_PATH, encoding="utf-8-sig") as f:
            header = f.readline()
        sep = "," if header.count(",") >= header.count(",") else ","
        df = pd.read_csv(DATA_PATH, sep=sep, encoding="utf-8-sig", low_memory=False)
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]
    rename = {c: name for name in CANONICAL_COLUMNS for c in df.columns if c.casefold() == name.casefold()}
    # La mora máxima a 15 meses ha llegado como mora_max_15m y como max_mora_15m.
    rename.update({c: MORA_MAX_15M for c in df.columns
                   if str(c).strip().casefold() in MORA_MAX_15M_ALIASES})
    return df.rename(columns=rename)

def _norm(value):
    return " ".join(str(value).split()).casefold()

def load_segmentacion():
    with open(SEGMENTACION_PATH, encoding="utf-8") as f:
        mapping = json.load(f)
    return {_norm(k): v for k, v in mapping.items()}

def map_ocupacion_avalista1(df):
    """Crea Ocupacion_avalista1 traduciendo el código de Avalista1Ocupacion
    con config/ocupacion_aval.json. Si la base no trae ese código, no crea la columna."""
    source = AVALISTA1_OCUPACION_CODIGO
    if source not in df.columns:
        return df
    with open(OCUPACION_AVAL_PATH, encoding="utf-8") as f:
        mapping = json.load(f)
    # El código puede llegar como 5, 5.0 o "5"; los códigos sin mapeo quedan visibles.
    codes = pd.to_numeric(df[source], errors="coerce").astype("Int64").astype("string")
    df[OCUPACION_AVALISTA1] = codes.map(lambda c: mapping.get(c, f"Código {c} sin mapeo") if pd.notna(c) else pd.NA)
    return df

# Ocupaciones del titular que no están en config/segmentacion.json y toman el segmento
# de su avalista 1 (nombre normalizado -> nombre para mostrar).
OCUPACIONES_POR_AVALISTA = {"ama de casa": "Ama de Casa", "universitario": "Universitario"}
SEGMENTO_SIN_AVALISTA = "Independiente Informal"

def segmentacion_final(df, mapping):
    """1. Segmento de descripcion_ocupacion según config/segmentacion.json.
    2. Ama de Casa y Universitario toman el segmento de la ocupación del avalista 1
       (código traducido con config/ocupacion_aval.json).
    2.1 Si el avalista no tiene segmento (Ama de Casa, Universitario, sin avalista o sin dato),
        el titular queda en Independiente Informal.
    El resto de ocupaciones sin segmento queda como 'Sin dato'."""
    titular = df["descripcion_ocupacion"].map(lambda x: _norm(x) if pd.notna(x) else "")
    segmento = titular.map(lambda x: mapping.get(x, "Sin dato"))
    if OCUPACION_AVALISTA1 in df.columns:
        segmento_aval = df[OCUPACION_AVALISTA1].map(lambda x: mapping.get(_norm(x)) if pd.notna(x) else None)
    else:
        segmento_aval = pd.Series(None, index=df.index, dtype="object")
    por_avalista = titular.isin(OCUPACIONES_POR_AVALISTA) & segmento.eq("Sin dato")
    return segmento.where(~por_avalista, segmento_aval.fillna(SEGMENTO_SIN_AVALISTA))

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

def prepare_data(df, incluir_sin_dato=False):
    df = clean_data(df)
    if "id_fecha_desembolso" in df.columns:
        raw = df["id_fecha_desembolso"].astype("string").str.replace(r"\.0$", "", regex=True)
        df["fecha_desembolso"] = pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
    if {"fecha_desembolso", "meses_observados"} <= set(df.columns):
        # La fecha de corte no viene en la base: es el último mes observado de cualquier crédito.
        mes_desembolso = df["fecha_desembolso"].dt.to_period("M")
        observados = pd.to_numeric(df["meses_observados"], errors="coerce")
        corte = (mes_desembolso + observados.fillna(0).astype(int)).max()
        # Meses de vida desde el desembolso; a diferencia de meses_observados, no se reduce
        # cuando el crédito se cancela antes de completar la ventana.
        df["meses_vida"] = (corte - mes_desembolso).map(lambda d: d.n if pd.notna(d) else pd.NA).astype("Int64")
    if "mes_desem" in df.columns:
        df["mes_desem"] = pd.to_numeric(df["mes_desem"], errors="coerce").astype("Int64")
    if "licencia_vehiculo" in df.columns:
        df["licencia_label"] = df["licencia_vehiculo"].map({"PAR":"Particular", "PUB":"Público"}).fillna(df["licencia_vehiculo"].astype(str))
    if "condicion_vehiculo" in df.columns:
        df["condicion_label"] = df["condicion_vehiculo"].map({"N":"Nuevo", "U":"Usado"}).fillna(df["condicion_vehiculo"].astype(str))
    df = map_ocupacion_avalista1(df)
    if "descripcion_ocupacion" in df.columns:
        df["segmentacion"] = segmentacion_final(df, load_segmentacion())
    else:
        df["segmentacion"] = "Sin perfil"
    # Los registros sin ocupación no tienen perfil y se excluyen del análisis,
    # salvo que la página los necesite para contarlos.
    if not incluir_sin_dato:
        df = df[df["segmentacion"].ne("Sin dato")].copy()
    # Los gráficos segmentan por perfil_label, que corresponde a la segmentación.
    df["perfil_label"] = df["segmentacion"]
    return df
