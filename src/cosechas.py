"""Datos y cálculos de cosechas (ICC, rodamientos y acumulación del default), compartidos por las hojas
de Cosechas. Replica las secciones 3, 4.2, 5 y 6 del notebook Score/default/default.ipynb."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.data_loader import ROOT, load_segmentacion, map_ocupacion_avalista1, segmentacion_final
from src.distribucion import GREEN_PALETTE, GRID, TEXT

# Base crédito-mes sin traslados, con la ocupación del avalista 1 (generada en el notebook).
COSECHAS_PATH = ROOT / "data" / "cosechas_2022_092025_ST.parquet"
# Mora que se mide: etiqueta del filtro -> días de mora que se deben superar.
UMBRALES_MORA = {"ICC 60 (mora > 60 días)": 60, "ICC 90 (mora > 90 días)": 90}
ALTURA_MAXIMA = 24
BANDA_OBJETIVO = (0.60, 0.80)


def _fecha(col):
    return pd.to_datetime(col.astype("string").str.replace(r"\.0$", "", regex=True), format="%Y%m%d")


@st.cache_data(show_spinner="Cargando base de cosechas…")
def load_cosechas():
    """Base crédito-mes con cosecha, altura y segmento. Excluye, como el notebook (sección 2.1),
    los créditos con algún corte anterior al desembolso (altura -1) y los de segmento 'Sin dato'.
    Devuelve (df, exclusiones)."""
    df = pd.read_parquet(COSECHAS_PATH)
    df["fecha_desembolso"] = _fecha(df["id_fecha_desembolso"])
    df["fecha_corte"] = _fecha(df["id_fecha"])
    df["cosecha"] = df["fecha_desembolso"].dt.year
    # Altura 0 = mes del desembolso.
    df["altura"] = ((df["fecha_corte"].dt.year - df["fecha_desembolso"].dt.year) * 12
                    + (df["fecha_corte"].dt.month - df["fecha_desembolso"].dt.month))
    df = map_ocupacion_avalista1(df)
    df["segmento"] = segmentacion_final(df, load_segmentacion())

    altura_negativa = set(df.loc[df["altura"] < 0, "credito"])
    sin_dato = set(df.loc[df["segmento"].eq("Sin dato"), "credito"])
    exclusiones = {"altura_negativa": len(altura_negativa), "sin_dato": len(sin_dato),
                   "total": len(altura_negativa | sin_dato)}
    return df[~df["credito"].isin(altura_negativa | sin_dato)].copy(), exclusiones


def ultima_altura_completa(cosecha, ultimo_corte):
    """Última altura que alcanzan todos los créditos de la cosecha (los desembolsados en diciembre)."""
    return (ultimo_corte.year - cosecha) * 12 + (ultimo_corte.month - 12)


def calcular_icc(df, umbral, grupo=None, solo_alturas_completas=True):
    """ICC por cosecha y altura: saldo de capital con más de `umbral` días de mora
    / monto desembolsado de la cosecha (créditos en altura 0)."""
    claves = ([grupo] if grupo else []) + ["cosecha"]
    vencido = df["saldo_capital"].where(df["numero_dias_mora"] > umbral, 0)
    icc = df.assign(saldo_vencido=vencido).groupby(claves + ["altura"])["saldo_vencido"].sum().reset_index()
    desembolso = (df.loc[df["altura"] == 0].groupby(claves)["valor_desembolso"].sum()
                  .rename("desembolso_cosecha"))
    icc = icc.merge(desembolso, on=claves)
    icc["icc"] = icc["saldo_vencido"] / icc["desembolso_cosecha"]
    if solo_alturas_completas:
        # Al final de cada curva solo quedan los créditos de comienzo de año y el ICC cae de forma artificial.
        icc = icc[icc["altura"] <= ultima_altura_completa(icc["cosecha"], df["fecha_corte"].max())]
    return icc


def curva_acumulada(df, umbral, por_monto=False, claves=("cosecha",), altura_maxima=ALTURA_MAXIMA):
    """Acumulación, por altura, de los créditos (o de su monto desembolsado) que superan `umbral`
    días de mora por primera vez, por cada combinación de `claves`. `proporcion` se mide sobre
    los eventos observados hasta `altura_maxima` (termina en 100 %); `tasa`, sobre el total del grupo."""
    claves = list(claves)
    datos = df[df["altura"].between(0, altura_maxima)]
    # Universo: créditos en altura 0.
    creditos = datos.loc[datos["altura"] == 0].drop_duplicates("credito")[claves + ["credito", "valor_desembolso"]]
    primer_evento = (datos.loc[datos["numero_dias_mora"] > umbral].groupby("credito")["altura"].min()
                     .rename("altura_evento"))
    creditos = creditos.join(primer_evento, on="credito")
    creditos["peso"] = creditos["valor_desembolso"] if por_monto else 1.0

    alturas = list(range(altura_maxima + 1))
    acumulado = (creditos.dropna(subset=["altura_evento"])
                 .pivot_table(index=claves, columns="altura_evento", values="peso", aggfunc="sum")
                 .reindex(columns=alturas).fillna(0).cumsum(axis=1))
    curva = acumulado.stack().rename("acumulado").reset_index().rename(columns={"altura_evento": "altura"})
    resumen = creditos.groupby(claves).agg(total=("peso", "sum"), creditos=("credito", "size"))
    curva = curva.join(resumen, on=claves)
    curva["total_eventos"] = curva.groupby(claves)["acumulado"].transform("max")
    curva["proporcion"] = curva["acumulado"] / curva["total_eventos"]
    curva["tasa"] = curva["acumulado"] / curva["total"]
    return curva[curva["total_eventos"] > 0]


def tabla_ventana(curva, claves=("cosecha",), mes_captura=15):
    """Por grupo: eventos y tasa a 24 meses, altura en que se acumula el 60 % y el 80 %
    de los eventos, y proporción capturada en el mes `mes_captura`."""
    claves = list(claves)
    filas = []
    for clave, d in curva.groupby(claves, sort=False):
        d = d.sort_values("altura")
        fila = dict(zip(claves, clave if isinstance(clave, tuple) else (clave,)))
        fila.update({
            "creditos": d["creditos"].iloc[0],
            "total": d["total"].iloc[0],
            "eventos": d["total_eventos"].iloc[0],
            "tasa": d["tasa"].iloc[-1],
            "altura_60": d.loc[d["proporcion"] >= BANDA_OBJETIVO[0], "altura"].min(),
            "altura_80": d.loc[d["proporcion"] >= BANDA_OBJETIVO[1], "altura"].min(),
            "captura": d.loc[d["altura"] == mes_captura, "proporcion"].max(),
        })
        filas.append(fila)
    return pd.DataFrame(filas)


def colores_series(series):
    return {s: GREEN_PALETTE[i % len(GREEN_PALETTE)] for i, s in enumerate(series)}


def grafico_curvas(datos, y, serie, y_titulo, x="altura", x_titulo="Altura (meses)", faceta=None, paneles=None,
                   orden_series=None, formato_y=".1%", banda=None, hover="", customdata=None, x_categorica=False,
                   altura=480, columnas=2):
    """Una línea por valor de `serie`. Con `faceta`, un panel por valor de esa columna (eje Y compartido).
    `banda` sombrea un rango objetivo, p. ej. (0.6, 0.8). `altura` es la de cada fila de paneles."""
    paneles = [None] if faceta is None else (paneles or sorted(datos[faceta].unique()))
    series = orden_series or sorted(datos[serie].unique(), key=str)
    colores = colores_series(series)
    cols = min(columnas, len(paneles))
    filas = -(-len(paneles) // cols)
    fig = make_subplots(rows=filas, cols=cols, shared_yaxes="all", horizontal_spacing=0.05,
                        vertical_spacing=0.12 if filas > 1 else 0,
                        subplot_titles=[str(p) for p in paneles] if faceta else None)
    for k, panel in enumerate(paneles):
        fila, col = k // cols + 1, k % cols + 1
        d_panel = datos if faceta is None else datos[datos[faceta] == panel]
        for s in series:
            d = d_panel[d_panel[serie] == s].sort_values(x)
            if d.empty:
                continue
            fig.add_trace(go.Scatter(
                x=d[x], y=d[y], mode="lines+markers", name=str(s), legendgroup=str(s), showlegend=k == 0,
                line=dict(width=2.5, color=colores[s]), marker=dict(size=5),
                customdata=customdata(d) if customdata else None,
                hovertemplate=f"{s}: %{{y:{formato_y}}}{hover}<extra></extra>",
            ), row=fila, col=col)
        if banda:
            fig.add_hrect(y0=banda[0], y1=banda[1], fillcolor="#91D4A5", opacity=0.25, line_width=0, row=fila, col=col)
            fig.add_hline(y=banda[0], line_dash="dash", line_color="#E8A33D", row=fila, col=col)
            fig.add_hline(y=banda[1], line_dash="dash", line_color="#E84C3D", row=fila, col=col)
    if x_categorica:
        fig.update_xaxes(type="category")
    else:
        fig.update_xaxes(tickmode="linear", tick0=0, dtick=3)
    fig.update_xaxes(gridcolor=GRID)
    fig.update_xaxes(title=x_titulo, row=filas)
    fig.update_yaxes(tickformat=formato_y, gridcolor=GRID, rangemode="tozero")
    fig.update_yaxes(title=y_titulo, col=1)
    fig.update_layout(
        height=altura * filas, margin=dict(l=10, r=10, t=30 if faceta else 10, b=10), paper_bgcolor="white",
        plot_bgcolor="white", font=dict(color=TEXT), hovermode="x unified", separators=",.",
        legend=dict(orientation="h", y=1.02 + (0.04 if faceta else 0), yanchor="bottom", x=0, title=serie.capitalize()),
    )
    return fig


# Rangos de mora de 30 días: 0 (al día), 30 (1–30), ..., 360 (más de 330 días).
RANGOS_MORA = list(range(0, 361, 30))
ETIQUETAS_RANGO = {r: "Al día" if r == 0 else ("> 330" if r == 360 else f"{r - 29}–{r}") for r in RANGOS_MORA}


def transiciones_mora(df, claves=()):
    """Una fila por crédito y mes con el rango de mora del mes y el del mes anterior.
    Solo se conservan las transiciones entre meses consecutivos."""
    claves = list(claves)
    d = df[["credito", "fecha_corte", "numero_dias_mora"] + claves].dropna().sort_values(["credito", "fecha_corte"])
    d["rango_actual"] = (np.ceil(d["numero_dias_mora"].clip(lower=0) / 30) * 30).clip(upper=360).astype(int)
    d["mes"] = d["fecha_corte"].dt.year * 12 + d["fecha_corte"].dt.month
    previo = d.groupby("credito")[["rango_actual", "mes"]].shift(1)
    d["rango_anterior"] = previo["rango_actual"]
    return d[(d["mes"] - previo["mes"]) == 1].astype({"rango_anterior": int})


def calcular_roll_rate(transiciones, claves=()):
    """Roll rate por rango de mora anterior (y por cada combinación de `claves`).
    Recuperación: el crédito baja de rango o se mantiene. Deterioro: sube de rango."""
    claves = list(claves)
    d = transiciones.assign(recupera=transiciones["rango_actual"] <= transiciones["rango_anterior"])
    rr = d.groupby(claves + ["rango_anterior"])["recupera"].agg(transiciones="size", recuperacion="mean").reset_index()
    rr["deterioro"] = 1 - rr["recuperacion"]
    return rr


def rango_cruce(roll_rate):
    """Primer rango de mora desde el cual el deterioro supera a la recuperación."""
    cruce = roll_rate.loc[roll_rate["deterioro"] > roll_rate["recuperacion"], "rango_anterior"]
    return int(cruce.min()) if not cruce.empty else None


def grafico_roll_rate(roll_rate, umbral=None, altura=480):
    """Recuperación vs. deterioro por rango de mora anterior. Si se indica `umbral`,
    sombrea los rangos con mora mayor a ese umbral."""
    d = roll_rate.sort_values("rango_anterior")
    x = d["rango_anterior"].map(ETIQUETAS_RANGO)
    fig = go.Figure()
    for col, nombre, color in [("recuperacion", "Recuperación", "#008F65"), ("deterioro", "Deterioro", "#E84C3D")]:
        fig.add_trace(go.Scatter(
            x=x, y=d[col], mode="lines+markers", name=nombre, line=dict(width=3, color=color), marker=dict(size=7),
            customdata=d[["transiciones"]].to_numpy(),
            hovertemplate=f"{nombre}: %{{y:.1%}}<br>Transiciones: %{{customdata[0]:,.0f}}<extra></extra>",
        ))
    if umbral is not None:
        # Eje categórico: cada rango ocupa una posición entera; se sombrea desde el primer rango > umbral.
        desde = list(d["rango_anterior"]).index(min(r for r in d["rango_anterior"] if r > umbral))
        fig.add_vrect(x0=desde - 0.5, x1=len(d) - 0.5, fillcolor="#FFD65B", opacity=0.15, line_width=0,
                      annotation_text=f"Mora > {umbral} días", annotation_position="top left")
    fig.update_xaxes(title="Rango de mora anterior (días)", type="category", gridcolor=GRID)
    fig.update_yaxes(title="Tasa de transición", tickformat=".0%", range=[0, 1.05], gridcolor=GRID)
    fig.update_layout(
        height=altura, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(color=TEXT), hovermode="x unified", separators=",.",
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0),
    )
    return fig
