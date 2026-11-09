"""Apetito 2: matrices de vehículo para ver cuánto pesa la cuota inicial frente al valor del vehículo.

La hoja Apetito clasifica el vehículo por valor a financiar; aquí se separan sus dos partes: el % de cuota inicial
(filas) y el quintil del valor del vehículo (columnas), más la matriz licencia × condición. Solo análisis: no edita
parámetros. Usa los mismos filtros que Apetito.
"""
import numpy as np
import pandas as pd
import streamlit as st

from src.apetito import PRODUCTIVO_ORDER, tipo_credito
from src.data_loader import exclusion_notes
from src.filtros import base_filtrable, filtros_desembolso, nota_desembolsos, selector_base
from src.matrices import mora_separation
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Apetito 2", page_icon="🚗", layout="wide")
apply_finanzauto_theme()

MIN_AGE_OPTIONS = {"Todos": 0, "≥ 12 meses": 12, "≥ 15 meses": 15}
MORA_FILTROS = {"Mora > 30": 30, "Mora > 60": 60, "Mora > 90": 90}
LICENSE_ORDER = ["Particular", "Público"]
CONDITION_ORDER = ["Nuevo", "Usado"]
# Rangos de cuota inicial (% del valor del vehículo): cada rango incluye su límite inferior.
CUOTA_BINS = [0, 10, 20, 30, 40, 50, 60, 70, 100]
CUOTA_ORDER = ["<10%", "10–20%", "20–30%", "30–40%", "40–50%", "50–60%", "60–70%", "≥70%"]
VEHICULO_Q = [f"Q{q}" for q in range(1, 6)]
TIPOS = ["Todos"] + PRODUCTIVO_ORDER

def format_int(n):
    return f"{int(n):,}".replace(",", ".")

def quintil_vehiculo(data):
    """Quintil (Q1 a Q5) del valor del vehículo > 0 sobre las filas de data, y la etiqueta de cada quintil con su
    intervalo en millones. Los empates quedan en el mismo quintil."""
    valor = pd.to_numeric(data.get("ValorVh", pd.Series(np.nan, index=data.index)), errors="coerce")
    valor = valor.where(valor > 0)
    q = np.ceil(valor.rank(pct=True, method="max") * 5)
    rangos = ("Q" + q.astype("Int64").astype("string")).astype("string")
    etiquetas = {}
    for r in VEHICULO_Q:
        v = valor[rangos.eq(r).fillna(False)] / 1e6
        etiquetas[r] = f"{r} · {v.min():,.0f}–{v.max():,.0f} M".replace(",", ".") if len(v) else r
    return rangos, etiquetas

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Apetito 2: cuota inicial y valor del vehículo</h1>
  <p>Concentración y mora por % de cuota inicial y quintil del valor del vehículo, y por licencia × condición.</p>
</div>
""", unsafe_allow_html=True)

DATA = base_filtrable()
NOTAS = exclusion_notes(dict(DATA.attrs))
# Mismo criterio de segmento válido que la hoja Apetito.
profiles = DATA.get("perfil_label", pd.Series(pd.NA, index=DATA.index)).astype("string").str.strip()
valid = profiles.notna() & ~profiles.str.casefold().isin({"", "otros", "otro", "nan", "none", "null"})
DATA = DATA[valid].copy()
DATA["perfil_label"] = profiles[valid].astype(str)
DATA_FILTROS = DATA

# ---------------- Filtros (los mismos de la hoja Apetito) ----------------
c_base, c_profile, c_age = st.columns([1, 1.4, 1.6], gap="medium")
base = selector_base("apetito2_base", c_base)
with c_profile:
    selected_profile = st.selectbox("Segmento", ["Todos"] + sorted(DATA["perfil_label"].unique().tolist()),
                                    key="apetito2_profile_filter")
with c_age:
    min_age_label = st.radio("Antigüedad mínima", list(MIN_AGE_OPTIONS), index=2, horizontal=True, key="apetito2_min_age",
        help="Meses desde el desembolso hasta la fecha de corte. Los créditos cancelados antes se conservan.")
DATA, _ = filtros_desembolso(DATA, base, "apetito2")
if MIN_AGE_OPTIONS[min_age_label] and "meses_vida" in DATA:
    # La antigüedad solo aplica a las desembolsadas; las solicitudes sin desembolso (sin meses de vida) se conservan.
    vida = DATA["meses_vida"]
    DATA = DATA[vida.ge(MIN_AGE_OPTIONS[min_age_label]).fillna(False) | vida.isna()]
DATA = DATA if selected_profile == "Todos" else DATA[DATA["perfil_label"].eq(selected_profile)]
st.metric("Con los filtros actuales", format_int(len(DATA)), border=True,
          help=f"Registros de la base {base} que quedan con los filtros seleccionados.")
if base == "Desembolsos":
    NOTAS.append(nota_desembolsos(DATA_FILTROS))

# Por defecto mora > 90: la definición de incumplimiento de originación.
mora_label = st.radio("Mora máxima a 15 meses", list(MORA_FILTROS), index=2, horizontal=True, key="apetito2_mora",
                      help="Créditos con mora_max_15m mayor al umbral. Se usa en las tablas de mora.")

# ---------------- Variables de las matrices ----------------
DATA = DATA.copy()
mora = pd.to_numeric(DATA.get("mora_max_15m", pd.Series(np.nan, index=DATA.index)), errors="coerce")
DATA["con_mora"] = mora.gt(MORA_FILTROS[mora_label]).fillna(False)
DATA["desembolsado"] = DATA["desembolsado_base"].astype(bool)
DATA["Tipo"] = tipo_credito(DATA)
# cuota_inicial: MontoCtaInicial / ValorVh en % (clean_data); 100 % o más no es válida y queda vacía.
cuota = pd.to_numeric(DATA.get("cuota_inicial", pd.Series(np.nan, index=DATA.index)), errors="coerce")
DATA["Cuota inicial"] = pd.cut(cuota, CUOTA_BINS, right=False, labels=CUOTA_ORDER).astype("string")
DATA["Valor vehículo"], VEH_LABELS = quintil_vehiculo(DATA)
for col, source, order in [("Licencia", "licencia_label", LICENSE_ORDER), ("Condición", "condicion_label", CONDITION_ORDER)]:
    values = DATA.get(source, pd.Series(pd.NA, index=DATA.index)).astype("string").str.strip()
    DATA[col] = values.where(values.isin(order))

def por_tipo(render):
    """Una pestaña por tipo de crédito (todos, productivo y consumo)."""
    for tipo, tab in zip(TIPOS, st.tabs(TIPOS)):
        with tab:
            d = DATA if tipo == "Todos" else DATA[DATA["Tipo"].eq(tipo)]
            render(d, "todos los créditos" if tipo == "Todos" else f"los créditos de {tipo.lower()}")

# ---------------- 1. Cuota inicial x valor del vehículo ----------------
st.markdown('<div class="fa-section">1. % de cuota inicial × quintil del valor del vehículo</div>', unsafe_allow_html=True)
por_tipo(lambda d, base_label: mora_separation(d, "Cuota inicial", "Valor vehículo", CUOTA_ORDER, VEHICULO_Q,
    "Cuota inicial", False, base_label, col_labels=VEH_LABELS, mora_label=mora_label))
st.caption("Filas: cuota inicial como % del valor del vehículo (MontoCtaInicial / ValorVh); cada rango incluye su "
           "límite inferior. Columnas: quintiles del valor del vehículo sobre los registros filtrados (Q1 los de menor "
           "valor), en millones de pesos. Cada celda es la proporción sobre el total de la tabla.")

# ---------------- 2. Licencia x condición ----------------
st.markdown('<div class="fa-section">2. Licencia × condición</div>', unsafe_allow_html=True)
por_tipo(lambda d, base_label: mora_separation(d, "Licencia", "Condición", LICENSE_ORDER, CONDITION_ORDER,
    "Licencia", False, base_label, mora_label=mora_label))
st.caption("Cada celda es la proporción sobre el total de la tabla.")

# ---------------- Notas ----------------
sin_cuota = int(DATA["Cuota inicial"].isna().sum())
sin_valor = int(DATA["Valor vehículo"].isna().sum())
sin_lic = int((DATA["Licencia"].isna() | DATA["Condición"].isna()).sum())
if sin_cuota or sin_valor:
    NOTAS.append(f"No entran en la matriz 1: {format_int(sin_cuota)} registros sin % de cuota inicial válido (sin valor "
                 f"del vehículo o cuota inicial, o cuota de 100 % o más) y {format_int(sin_valor)} sin valor del vehículo.")
if sin_lic:
    NOTAS.append(f"No entran en la matriz 2: {format_int(sin_lic)} registros sin licencia o condición válida.")
sin_tipo = int(DATA["Tipo"].eq("Sin dato").sum())
if sin_tipo:
    NOTAS.append(f"{format_int(sin_tipo)} registros sin dato de productivo: solo aparecen en la pestaña Todos.")
if NOTAS:
    st.markdown('<div class="fa-section">Notas sobre registros omitidos</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("\n".join(f"- {n}" for n in NOTAS))
