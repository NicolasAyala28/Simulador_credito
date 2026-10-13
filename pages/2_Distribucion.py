import math
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from src.data_loader import load_data, prepare_data

st.set_page_config(page_title="Distribución de variables", page_icon="📊", layout="wide")

from src.theme import apply_finanzauto_theme
apply_finanzauto_theme()


# Paleta verde corporativa inspirada en Finanzauto.
GREEN_PALETTE = ["#064B39", "#008F65", "#35B779", "#A4CE39", "#2F6B4F", "#70C1A1", "#C5DF8B"]
BG = "#FFFFFF"
GRID = "#E5EFEA"
TEXT = "#153C32"

NUMERIC_VARS = [
    ("acierta", "Acierta"),
    ("Frank", "Frank"),
    ("ingresos", "Ingresos"),
    ("cuota_inicial", "Cuota inicial"),
    ("ValorVh", "Valor del vehículo"),
    ("NumeroConsultas", "Número de consultas"),
]
CATEGORICAL_VARS = [
    ("estado_civil", "Estado civil"),
    ("licencia_label", "Tipo de licencia"),
    ("condicion_label", "Condición del vehículo"),
    ("productivo", "Productivo"),
    ("PlanFinanciacion", "Plan de financiación"),
    ("descripcion_ocupacion", "Descripción de ocupación"),
]

df = prepare_data(load_data())

# Excluir perfiles nulos/erróneos y la categoría "Otros" de esta página.
invalid_profile_values = {"otros", "otro", "nan", "none", "null", ""}
df["perfil_label"] = df["perfil_label"].astype("string").str.strip()
df = df[df["perfil_label"].notna()]
df = df[~df["perfil_label"].str.casefold().isin(invalid_profile_values)]
st.markdown("""
<style>
.block-container {padding-top: 1.1rem; padding-bottom: 1rem; max-width: 1800px;}
h1, h2, h3 {color: #153C32;}
.section-title {border-left: 5px solid #16866A; padding-left: 10px; margin: 0.3rem 0 0.8rem 0;}
[data-testid="stMetric"] {background:#F3F8F5; border:1px solid #DCEBE3; padding:12px; border-radius:10px;}
div[data-testid="stDataFrame"] {border:1px solid #E1ECE6; border-radius:8px;}
</style>
""", unsafe_allow_html=True)

st.title("Distribución de variables")
st.write(
    "Analiza la distribución de las principales variables de la base, diferenciada por perfil "
    "(`perfil_label`). Cada gráfico compara los perfiles y presenta sus estadísticos correspondientes."
)

# Filtros superiores: únicamente Perfil, Año y Mes.
with st.container(border=True):
    st.markdown("**Filtros de datos**")
    f1, f2, f3 = st.columns([1.5, 1, 1])
    profiles = sorted(df["perfil_label"].dropna().astype(str).unique().tolist())
    years = sorted(df["fecha_desembolso"].dropna().dt.year.unique().tolist()) if "fecha_desembolso" in df else []
    months = list(range(1, 13))
    month_names = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
    with f1:
        selected_profile = st.selectbox("Perfil", ["Todos"] + profiles, key="distribution_profile")
    with f2:
        selected_year = st.selectbox("Año", ["Todos"] + years, key="distribution_year")
    with f3:
        selected_month = st.selectbox("Mes", ["Todos"] + months, format_func=lambda x: x if x == "Todos" else month_names[x], key="distribution_month")

filtered = df.copy()
if selected_profile != "Todos":
    filtered = filtered[filtered["perfil_label"].astype(str) == selected_profile]
if selected_year != "Todos":
    filtered = filtered[filtered["fecha_desembolso"].dt.year == int(selected_year)]
if selected_month != "Todos":
    filtered = filtered[filtered["fecha_desembolso"].dt.month == int(selected_month)]

st.caption(f"Registros según filtros: {len(filtered):,}".replace(",", "."))

def profile_color_map(data):
    labels = sorted(data["perfil_label"].dropna().astype(str).unique().tolist())
    return {label: GREEN_PALETTE[i % len(GREEN_PALETTE)] for i, label in enumerate(labels)}

def numeric_stats(data, col):
    rows = []
    for profile, group in data.groupby("perfil_label", dropna=False, sort=True):
        values = pd.to_numeric(group[col], errors="coerce").dropna()
        if values.empty:
            continue
        rows.append({
            "Perfil": str(profile),
            "Registros": len(values),
            "Promedio": values.mean(),
            "Desv. est.": values.std(),
            "Mín.": values.min(),
            "Q1": values.quantile(.25),
            "Mediana": values.median(),
            "Q3": values.quantile(.75),
            "Máx.": values.max(),
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result["Registros"] = result["Registros"].map(lambda x: f"{x:,}".replace(",", "."))
        for c in ["Promedio", "Desv. est.", "Mín.", "Q1", "Mediana", "Q3", "Máx."]:
            result[c] = result[c].map(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    return result

def categorical_stats(data, col):
    temp = data[["perfil_label", col]].copy()
    temp[col] = temp[col].fillna("Sin dato").astype(str)
    if temp.empty:
        return pd.DataFrame()
    counts = pd.crosstab(temp[col], temp["perfil_label"])
    pct = counts.div(counts.sum(axis=0).replace(0, 1), axis=1) * 100
    # Long table: one row per category and profile, with count and percentage.
    rows = []
    for category in counts.index:
        for profile in counts.columns:
            rows.append({
                "Categoría": category,
                "Perfil": profile,
                "Registros": int(counts.loc[category, profile]),
                "% dentro del perfil": round(float(pct.loc[category, profile]), 2),
            })
    return pd.DataFrame(rows)

def format_number(x):
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:.1f} M"
    if abs(x) >= 1_000:
        return f"{x/1_000:.1f} mil"
    return f"{x:.1f}"

st.markdown('<h3 class="section-title">Variables numéricas</h3>', unsafe_allow_html=True)
numeric_cols = st.columns(3, gap="small")
for i, (col, label) in enumerate(NUMERIC_VARS):
    with numeric_cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"**{label}**")
            if col not in filtered.columns:
                st.warning(f"No se encontró la columna `{col}`.")
                continue
            plot_data = filtered[["perfil_label", col]].copy()
            plot_data[col] = pd.to_numeric(plot_data[col], errors="coerce")
            plot_data[col] = plot_data[col].replace([float("inf"), float("-inf")], pd.NA)
            plot_data = plot_data.dropna(subset=[col, "perfil_label"])
            if plot_data.empty:
                st.info("Sin datos para los filtros seleccionados.")
                continue
            fig = px.histogram(
                plot_data, x=col, color="perfil_label", barmode="overlay",
                opacity=0.58, nbins=30, color_discrete_map=profile_color_map(plot_data),
                labels={col: label, "count": "Frecuencia", "perfil_label": "Perfil"},
            )
            fig.update_layout(
                height=300, margin=dict(l=8,r=135,t=8,b=28), paper_bgcolor="white",
                plot_bgcolor="white", font=dict(color=TEXT, size=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left", font=dict(size=9), bgcolor="rgba(255,255,255,0.85)"),
                xaxis=dict(showgrid=True, gridcolor=GRID, title=None, automargin=True, ticks="outside", showticklabels=True),
                yaxis=dict(showgrid=True, gridcolor=GRID, title="Frecuencia"),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"distribution_numeric_{col}")
            st.markdown("**Estadísticos por perfil**")
            stats = numeric_stats(filtered, col)
            st.dataframe(stats, width="stretch", hide_index=True, height=205)

st.markdown('<h3 class="section-title">Variables categóricas</h3>', unsafe_allow_html=True)
categorical_cols = st.columns(3, gap="small")
for i, (col, label) in enumerate(CATEGORICAL_VARS):
    with categorical_cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"**{label}**")
            if col not in filtered.columns:
                st.warning(f"No se encontró la columna `{col}`.")
                continue
            plot_data = filtered[["perfil_label", col]].copy()
            plot_data[col] = plot_data[col].astype("string").str.strip()
            invalid_values = {"", "nan", "none", "null", "n/a", "na", "sin dato"}
            plot_data = plot_data[plot_data[col].notna()]
            plot_data = plot_data[~plot_data[col].str.casefold().isin(invalid_values)]
            plot_data[col] = plot_data[col].astype(str)
            if plot_data.empty:
                st.info("Sin datos para los filtros seleccionados.")
                continue
            counts = (plot_data.groupby(["perfil_label", col]).size()
                      .rename("Registros").reset_index())
            counts["Porcentaje"] = counts["Registros"] / counts.groupby("perfil_label")["Registros"].transform("sum") * 100
            # Barras agrupadas: una barra por perfil dentro de cada categoría.
            fig = px.bar(
                counts, x="Porcentaje", y=col, color="perfil_label", orientation="h",
                barmode="group", color_discrete_map=profile_color_map(plot_data),
                labels={col: label, "Porcentaje": "% dentro del perfil", "perfil_label": "Perfil"},
            )
            fig.update_layout(
                height=275, margin=dict(l=8,r=8,t=48,b=28), paper_bgcolor="white",
                plot_bgcolor="white", font=dict(color=TEXT, size=10),
                legend=dict(
                    orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02,
                    font=dict(size=9), bgcolor="rgba(255,255,255,0.92)",
                    bordercolor=GRID, borderwidth=1,
                ),
                xaxis=dict(showgrid=True, gridcolor=GRID, title=None, automargin=True, ticks="outside", showticklabels=True),
                yaxis=dict(showgrid=False, title="", categoryorder="total ascending"),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"distribution_categorical_{col}")
            st.markdown("**Distribución por perfil**")
            # Tabla compacta de porcentaje, útil para comparar perfiles.
            pct_table = counts.pivot(index=col, columns="perfil_label", values="Porcentaje").fillna(0).round(1)
            pct_table.index.name = "Categoría"
            st.dataframe(pct_table, width="stretch", height=205)

st.markdown("""
<div style="background:#EFF7F2;border:1px solid #CFE5D8;border-radius:10px;padding:12px 16px;margin-top:8px;">
<b style="color:#006B52;">Notas</b>
<ul style="margin-bottom:0;">
<li>Los gráficos muestran la distribución por <code>perfil_label</code>; se excluyen perfiles nulos y la categoría "Otros".</li>
<li>Los filtros superiores son Perfil, Año y Mes; se aplican a todos los gráficos y tablas.</li>
<li>Los nulos, valores infinitos y marcadores textuales de dato faltante se excluyen de cada gráfico y sus estadísticos; los porcentajes categóricos se calculan sobre los valores válidos dentro de cada perfil.</li>
<li>En las tablas de variables categóricas, cada porcentaje corresponde a la participación de la categoría dentro de los registros válidos del perfil; por eso, cada columna representa una distribución porcentual por perfil.</li>
</ul>
</div>
""", unsafe_allow_html=True)
