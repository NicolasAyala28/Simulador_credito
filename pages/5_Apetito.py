import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import exclusion_notes
from src.filtros import base_filtrable, filtros_desembolso, nota_desembolsos, selector_base
from src.apetito import (PRODUCTIVO_ORDER, PRODUCTIVO_SIN_DATO, PERCENTILES, VALOR_RANGOS, VEHICULO_ORDER, add_apetito,
    percentil_acierta, vehiculo_key)
from src.escenarios import aplicar_cortes, cortes_escenario, escenario_activo, escenario_filtros, etiquetas, sembrar
from src.parametros import DECISION_OPTIONS, NIVELES, apetito_escenarios, rie_params, version_sidebar
from src.rie import rie_scores
from src.matrices import mora_separation
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Apetito", page_icon="🎯", layout="wide")
apply_finanzauto_theme()

# Base preparada y con las columnas de los filtros, en caché (src/filtros.py).
DATA = base_filtrable()
DATA_FULL_ATTRS = dict(DATA.attrs)

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
  <h1 style="font-size:27px">Apetito: vehículo, perfil y decisión</h1>
  <p>Clasificación de apetito por vehículo y por perfil, decisión por tipo de crédito y su distribución.</p>
</div>
""",unsafe_allow_html=True)

profiles = DATA.get("perfil_label", pd.Series(["Sin perfil"]*len(DATA))).astype("string").str.strip()
invalid_profiles = {"","otros","otro","nan","none","null"}
valid_profile_mask = profiles.notna() & ~profiles.str.casefold().isin(invalid_profiles)
DATA = DATA[valid_profile_mask].copy()
DATA["perfil_label"] = profiles[valid_profile_mask].astype(str)
profile_options = sorted(DATA["perfil_label"].unique().tolist())
DATA_FILTROS = DATA
DESEMBOLSADO = DATA["desembolsado_base"]

def tree_branch(series, order):
    values = series.astype("string").str.strip()
    return values.where(values.isin(order))

# RIE con los parámetros editados en la hoja RIE en esta sesión (o los guardados), sobre toda la base:
# con él se calibra el perfil por defecto de cada segmento y luego se filtra con la hoja.
RIE_ALL = rie_scores(DATA, rie_params())["Normalización"].map(RIE_GROUPS)
sembrar(apetito_escenarios(), SEGMENT_ORDER, pd.DataFrame({
    "Segmento": tree_branch(DATA["perfil_label"], SEGMENT_ORDER), "RIE": RIE_ALL,
    # La calibración del perfil por defecto usa el decil de acierta sobre toda la base, no el de los filtros.
    "Percentil": percentil_acierta(DATA),
    "mora_max_15m": DATA.get("mora_max_15m"), "meses_vida": DATA.get("meses_vida")}))

c_base,c_profile,c_age = st.columns([1,1.4,1.6],gap="medium")
base_analisis = selector_base("matrices_base", c_base)
with c_profile:
    selected_profile = st.selectbox("Segmento",["Todos"]+profile_options,key="matrices_profile_filter")
with c_age:
    # Por defecto 15 meses: créditos con la ventana de mora completa.
    min_age_label = st.radio("Antigüedad mínima",list(MIN_AGE_OPTIONS),index=2,horizontal=True,key="matrices_min_age",
        help="Meses desde el desembolso hasta la fecha de corte. Los créditos cancelados antes se conservan.")
ES_DESEMBOLSOS = base_analisis == "Desembolsos"
DATA, selected_filters = filtros_desembolso(DATA, base_analisis, "matrices")
# Escenario de los filtros (src/escenarios.py): base y filtros de desembolso con valor específico. Sus cortes
# (rangos de valor y deciles) se calculan sobre esta base, antes de la antigüedad y el segmento, que solo filtran.
FILTROS_ESC = escenario_filtros(base_analisis, selected_filters)
ESC_CLAVE, levels, ESC_EXISTE = escenario_activo(apetito_escenarios(), FILTROS_ESC)
CORTES = levels.get("cortes") or cortes_escenario(FILTROS_ESC)

if MIN_AGE_OPTIONS[min_age_label] and "meses_vida" in DATA:
    # La antigüedad solo aplica a las desembolsadas; las solicitudes sin desembolso (sin meses de vida) se conservan.
    vida = DATA["meses_vida"]
    DATA = DATA[vida.ge(MIN_AGE_OPTIONS[min_age_label]).fillna(False) | vida.isna()]
DATA = DATA if selected_profile=="Todos" else DATA[DATA["perfil_label"]==selected_profile]

st.metric("Con los filtros actuales", format_int(len(DATA)), border=True,
          help=f"Registros de la base {base_analisis} que quedan con los filtros seleccionados.")

profile_key = slug(selected_profile)

# Decil de acierta por segmento y quintil del valor a financiar con los cortes del escenario.
DATA = DATA.copy()
DATA["percentil_acierta"], DATA["valor_rango"] = aplicar_cortes(DATA, CORTES)
if ESC_EXISTE:
    st.info(f"Escenario **{ESC_CLAVE}**: niveles guardados en la sesión"
            + (" con rangos y deciles fijados al guardar." if levels.get("cortes") else
               "; rangos y deciles calculados con los datos actuales (se fijan al pulsar «Guardar configuración»)."))
else:
    st.info(f"Escenario **{ESC_CLAVE}** sin configuración propia: se muestran los niveles del escenario de respaldo. "
            "Al pulsar «Guardar configuración» se crea con lo editado y con los rangos y deciles de estos filtros.")

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
# Notas sobre los registros omitidos y otros avisos: se muestran juntas al final de la hoja.
NOTAS = exclusion_notes(DATA_FULL_ATTRS)
if no_rie:
    NOTAS.append(f"Solicitudes con RIE no calculable: {format_int(no_rie)} ({no_rie / total_tree * 100 if total_tree else 0:.1f}%) "
                 f"de {format_int(total_tree)}. No entran en la matriz de perfil ni en la decisión porque les falta "
                 "información para el puntaje RIE (ver hoja RIE).")
if ES_DESEMBOLSOS:
    NOTAS.append(nota_desembolsos(DATA_FILTROS))
mora_15m = pd.to_numeric(DATA.get("mora_max_15m", pd.Series(np.nan, index=DATA.index)), errors="coerce")
# Sin la mora de la base, las tablas de mora quedan vacías: se avisa en lugar de mostrar ceros sin explicación.
if "mora_max_15m" not in DATA:
    NOTAS.append("La base no trae la columna mora_max_15m: las tablas de mora quedan vacías. Regenera la base con la "
                 "mora a 15 meses (query_comite del notebook generacion_base) unida a los desembolsos.")
elif mora_15m.notna().sum() == 0:
    NOTAS.append("La columna mora_max_15m viene vacía en todos los créditos de la base: las tablas de mora quedan "
                 "vacías. Revisa en el notebook la unión de los desembolsos con la mora (query_comite).")
if "desembolsado" not in DATA:
    NOTAS.append("La base no trae la columna desembolsado: se toman como desembolsadas las solicitudes con mora "
                 "registrada. Regenera la base con el notebook generacion_base (celda de unión), que la crea.")
elif not DESEMBOLSADO.any():
    NOTAS.append("Ninguna solicitud de la base está marcada como desembolsada: revisa en el notebook generacion_base "
                 "el cruce de solicitudes con desembolsos (NumeroSolicitud = numero_solicitud).")
# Fuera del formulario para que el filtro se aplique de inmediato, sin esperar a «Guardar configuración».
# Por defecto mora > 90: la definición de incumplimiento de originación.
mora_label = st.radio("Mora máxima a 15 meses", list(MORA_FILTROS), index=2, horizontal=True, key="arbol_apetito_mora",
                      help="Créditos con mora_max_15m mayor al umbral. Se usa en las tablas de mora de cada matriz.")
# Sin dato de mora no cuenta como mora.
APETITO["con_mora"] = mora_15m.gt(MORA_FILTROS[mora_label]).fillna(False)
# La mora solo existe en las solicitudes desembolsadas: las tablas de mora se miden sobre ellas.
APETITO["desembolsado"] = DESEMBOLSADO.loc[DATA.index]
# Las llaves de los editores cambian con los filtros para que una edición no pase a otra celda.
filters_key = "_".join([slug(base_analisis), profile_key, slug(min_age_label)]
                       + [slug(v) for v in selected_filters.values()])

def level_distribution(data, level_col, title, key=None):
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
    st.dataframe(table.style.apply_index(lambda idx: [NIVEL_COLORS.get(v, "") for v in idx]), key=key and f"{key}_niveles",
                 width="stretch", column_config={
                     "Solicitudes": st.column_config.NumberColumn(format="localized"),
                     "Desembolsadas": st.column_config.NumberColumn(format="localized"),
                     "%": st.column_config.NumberColumn(format="%.1f%%"),
                     f"Con {mora_label.lower()}": st.column_config.NumberColumn(format="localized"),
                     f"% {mora_label.lower()}": st.column_config.NumberColumn(format="%.1f%%")})

def apetito_matrix(rows, cols, store, key_of, editor_key, row_name, options=NIVELES, colors=NIVEL_COLORS,
                   row_labels=None, col_labels=None):
    """Valor editable de cada celda: nivel (Bajo, Medio, Alto) o decisión en la matriz perfil x vehículo. Va dentro
    del formulario: lo editado se aplica al pulsar «Guardar configuración». Devuelve True si cambió algún valor."""
    shown = {r: (row_labels or {}).get(r, r) for r in rows}
    shown_cols = {c: (col_labels or {}).get(c, c) for c in cols}
    current = pd.DataFrame([[store.get(key_of(r, c)) for c in cols] for r in rows],
                           index=pd.Index([shown[r] for r in rows], name=row_name),
                           columns=[shown_cols[c] for c in cols], dtype="object")
    st.caption("Decisión (editable)" if options is DECISION_OPTIONS else "Nivel de apetito (editable)")
    styled = current.style.map(lambda v: colors.get(v, ""))
    edited = st.data_editor(styled, width="stretch", num_rows="fixed", key=editor_key,
                            column_config={c: st.column_config.SelectboxColumn(c, options=options) for c in current.columns})
    changed = False
    for r in rows:
        for c in cols:
            value, key = edited.loc[shown[r], shown_cols[c]], key_of(r, c)
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

    # 1. Vehículo: una matriz por segmento y tipo de crédito, filas rango de valor y columnas licencia/condición.
    st.markdown("**1. Vehículo: valor a financiar × licencia/condición, por segmento y tipo de crédito**")
    VEH = APETITO[APETITO["Tipo"].isin(PRODUCTIVO_ORDER)].dropna(subset=["Segmento", "Vehículo", "Valor"])
    # Las desembolsadas que no tienen tipo de crédito o licencia/condición válidos no entran en la mora del vehículo.
    des = APETITO["desembolsado"]
    n_des, n_des_veh = int(des.sum()), int(VEH["desembolsado"].sum())
    if n_des_veh < n_des:
        NOTAS.append(f"De {format_int(n_des)} solicitudes desembolsadas, {format_int(n_des - n_des_veh)} no entran en la "
                     f"mora del vehículo: {format_int(int((des & ~APETITO['Tipo'].isin(PRODUCTIVO_ORDER)).sum()))} sin tipo de "
                     f"crédito, {format_int(int((des & APETITO['Vehículo'].isna()).sum()))} sin licencia o condición válida, "
                     f"{format_int(int((des & APETITO['Valor'].isna()).sum()))} sin valor a financiar "
                     f"y {format_int(int((des & APETITO['Segmento'].isna()).sum()))} sin segmento.")
    # Particular productivo se asume atípico: se muestra, pero se deja constancia de cuántos hay.
    atipicos = APETITO["Tipo"].eq("Productivo") & APETITO["Licencia"].eq("Particular")
    if atipicos.any():
        NOTAS.append(f"{format_int(int(atipicos.sum()))} solicitudes son productivas con licencia particular "
                     f"({format_int(int((atipicos & des).sum()))} desembolsadas): se consideran un caso atípico.")
    veh_segments = [s for s in SEGMENT_ORDER if VEH["Segmento"].eq(s).any()]
    for segment, seg_tab in zip(veh_segments, st.tabs(veh_segments) if veh_segments else []):
        with seg_tab:
            # Rangos de valor a financiar del segmento (quintiles dentro del segmento, con los cortes del escenario).
            V_LABELS = etiquetas(CORTES.get("valor", {}).get(segment), VALOR_RANGOS, 1e6, " M")
            for tipo, tab in zip(PRODUCTIVO_ORDER, st.tabs(PRODUCTIVO_ORDER)):
                with tab:
                    VEH_T = VEH[VEH["Segmento"].eq(segment) & VEH["Tipo"].eq(tipo)]
                    tabla_key = f"veh_{slug(segment)}_{slug(tipo)}"
                    # Cada celda como proporción del total de la tabla (no de la fila).
                    mora_separation(VEH_T, "Valor", "Vehículo", VALOR_RANGOS, VEHICULO_ORDER, "Valor a financiar", False,
                                    f"los créditos de {tipo.lower()} del segmento", V_LABELS, mora_label=mora_label,
                                    key=tabla_key)
                    if tipo == "Productivo":
                        st.caption("Particular productivo se considera un caso atípico.")
                    edit_col, dist_col = st.columns(2, gap="medium")
                    with edit_col:
                        changed.append(apetito_matrix(VALOR_RANGOS, VEHICULO_ORDER, levels["vehiculo"],
                                       lambda r, c, s=segment, t=tipo: vehiculo_key(s, t, r, c),
                                       f"arbol_apetito_vehiculo_{slug(segment)}_{slug(tipo)}_{filters_key}",
                                       "Valor a financiar", row_labels=V_LABELS))
                    with dist_col:
                        level_distribution(VEH_T, "Nivel vehículo", "Nivel vehículo", key=tabla_key)
    if veh_segments:
        st.caption("Valor a financiar (valor del vehículo − cuota inicial): quintiles dentro de cada segmento sobre la base "
                   "del escenario (V1 los montos más bajos, V5 los más altos), en millones de pesos, sin las solicitudes "
                   "fuera del alcance del estudio (ver las notas al final de la hoja). Los mismos rangos para productivo y "
                   "consumo dentro de cada segmento. Niveles por defecto: config/apetito_default.json.")
    else:
        st.warning("No hay solicitudes con segmento, tipo de crédito, licencia, condición y valor a financiar para los "
                   "filtros seleccionados.")

    # 2. Perfil: por segmento, filas RIE y columnas decil.
    st.markdown("**2. Perfil: RIE × decil, por segmento**")
    segments = [s for s in SEGMENT_ORDER if APETITO["Segmento"].eq(s).any()]
    if not segments:
        st.warning("No hay créditos con segmento para los filtros seleccionados.")
    for segment, tab in zip(segments, st.tabs(segments) if segments else []):
        with tab:
            SEG = APETITO[APETITO["Segmento"].eq(segment)].dropna(subset=["RIE", "Percentil"])
            # Intervalo de acierta de cada decil en el segmento, con los registros filtrados.
            P_LABELS = etiquetas(CORTES.get("acierta", {}).get(segment), PERCENTILES)
            mora_separation(SEG, "RIE", "Percentil", RIE_ORDER, PERCENTILES, "RIE", False, "el segmento",
                            col_labels=P_LABELS, mora_label=mora_label)
            edit_col, dist_col = st.columns(2, gap="medium")
            with edit_col:
                changed.append(apetito_matrix(RIE_ORDER, PERCENTILES, levels["perfil"],
                               lambda r, c, s=segment: f"{s} | {r} | {c}",
                               f"arbol_apetito_perfil_{slug(segment)}_{filters_key}", "RIE", col_labels=P_LABELS))
            with dist_col:
                level_distribution(SEG, "Nivel perfil", "Nivel perfil")
    st.caption("P10 a P100: deciles calculados dentro de cada segmento sobre la base del escenario; P10 es el 10 % con el valor más bajo; junto a cada decil, su intervalo de acierta. "
               "Los créditos sin dato para el decil o sin RIE calculable no aparecen. Niveles por defecto: "
               "config/apetito_default.json, iguales para todos los segmentos.")

    # 3. Decisión perfil x vehículo, un apartado por tipo de crédito (productivo / consumo).
    st.markdown("**3. Decisión perfil × vehículo, por tipo de crédito**")
    for tipo, tab in zip(PRODUCTIVO_ORDER, st.tabs(PRODUCTIVO_ORDER)):
        with tab:
            st.caption("Filas: nivel perfil · columnas: nivel vehículo")
            TIPO = APETITO[APETITO["Tipo"].eq(tipo)]
            mora_separation(TIPO, "Nivel perfil", "Nivel vehículo", NIVELES, NIVELES, "Perfil", False,
                            f"los créditos de {tipo.lower()}", mora_label=mora_label)
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
# El escenario se guarda con sus filtros y con los cortes con que se editó.
if any(changed):
    levels["cortes"] = levels.get("cortes") or CORTES
    apetito_escenarios()[ESC_CLAVE] = levels
    st.rerun()

# 4. Distribución de la decisión de la matriz (antes de mitigantes) por tipo de crédito.
st.markdown("**4. Distribución de la decisión por tipo de crédito: "
            + ("desembolsadas**" if ES_DESEMBOLSOS else "solicitudes vs. desembolsadas**"))
DIST = APETITO[APETITO["Combinación"].notna()].copy()
DIST["Decisión"] = DIST["Combinación"].map(levels["matriz"]).fillna(SIN_DECISION)
dist_labels = DECISION_OPTIONS + ([SIN_DECISION] if DIST["Decisión"].eq(SIN_DECISION).any() else [])
# Una barra por tipo con todas las solicitudes y otra solo con las desembolsadas, para comparar la decisión
# propuesta con lo que efectivamente se desembolsó.
# En la base Desembolsos todas son desembolsadas: la barra de solicitudes repetiría la misma.
BASES = {"Desembolsadas": DIST["desembolsado"]} if ES_DESEMBOLSOS else {
    "Solicitudes": pd.Series(True, index=DIST.index), "Desembolsadas": DIST["desembolsado"]}
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

# ---------------- Notas sobre registros omitidos ----------------
if NOTAS:
    st.markdown('<div class="fa-section">Notas sobre registros omitidos</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("\n".join(f"- {n}" for n in NOTAS))

version_sidebar()
