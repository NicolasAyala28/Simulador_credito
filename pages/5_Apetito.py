import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import MAX_FINANCIACION, load_data, prepare_data
from src.apetito import (PRODUCTIVO_ORDER, PRODUCTIVO_SIN_DATO, PERCENTILES, VALOR_RANGOS, VEHICULO_ORDER, add_apetito,
    percentil_acierta, seed_defaults, valor_etiquetas, valor_rango)
from src.parametros import DECISION_OPTIONS, NIVELES, apetito_levels, rie_params, version_sidebar
from src.rie import rie_scores
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Árbol", page_icon="🌳", layout="wide")
apply_finanzauto_theme()

DATA = prepare_data(load_data())
DATA_FULL_ATTRS = dict(DATA.attrs)
DATA = DATA.reset_index(drop=True)

TEXT = "#0A2F4A"
# Antigüedad mínima desde el desembolso (meses de vida) para comparar créditos maduros.
MIN_AGE_OPTIONS = {"Todos": 0, "≥ 12 meses": 12, "≥ 15 meses": 15}

SEGMENT_ORDER = ["Empleado", "Independiente Formal", "Independiente Informal", "Transportador"]
# El RIE del árbol agrupa la normalización 0-3 del puntaje: 0 y 1 forman "0-1".
RIE_GROUPS = {0: "0-1", 1: "0-1", 2: "2", 3: "3"}
RIE_ORDER = ["0-1", "2", "3"]
LICENSE_ORDER = ["Particular", "Público"]
CONDITION_ORDER = ["Nuevo", "Usado"]

# Clasificación de apetito (src/apetito.py): perfil, vehículo y matriz perfil x vehículo por tipo de crédito.
MORA_FILTROS = {"Mora > 30": 30, "Mora > 60": 60, "Mora > 90": 90}
# Color de cada nivel de apetito: Bajo verde, Medio naranja, Alto rojo.
NIVEL_COLORS = {
    "Bajo": "background-color: #A8DDBF; color: #064B39",
    "Medio": "background-color: #FFC680; color: #6B3A00",
    "Alto": "background-color: #F19A90; color: #7A140B",
}
# Decisión de la matriz perfil x vehículo: Aprobado verde, Condiciones naranja, A estudio rojo.
DECISION_COLORS = dict(zip(DECISION_OPTIONS, NIVEL_COLORS.values()))
SIN_DECISION = "Sin decisión"
SIN_NIVEL = "Sin nivel"
DECISION_BAR_COLORS = dict(zip(DECISION_OPTIONS + [SIN_DECISION], ["#087A55", "#F29A2E", "#D9534F", "#9AA9B5"]))

def slug(value):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip().casefold())
    return value.strip("_") or "sin_perfil"

def format_int(n):
    return f"{int(n):,}".replace(",", ".")

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Árbol: apetito por vehículo y perfil</h1>
  <p>Clasificación de apetito por vehículo y por perfil, decisión por tipo de crédito y su distribución.</p>
</div>
""",unsafe_allow_html=True)

profiles = DATA.get("perfil_label", pd.Series(["Sin perfil"]*len(DATA))).astype("string").str.strip()
invalid_profiles = {"","otros","otro","nan","none","null"}
valid_profile_mask = profiles.notna() & ~profiles.str.casefold().isin(invalid_profiles)
DATA = DATA[valid_profile_mask].copy()
DATA["perfil_label"] = profiles[valid_profile_mask].astype(str)
profile_options = sorted(DATA["perfil_label"].unique().tolist())
# Decil de acierta por segmento y rango de valor del vehículo, sobre toda la base, antes de los filtros de la hoja.
DATA["percentil_acierta"] = percentil_acierta(DATA)
DATA["valor_rango"] = valor_rango(DATA)
VALOR_LABELS = valor_etiquetas(DATA, DATA["valor_rango"])

def tree_branch(series, order):
    values = series.astype("string").str.strip()
    return values.where(values.isin(order))

# RIE con los parámetros editados en la hoja RIE en esta sesión (o los guardados), sobre toda la base:
# con él se calibra el perfil por defecto de cada segmento y luego se filtra con la hoja.
RIE_ALL = rie_scores(DATA, rie_params())["Normalización"].map(RIE_GROUPS)
levels = apetito_levels()
seed_defaults(levels, SEGMENT_ORDER, pd.DataFrame({
    "Segmento": tree_branch(DATA["perfil_label"], SEGMENT_ORDER), "RIE": RIE_ALL, "Percentil": DATA["percentil_acierta"],
    "mora_max_15m": DATA.get("mora_max_15m"), "meses_vida": DATA.get("meses_vida")}))

c_profile,c_age = st.columns(2,gap="medium")
with c_profile:
    selected_profile = st.selectbox("Segmento",["Todos"]+profile_options,key="matrices_profile_filter")
with c_age:
    # Por defecto 15 meses: créditos con la ventana de mora completa.
    min_age_label = st.radio("Antigüedad mínima",list(MIN_AGE_OPTIONS),index=2,horizontal=True,key="matrices_min_age",
        help="Meses desde el desembolso hasta la fecha de corte. Los créditos cancelados antes se conservan.")
if MIN_AGE_OPTIONS[min_age_label] and "meses_vida" in DATA:
    # La antigüedad solo aplica a las desembolsadas; las solicitudes sin desembolso (sin meses de vida) se conservan.
    vida = DATA["meses_vida"]
    DATA = DATA[vida.ge(MIN_AGE_OPTIONS[min_age_label]).fillna(False) | vida.isna()]
DATA = DATA if selected_profile=="Todos" else DATA[DATA["perfil_label"]==selected_profile]
profile_key = slug(selected_profile)

# ---------------- Datos por crédito ----------------
APETITO = add_apetito(pd.DataFrame({
    "Segmento": tree_branch(DATA["perfil_label"], SEGMENT_ORDER),
    "RIE": RIE_ALL.loc[DATA.index],
    "Licencia": tree_branch(DATA.get("licencia_label", pd.Series(pd.NA, index=DATA.index)), LICENSE_ORDER),
    "Condición": tree_branch(DATA.get("condicion_label", pd.Series(pd.NA, index=DATA.index)), CONDITION_ORDER),
    "clase_vehiculo": DATA.get("clase_vehiculo", pd.Series(pd.NA, index=DATA.index)),
    "productivo": DATA.get("productivo", pd.Series(pd.NA, index=DATA.index)),
    "percentil_acierta": DATA["percentil_acierta"],
    "valor_rango": DATA["valor_rango"],
}), levels)
total_tree = len(APETITO)
no_rie = int(APETITO["RIE"].isna().sum())

# ---------------- Clasificación de apetito ----------------
st.markdown('<div class="fa-section">Clasificación de apetito</div>', unsafe_allow_html=True)
if (n_fuera := DATA_FULL_ATTRS.get("excluidas_financiacion", 0)):
    st.info(f"Se omiten {format_int(n_fuera)} solicitudes con valor a financiar mayor a "
            f"{MAX_FINANCIACION / 1e6:,.0f} millones (fuera del alcance del estudio).".replace(",", "."))
st.info(f"Solicitudes con RIE no calculable: {format_int(no_rie)} ({no_rie / total_tree * 100 if total_tree else 0:.1f}%) "
        f"de {format_int(total_tree)}. No entran en la matriz de perfil ni en la decisión porque les falta información "
        "para el puntaje RIE (ver hoja RIE).")
mora_15m = pd.to_numeric(DATA.get("mora_max_15m", pd.Series(np.nan, index=DATA.index)), errors="coerce")
# Sin la mora de la base, las tablas de mora quedan vacías: se avisa en lugar de mostrar ceros sin explicación.
if "mora_max_15m" not in DATA:
    st.warning("La base no trae la columna mora_max_15m: las tablas de mora quedan vacías. Regenera la base con la "
               "mora a 15 meses (query_comite del notebook generacion_base) unida a los desembolsos.")
elif mora_15m.notna().sum() == 0:
    st.warning("La columna mora_max_15m viene vacía en todos los créditos de la base: las tablas de mora quedan "
               "vacías. Revisa en el notebook la unión de los desembolsos con la mora (query_comite).")
# Fuera del formulario para que el filtro se aplique de inmediato, sin esperar a «Guardar configuración».
# Por defecto mora > 90: la definición de incumplimiento de originación.
mora_label = st.radio("Mora máxima a 15 meses", list(MORA_FILTROS), index=2, horizontal=True, key="arbol_apetito_mora",
                      help="Créditos con mora_max_15m mayor al umbral. Se usa en las tablas de mora de cada matriz.")
# Sin dato de mora no cuenta como mora.
APETITO["con_mora"] = mora_15m.gt(MORA_FILTROS[mora_label]).fillna(False)
# La mora solo existe en las solicitudes desembolsadas: las tablas de mora se miden sobre ellas.
# Sin la marca desembolsado, se toman como desembolsadas las que tienen mora registrada.
APETITO["desembolsado"] = (pd.to_numeric(DATA["desembolsado"], errors="coerce").eq(1) if "desembolsado" in DATA
                           else mora_15m.notna())
# Las llaves de los editores cambian con los filtros para que una edición no pase a otra celda.
filters_key = "_".join([profile_key, slug(min_age_label)])

# Degradados de las tablas: verde para la proporción de créditos y blanco -> amarillo -> rojo para la mora.
SHARE_SCALE = [(0.0, (255, 255, 255)), (1.0, (67, 189, 131))]
MORA_SCALE = [(0.0, (255, 255, 255)), (0.5, (255, 214, 91)), (1.0, (232, 76, 61))]

def gradient_css(value, vmax, scale):
    """Color de fondo de la celda según su valor sobre el máximo de la tabla."""
    if pd.isna(value) or not vmax or value <= 0:
        return ""
    t = min(float(value) / vmax, 1.0)
    for (t0, c0), (t1, c1) in zip(scale, scale[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            r, g, b = (round(a + (b_ - a) * f) for a, b_ in zip(c0, c1))
            return f"background-color: rgb({r},{g},{b}); color: #0A2F4A"
    return ""

def styled_gradient(table, values, scale):
    """Aplica el degradado a las celdas de table con los números de values (mismas filas y columnas);
    las columnas que no están en values (Total) quedan sin color. Cada columna de values se escala aparte
    si su nombre empieza por %, el resto con el máximo común de las celdas."""
    cells = [c for c in values.columns if not str(c).startswith("%")]
    vmax = values[cells].max().max() if cells else 0
    def colors(_):
        out = pd.DataFrame("", index=table.index, columns=table.columns)
        for c in values.columns:
            top = values[c].max() if str(c).startswith("%") else vmax
            out[c] = [gradient_css(v, top, scale) for v in values[c]]
        return out
    return table.style.apply(colors, axis=None)

def cell_text(n, pct):
    return f"{format_int(n)} ({pct:.1f}%)" if n else "–"

def share_table(data, row_col, col_col, rows, cols, row_name, by_row, row_labels=None):
    """Cantidad (proporción) por celda. La proporción es sobre el total de la fila (by_row) o sobre el total
    de la tabla. La columna Total lleva el total de la fila y su proporción."""
    counts = pd.crosstab(data[row_col], data[col_col]).reindex(index=rows, columns=cols, fill_value=0)
    counts["Total"] = counts.sum(axis=1)
    base = counts["Total"].where(counts["Total"] > 0) if by_row else (counts["Total"].sum() or np.nan)
    pct = counts.div(base, axis=0).mul(100) if by_row else counts.div(base).mul(100)
    if by_row:
        # Sobre la fila, el total siempre es 100 %: se muestra la proporción de la fila sobre la tabla.
        pct["Total"] = counts["Total"].div(counts["Total"].sum() or np.nan).mul(100)
    table = pd.DataFrame({c: [cell_text(n, p) for n, p in zip(counts[c], pct[c].fillna(0))] for c in counts.columns},
                         index=pd.Index([(row_labels or {}).get(r, r) for r in rows], name=row_name))
    pct.index = table.index
    return table, counts["Total"], pct[cols]

def mora_separation(data, row_col, col_col, rows, cols, row_name, by_row, base_label, row_labels=None):
    """Concentración (todas las solicitudes) y mora (solo desembolsadas) por celda, lado a lado."""
    data = data.dropna(subset=[row_col, col_col])
    left, right = st.columns(2, gap="medium")
    table, _, pct = share_table(data, row_col, col_col, rows, cols, row_name, by_row, row_labels)
    with left:
        st.caption(f"Concentración: solicitudes (proporción sobre {base_label})")
        st.dataframe(styled_gradient(table, pct, SHARE_SCALE), width="stretch")
    desembolsadas = data[data["desembolsado"]]
    _, totals, _ = share_table(desembolsadas, row_col, col_col, rows, cols, row_name, by_row, row_labels)
    mora_data = desembolsadas[desembolsadas["con_mora"]]
    mora_table, mora_totals, mora_pct = share_table(mora_data, row_col, col_col, rows, cols, row_name, by_row, row_labels)
    rate_col = f"% {mora_label.lower()}"
    rate = pd.Series(mora_totals.to_numpy() / totals.where(totals > 0).to_numpy() * 100, index=mora_table.index)
    mora_table.insert(len(mora_table.columns) - 1, "Desembolsadas", [format_int(t) if t else "–" for t in totals])
    mora_table[rate_col] = [f"{r:.1f}%" if pd.notna(r) else "–" for r in rate]
    mora_pct[rate_col] = rate
    with right:
        st.caption(f"Mora: desembolsadas con {mora_label.lower()} (proporción sobre las desembolsadas con mora de "
                   f"{base_label}); Desembolsadas es el total de la fila y la última columna su % con {mora_label.lower()}")
        st.dataframe(styled_gradient(mora_table, mora_pct, MORA_SCALE), width="stretch")

def level_distribution(data, level_col, title):
    """Solicitudes clasificadas en cada nivel (Bajo, Medio, Alto o sin nivel) y la mora de las desembolsadas."""
    levels_ = data[level_col].fillna(SIN_NIVEL)
    order = [l for l in NIVELES + [SIN_NIVEL] if l in NIVELES or levels_.eq(l).any()]
    n = levels_.value_counts().reindex(order, fill_value=0)
    n_des = levels_[data["desembolsado"]].value_counts().reindex(order, fill_value=0)
    n_mora = levels_[data["desembolsado"] & data["con_mora"]].value_counts().reindex(order, fill_value=0)
    table = pd.DataFrame({"Solicitudes": n, "%": n.div(n.sum() or np.nan).mul(100), "Desembolsadas": n_des,
                          f"Con {mora_label.lower()}": n_mora, f"% {mora_label.lower()}": n_mora.div(n_des.where(n_des > 0)).mul(100)})
    table.index.name = title
    st.caption("Proporción de solicitudes clasificada en cada nivel; la mora es sobre las desembolsadas")
    st.dataframe(table.style.apply_index(lambda idx: [NIVEL_COLORS.get(v, "") for v in idx]),
                 width="stretch", column_config={
                     "Solicitudes": st.column_config.NumberColumn(format="localized"),
                     "Desembolsadas": st.column_config.NumberColumn(format="localized"),
                     "%": st.column_config.NumberColumn(format="%.1f%%"),
                     f"Con {mora_label.lower()}": st.column_config.NumberColumn(format="localized"),
                     f"% {mora_label.lower()}": st.column_config.NumberColumn(format="%.1f%%")})

def apetito_matrix(rows, cols, store, key_of, editor_key, row_name, options=NIVELES, colors=NIVEL_COLORS,
                   row_labels=None):
    """Valor editable de cada celda: nivel (Bajo, Medio, Alto) o decisión en la matriz perfil x vehículo. Va dentro
    del formulario: lo editado se aplica al pulsar «Guardar configuración». Devuelve True si cambió algún valor."""
    shown = {r: (row_labels or {}).get(r, r) for r in rows}
    current = pd.DataFrame([[store.get(key_of(r, c)) for c in cols] for r in rows],
                           index=pd.Index([shown[r] for r in rows], name=row_name), columns=cols, dtype="object")
    st.caption("Decisión (editable)" if options is DECISION_OPTIONS else "Nivel de apetito (editable)")
    styled = current.style.map(lambda v: colors.get(v, ""))
    edited = st.data_editor(styled, width="stretch", num_rows="fixed", key=editor_key,
                            column_config={c: st.column_config.SelectboxColumn(c, options=options) for c in cols})
    changed = False
    for r in rows:
        for c in cols:
            value, key = edited.loc[shown[r], c], key_of(r, c)
            new = value if value in options else None
            if store.get(key) != new:
                changed = True
                if new:
                    store[key] = new
                else:
                    store.pop(key, None)
    return changed

# Formulario: las ediciones no recargan la hoja; se aplican todas juntas con «Guardar configuración».
with st.form("arbol_apetito_form", border=False):
    changed = []

    # 1. Vehículo: una matriz por tipo de crédito, filas rango de valor y columnas licencia/condición.
    st.markdown("**1. Vehículo: valor del vehículo × licencia/condición, por tipo de crédito**")
    VEH = APETITO[APETITO["Tipo"].isin(PRODUCTIVO_ORDER)].dropna(subset=["Vehículo", "Valor"])
    # Las desembolsadas que no tienen tipo de crédito o licencia/condición válidos no entran en la mora del vehículo.
    des = APETITO["desembolsado"]
    n_des, n_des_veh = int(des.sum()), int(VEH["desembolsado"].sum())
    if n_des_veh < n_des:
        st.warning(f"De {format_int(n_des)} solicitudes desembolsadas, {format_int(n_des - n_des_veh)} no entran en la "
                   f"mora del vehículo: {format_int(int((des & ~APETITO['Tipo'].isin(PRODUCTIVO_ORDER)).sum()))} sin tipo de "
                   f"crédito, {format_int(int((des & APETITO['Vehículo'].isna()).sum()))} sin licencia o condición válida "
                   f"y {format_int(int((des & APETITO['Valor'].isna()).sum()))} sin valor del vehículo.")
    if not VEH.empty:
        for tipo, tab in zip(PRODUCTIVO_ORDER, st.tabs(PRODUCTIVO_ORDER)):
            with tab:
                VEH_T = VEH[VEH["Tipo"].eq(tipo)]
                mora_separation(VEH_T, "Valor", "Vehículo", VALOR_RANGOS, VEHICULO_ORDER, "Valor del vehículo", True,
                                "la fila", VALOR_LABELS)
                edit_col, dist_col = st.columns(2, gap="medium")
                with edit_col:
                    changed.append(apetito_matrix(VALOR_RANGOS, VEHICULO_ORDER, levels["vehiculo"],
                                   lambda r, c, t=tipo: f"{t} | {r} | {c}",
                                   f"arbol_apetito_vehiculo_{slug(tipo)}_{filters_key}", "Valor del vehículo",
                                   row_labels=VALOR_LABELS))
                with dist_col:
                    level_distribution(VEH_T, "Nivel vehículo", "Nivel vehículo")
        st.caption("Valor del vehículo: quintiles de ValorVh sobre toda la base (V1 los más baratos, V5 los más caros), "
                   f"en millones de pesos, sin las solicitudes con valor a financiar mayor a {MAX_FINANCIACION / 1e6:,.0f} M "
                   "(fuera del alcance del estudio). Los mismos rangos para productivo y consumo.")
    else:
        st.warning("No hay solicitudes con tipo de crédito, licencia, condición y valor del vehículo para los filtros seleccionados.")

    # 2. Perfil: por segmento, filas RIE y columnas decil.
    st.markdown("**2. Perfil: RIE × decil, por segmento**")
    segments = [s for s in SEGMENT_ORDER if APETITO["Segmento"].eq(s).any()]
    if not segments:
        st.warning("No hay créditos con segmento para los filtros seleccionados.")
    for segment, tab in zip(segments, st.tabs(segments) if segments else []):
        with tab:
            SEG = APETITO[APETITO["Segmento"].eq(segment)].dropna(subset=["RIE", "Percentil"])
            mora_separation(SEG, "RIE", "Percentil", RIE_ORDER, PERCENTILES, "RIE", False, "el segmento")
            edit_col, dist_col = st.columns(2, gap="medium")
            with edit_col:
                changed.append(apetito_matrix(RIE_ORDER, PERCENTILES, levels["perfil"],
                               lambda r, c, s=segment: f"{s} | {r} | {c}",
                               f"arbol_apetito_perfil_{slug(segment)}_{filters_key}", "RIE"))
            with dist_col:
                level_distribution(SEG, "Nivel perfil", "Nivel perfil")
    st.caption("P10 a P100: deciles calculados dentro de cada segmento; P10 es el 10 % con el valor más bajo. "
               "Los créditos sin dato para el decil o sin RIE calculable no aparecen. Niveles por defecto: "
               "config/apetito_default.json, iguales para todos los segmentos.")

    # 3. Decisión perfil x vehículo, un apartado por tipo de crédito (productivo / consumo).
    st.markdown("**3. Decisión perfil × vehículo, por tipo de crédito**")
    for tipo, tab in zip(PRODUCTIVO_ORDER, st.tabs(PRODUCTIVO_ORDER)):
        with tab:
            st.caption("Filas: nivel perfil · columnas: nivel vehículo")
            TIPO = APETITO[APETITO["Tipo"].eq(tipo)]
            mora_separation(TIPO, "Nivel perfil", "Nivel vehículo", NIVELES, NIVELES, "Perfil", False,
                            f"los créditos de {tipo.lower()}")
            edit_col, _ = st.columns(2, gap="medium")
            with edit_col:
                changed.append(apetito_matrix(NIVELES, NIVELES, levels["matriz"], lambda r, c, t=tipo: f"{t} | {r} | {c}",
                               f"arbol_apetito_matriz_{slug(tipo)}_{filters_key}", "Perfil",
                               DECISION_OPTIONS, DECISION_COLORS))
    sin_nivel = int((APETITO["Nivel perfil"].isna() | APETITO["Nivel vehículo"].isna()).sum())
    sin_tipo = int(APETITO["Tipo"].eq(PRODUCTIVO_SIN_DATO).sum())
    st.caption("Cada crédito entra con el nivel de su celda en las matrices de perfil y vehículo. "
               + (f"{format_int(sin_nivel)} créditos no tienen nivel de perfil o de vehículo. " if sin_nivel else "")
               + (f"{format_int(sin_tipo)} créditos no tienen dato de productivo. " if sin_tipo else "")
               + "Las combinaciones en Condiciones pasan a la hoja Mitigantes. Lo editado se aplica al pulsar "
               "«Guardar configuración»; si cambias un filtro o de hoja antes de guardar, se pierde. Para conservarlo "
               "en un archivo usa «Guardar como nueva versión» en la barra lateral.")
    st.form_submit_button("Guardar configuración", type="primary")
# Los colores y las tablas de niveles salen de lo guardado: tras guardar se dibuja la hoja una vez más.
if any(changed):
    st.rerun()

# 4. Distribución de la decisión de la matriz (antes de mitigantes) por tipo de crédito.
st.markdown("**4. Distribución de la decisión por tipo de crédito: solicitudes vs. desembolsadas**")
DIST = APETITO[APETITO["Combinación"].notna()].copy()
DIST["Decisión"] = DIST["Combinación"].map(levels["matriz"]).fillna(SIN_DECISION)
dist_labels = DECISION_OPTIONS + ([SIN_DECISION] if DIST["Decisión"].eq(SIN_DECISION).any() else [])
# Una barra por tipo con todas las solicitudes y otra solo con las desembolsadas, para comparar la decisión
# propuesta con lo que efectivamente se desembolsó.
BASES = {"Solicitudes": pd.Series(True, index=DIST.index), "Desembolsadas": DIST["desembolsado"]}
rows = [(f"{tipo} · {base}", DIST[DIST["Tipo"].eq(tipo) & mask]) for tipo in PRODUCTIVO_ORDER for base, mask in BASES.items()]
dist = pd.DataFrame({name: d["Decisión"].value_counts().reindex(dist_labels, fill_value=0) for name, d in rows if len(d)}).T
if dist.empty:
    st.info("No hay solicitudes con tipo, nivel de perfil y nivel de vehículo para los filtros seleccionados.")
else:
    shares = dist.div(dist.sum(axis=1), axis=0).mul(100)
    fig = go.Figure()
    for label in dist_labels:
        fig.add_bar(y=dist.index, x=shares[label], name=label, orientation="h",
            marker=dict(color=DECISION_BAR_COLORS[label], line=dict(color="white", width=2)),
            customdata=dist[label], text=shares[label].map(lambda v: f"{v:.1f}%" if v >= 4 else ""),
            textposition="inside", insidetextanchor="middle", textfont=dict(color="white", size=12),
            hovertemplate="%{y} · " + label + ": %{customdata:,} (%{x:.1f}%)<extra></extra>")
    fig.update_layout(barmode="stack", height=90 + 55 * len(dist), margin=dict(l=8, r=8, t=10, b=10),
        legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center", traceorder="normal"),
        xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#E5EFEA", title=None),
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT), separators=",.")
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="arbol_distribucion_decision")
        totals = dist.sum(axis=1)
        st.caption("Proporción según la decisión de la celda en la matriz perfil × vehículo, antes de mitigantes. "
                   "Por tipo: todas las solicitudes con tipo, nivel de perfil y nivel de vehículo, y solo las desembolsadas ("
                   + "; ".join(f"{k}: {format_int(v)}" for k, v in totals.items())
                   + "). Los de Condiciones se resuelven en la hoja Mitigantes. Se actualiza al pulsar «Guardar configuración».")

version_sidebar()
