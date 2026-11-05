import json
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
# Base de solicitudes (frank_requests + frank_responses) con la mora a 15 meses de las desembolsadas;
# la genera motor_decision/generacion_base.ipynb.
DATA_PATH = ROOT / "data" / "solicitudes_2024_2025.parquet"
SEGMENTACION_PATH = ROOT / "config" / "segmentacion.json"
OCUPACION_AVAL_PATH = ROOT / "config" / "ocupacion_aval.json"
# Códigos de ClaseVehiculo, EstadoCivil, Licencia y Condicion de la solicitud, extraídos del diccionario Variables Frank.
CODIGOS_SOLICITUD_PATH = ROOT / "config" / "codigos_solicitud.json"
AVALISTA1_OCUPACION_CODIGO = "Avalista1Ocupacion"
OCUPACION_AVALISTA1 = "Ocupacion_avalista1"
# Nombres canónicos de columnas que la fuente ha entregado con distinto uso de mayúsculas.
CANONICAL_COLUMNS = ["Frank", "FGA", "FrankDecision", "PlanFinanciacion"]
MORA_MAX_15M = "mora_max_15m"
MORA_MAX_15M_ALIASES = {"mora_max_15m", "max_mora_15m"}
# Campos de la base de solicitudes -> nombres que usa el simulador (los de la base de desembolsos).
SOLICITUD_COLUMNS = {
    "Acierta": "acierta", "IngresoTotalMensual": "ingresos", "TasaMV": "tasa_nominal",
    # ValorCuotaCST es la cuota con sector telcos (diccionario Variables Frank): alimenta el DTI.
    "ValorCuotaCST": "ValorCuotaSectorTelcos", "Licencia": "licencia_vehiculo", "Condicion": "condicion_vehiculo",
    "ClaseVehiculo": "clase_vehiculo", "Decision": "FrankDecision", "RIE": "RIE_motor",
}
# DestinoCredito: P = productivo, C = consumo.
DESTINO_PRODUCTIVO = {"P": "1", "C": "0"}
# Campos que el simulador no usa y que no deben quedar en memoria (identificadores y auxiliares).
SOLICITUD_DROP = ["n", "n_right", "solicitud_id", "numero_solicitud", "Avalista1AVId"]

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
    df = df.rename(columns=rename)
    return normalize_solicitudes(df) if "Ocupacion" in df.columns else df

def _codes(series, mapping):
    """Traduce códigos (5, 5.0 o "5") con mapping; los valores que ya vienen en texto se conservan y los
    códigos sin mapeo quedan visibles como "Código N sin mapeo"."""
    text = series.astype("string").str.strip()
    codes = pd.to_numeric(text, errors="coerce").astype("Int64").astype("string")
    unmapped = codes.map(lambda c: f"Código {c} sin mapeo" if pd.notna(c) else pd.NA).astype("string")
    return codes.map(mapping).astype("string").fillna(unmapped).fillna(text.where(codes.isna()))

def normalize_solicitudes(df):
    """Lleva la base de solicitudes a los nombres y formatos del simulador."""
    df = df.drop(columns=[c for c in SOLICITUD_DROP if c in df.columns])
    df = df.rename(columns={k: v for k, v in SOLICITUD_COLUMNS.items() if k in df.columns})
    with open(OCUPACION_AVAL_PATH, encoding="utf-8") as f:
        ocupaciones = json.load(f)
    with open(CODIGOS_SOLICITUD_PATH, encoding="utf-8") as f:
        codigos = json.load(f)
    # Ocupación, estado civil y clase de vehículo llegan como código; se traducen al texto que usan
    # segmentación, RIE (estado civil casado / unión libre) y la matriz de vehículo.
    df["descripcion_ocupacion"] = _codes(df.pop("Ocupacion"), ocupaciones)
    if "EstadoCivil" in df.columns:
        df["estado_civil"] = _codes(df.pop("EstadoCivil"), codigos["EstadoCivil"])
    if "clase_vehiculo" in df.columns:
        df["clase_vehiculo"] = _codes(df["clase_vehiculo"], codigos["ClaseVehiculo"])
    # Licencia (1 PAR, 2 PUB) y condición (1 N, 2 U) pueden llegar como código.
    if "licencia_vehiculo" in df.columns:
        df["licencia_vehiculo"] = _codes(df["licencia_vehiculo"].astype("string").str.upper(), codigos["Licencia"])
    if "condicion_vehiculo" in df.columns:
        df["condicion_vehiculo"] = _codes(df["condicion_vehiculo"].astype("string").str.upper(), codigos["Condicion"])
    # Tipo de crédito: la columna productivo de la base; donde venga vacía (por ejemplo, solicitudes no
    # desembolsadas) se completa con DestinoCredito de la solicitud (P/C -> 1/0; el texto se conserva).
    if "DestinoCredito" in df.columns:
        destino = df.pop("DestinoCredito").astype("string").str.strip().str.upper()
        destino = destino.map(DESTINO_PRODUCTIVO).fillna(destino)
        productivo = (df["productivo"].astype("string").str.strip() if "productivo" in df.columns
                      else pd.Series(pd.NA, index=df.index, dtype="string"))
        df["productivo"] = productivo.where(productivo.notna() & productivo.ne(""), destino)
    # Por instrucción del usuario: la marca de prenda de las solicitudes no es confiable, así que
    # se asume que ninguna garantía está prendada.
    for i in (1, 2, 3):
        df[f"RPV{i}Prendado"] = "NO"
    # Solo entran las solicitudes de 2024 que tienen respuesta del motor (frank_responses).
    fecha = pd.to_datetime(df.get("FechaProceso"), format="mixed", errors="coerce")
    sin_respuesta = df.get("FrankDecision", pd.Series(pd.NA, index=df.index)).isna()
    df = df[~(fecha.dt.year.eq(2024) & sin_respuesta)].copy()
    if "desembolsado" in df.columns:
        df["desembolsado"] = pd.to_numeric(df["desembolsado"], errors="coerce").fillna(0).astype(int)
    return df

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

# Alcance del estudio: se omiten las solicitudes con valor a financiar (ValorVh - MontoCtaInicial) mayor a este
# monto, por instrucción del usuario. df.attrs["excluidas_financiacion"] guarda cuántas se omitieron.
MAX_FINANCIACION = 180_000_000

def prepare_data(df, incluir_sin_dato=False):
    df = clean_data(df)
    financiar = pd.to_numeric(df.get("ValorVh"), errors="coerce") - pd.to_numeric(df.get("MontoCtaInicial"), errors="coerce")
    fuera = financiar.gt(MAX_FINANCIACION).fillna(False)
    df = df[~fuera].copy()
    df.attrs["excluidas_financiacion"] = int(fuera.sum())
    if "id_fecha_desembolso" in df.columns:
        raw = df["id_fecha_desembolso"].astype("string").str.replace(r"\.0$", "", regex=True)
        df["fecha_desembolso"] = pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
    # Meses observados: meses_observados o, si la base no lo trae, ventana (máxima altura observada,
    # con tope en 15 meses). Con el tope, la fecha de corte inferida puede quedar antes de la real,
    # pero todos los desembolsos de la foto fija (hasta 2025-04) cumplen 15 meses.
    observados_col = next((c for c in ["meses_observados", "ventana"] if c in df.columns), None)
    if "fecha_desembolso" in df.columns and observados_col:
        # La fecha de corte no viene en la base: es el último mes observado de cualquier crédito.
        mes_desembolso = df["fecha_desembolso"].dt.to_period("M")
        observados = pd.to_numeric(df[observados_col], errors="coerce")
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
    if {"licencia_label", "condicion_label"} <= set(df.columns):
        # veh: licencia/condición del vehículo (Público/Nuevo, Público/Usado, Particular/Nuevo, Particular/Usado);
        # sin licencia o condición válida queda en blanco.
        veh = df["licencia_label"].astype("string") + "/" + df["condicion_label"].astype("string")
        df["veh"] = veh.where(veh.isin(["Público/Nuevo", "Público/Usado", "Particular/Nuevo", "Particular/Usado"]))
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

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

def _rango_meses(fechas):
    fechas = pd.to_datetime(fechas, format="mixed", errors="coerce").dropna()
    if fechas.empty:
        return None
    a, b = fechas.min(), fechas.max()
    return f"{MESES[a.month - 1]} {a.year} – {MESES[b.month - 1]} {b.year}"

def study_periods(df):
    """Periodo de solicitudes (FechaProceso) y de desembolsos (fecha_desembolso de las desembolsadas).
    Si la base no trae la fecha de desembolso, el de desembolsos usa la fecha de solicitud de las
    desembolsadas y lo indica. Devuelve (periodo_solicitudes, periodo_desembolsos)."""
    solicitudes = _rango_meses(df["FechaProceso"]) if "FechaProceso" in df.columns else None
    desembolsadas = (pd.to_numeric(df["desembolsado"], errors="coerce").eq(1) if "desembolsado" in df.columns
                     else pd.Series(True, index=df.index))
    desembolsos = None
    if "fecha_desembolso" in df.columns:
        desembolsos = _rango_meses(df.loc[desembolsadas, "fecha_desembolso"])
    if desembolsos is None and solicitudes and desembolsadas.any():
        rango = _rango_meses(df.loc[desembolsadas, "FechaProceso"])
        desembolsos = f"{rango} (fecha de solicitud)" if rango else None
    return solicitudes or "No identificado", desembolsos or "No identificado"
