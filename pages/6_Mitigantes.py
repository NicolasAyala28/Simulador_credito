import zlib

import numpy as np
import pandas as pd
import streamlit as st

from src.common import load_config
from src.data_loader import load_data, prepare_data
from src.apetito import (COMBINACION_LEVELS, PRODUCTIVO_ORDER, VEHICULO_ORDER, add_apetito,
    percentil_acierta, seed_defaults)
from src.decision import (A_ESTUDIO, APROBADO, CONDICIONES, GARANTIA_MAX_ANTIGUEDAD, GARANTIA_MIN_COBERTURA,
    RIE_ORDER, SEGMENT_ORDER, credit_mitigants, matrix_decisions)
from src.parametros import NIVELES, apetito_levels, mitigante_conditions, version_sidebar
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Mitigantes", page_icon="◫", layout="wide")
apply_finanzauto_theme()

CUMPLE, NO_CUMPLE = "Decisión - Cumple", "Decisión - No cumple"

def format_n(n):
    return f"{int(n):,}".replace(",", ".")

def format_pct(part, total):
    return f"{part / total * 100:.1f}%" if total else "0.0%"

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Mitigantes: avalista, garantía y FGA</h1>
  <p>Solicitudes con avalista y garantías idóneos según los datos de la solicitud, y cumplimiento de las combinaciones perfil × vehículo con decisión "Condiciones".</p>
</div>
""", unsafe_allow_html=True)

# ---------------- Mitigantes por crédito ----------------
# Idoneidad con los datos de la solicitud (avalista 1 y garantías RPV1-RPV3) y combinación perfil x vehículo.
aval_cfg = load_config("avalista")
gar_cfg = load_config("garantia")
PREPARED = prepare_data(load_data()).reset_index(drop=True)
MITIGATED = credit_mitigants(PREPARED, aval_cfg, gar_cfg)
MITIGATED["percentil_acierta"] = percentil_acierta(MITIGATED)
seed_defaults(apetito_levels(), SEGMENT_ORDER, MITIGATED.assign(Percentil=MITIGATED["percentil_acierta"]))
missing = MITIGATED.attrs.get("mitigantes_faltantes", [])
if missing:
    st.warning(f"La base no trae {', '.join(missing)}: el mitigante que depende de esos campos no se cumple en ninguna "
               "solicitud.")
DATA = add_apetito(MITIGATED, apetito_levels())

# ---------------- Tarjetas ----------------
segment_options = ["Todos"] + [s for s in SEGMENT_ORDER if DATA["Segmento"].eq(s).any()]
# Las tarjetas van antes del filtro pero dependen de él: se lee el valor elegido en la sesión.
selected_segment = st.session_state.get("mit_segmento", "Todos")
if selected_segment not in segment_options:
    selected_segment = "Todos"
VIEW = DATA if selected_segment == "Todos" else DATA[DATA["Segmento"].eq(selected_segment)]
total = len(VIEW)
cards = [
    ("Con avalista idóneo", VIEW["avalista_idoneo"]),
    ("Con garantía idónea", VIEW["garantia_idonea"]),
    ("Con avalista y garantía idóneos", VIEW["avalista_idoneo"] & VIEW["garantia_idonea"]),
    ("Sin garantía idónea (podrían pedir FGA)", ~VIEW["garantia_idonea"]),
]
for col, (label, mask) in zip(st.columns(len(cards), gap="medium"), cards):
    n = int(mask.sum())
    col.metric(label, format_n(n), format_pct(n, total), delta_color="off", border=True)
st.caption(f"Porcentajes sobre {format_n(total)} solicitudes del segmento seleccionado. Avalista idóneo: solo el "
           f"avalista 1, con Acierta ≥ {aval_cfg['acierta']:g} y capacidad de pago (ingreso / cuota) ≥ "
           f"{aval_cfg['capacidad_pago']:g}. Garantía idónea: cada garantía con máximo {GARANTIA_MAX_ANTIGUEDAD} años y "
           f"valor superior al {gar_cfg['valor'] * 100:g}% del valor del vehículo; la solicitud la tiene si sus garantías "
           f"idóneas suman más del {GARANTIA_MIN_COBERTURA * 100:g}% del valor a financiar. Se asume que ninguna garantía "
           "está prendada (el dato de las solicitudes no es confiable). FGA: se puede pedir en todas las solicitudes; "
           "solo reemplaza a la garantía cuando la combinación la exige y la solicitud no tiene garantía idónea.")

# ---------------- Filtro ----------------
st.selectbox("Segmento", segment_options, index=segment_options.index(selected_segment), key="mit_segmento")

# ---------------- Combinaciones con "Condiciones" ----------------
st.markdown('<div class="fa-section">Combinaciones perfil × vehículo con decisión "Condiciones"</div>',
            unsafe_allow_html=True)
matriz = apetito_levels()["matriz"]
conditions = mitigante_conditions()
# Decisión final de cada crédito con combinación completa: la de su celda en la matriz de la hoja Árbol;
# en las celdas con "Condiciones", Aprobado si tiene los mitigantes exigidos y A estudio si no.
DECIDED = matrix_decisions(VIEW, matriz, conditions)

ZERO = {"avalista": 0, "garantia": 0, "fga": 0, "desistir": 0}
# Columnas editables de la tabla -> clave guardada; Desistir solo en la vista Detalle.
EDIT_COLS = {"Avalista": "avalista", "Garantía": "garantia", "FGA": "fga", "Desistir": "desistir"}
MIT_CAPTION = ("{filas} filas. Tipo: productivo o consumo. Avalista, "
    "Garantía y FGA (1/0) definen los mitigantes exigidos a cada fila: con Avalista y Garantía en 1 se exigen "
    "los dos; FGA en 1 permite reemplazar la garantía (con Garantía en 0 no tiene efecto). Lo exigido en el "
    "detalle tiene precedencia sobre lo exigido a la combinación. Decisión - Cumple es el % de créditos de la "
    "fila que tienen los mitigantes exigidos y Decisión - No cumple el resto; las filas con Avalista y Garantía "
    "en 0 no se evalúan. Desistir en 1 (vista Detalle) envía la fila a estudio sin evaluar mitigantes. Los cambios se aplican al pulsar «Guardar configuración de mitigantes» y quedan en un archivo con «Guardar como nueva versión» en la barra lateral.")
# Detalle: licencia/condición y RIE de cada combinación en Condiciones.
DETALLE_COLS = {"Vehículo": "Licencia/condición", "RIE": "RIE"}
order = {"Tipo": PRODUCTIVO_ORDER, "Nivel perfil": NIVELES, "Nivel vehículo": NIVELES,
         "Vehículo": VEHICULO_ORDER, "RIE": RIE_ORDER}
EN_CONDICIONES = DECIDED[DECIDED["decision_arbol"].eq(CONDICIONES)]
vista = st.radio("Exigir mitigantes por", ["Detalle", "Combinación"], horizontal=True, key="mit_vista",
                 help="Detalle: una fila por licencia/condición y RIE dentro de cada "
                      "combinación. Combinación: una fila por tipo, nivel perfil y nivel vehículo, que aplica a todo su "
                      "detalle salvo las filas de detalle editadas.")
group_cols = COMBINACION_LEVELS + (list(DETALLE_COLS) if vista == "Detalle" else [])
key_col = "detalle" if vista == "Detalle" else "rama"
if EN_CONDICIONES.empty:
    st.info('No hay solicitudes en combinaciones con decisión "Condiciones". Asígnalas en la matriz perfil × vehículo '
            'de la hoja Árbol.')
    table = pd.DataFrame()
else:
    table = (EN_CONDICIONES.groupby(group_cols + list(dict.fromkeys([key_col, "rama"])), observed=True).size().rename("Créditos")
             .reset_index())
    if vista == "Detalle":
        # Filtros de la tabla (vacío = todos), para no recorrer todas las filas del detalle.
        # En un formulario: los filtros se aplican al pulsar «Aplicar filtros», sin recargar en cada selección.
        with st.expander("Filtros de la tabla", expanded=False), st.form("mit_filtros_form", border=False):
            selected = {}
            for col, f in zip(["Tipo", "Nivel perfil", "Nivel vehículo", "Vehículo", "RIE"], st.columns(5)):
                with f:
                    selected[col] = st.multiselect(
                        DETALLE_COLS.get(col, col), [v for v in order[col] if table[col].eq(v).any()],
                        placeholder="Todos", key=f"mit_filtro_{col}")
            st.form_submit_button("Aplicar filtros")
        for col, chosen in selected.items():
            if chosen:
                table = table[table[col].isin(chosen)]
    for col in group_cols:
        table[f"_{col}"] = table[col].map({v: i for i, v in enumerate(order[col])})
    table = (table.sort_values([f"_{c}" for c in COMBINACION_LEVELS] + ["Créditos"],
                               ascending=[True] * len(COMBINACION_LEVELS) + [False])
             .drop(columns=[f"_{c}" for c in group_cols]).reset_index(drop=True))
if not table.empty:
    keys, ramas = table[key_col].tolist(), table["rama"].tolist()
    # Lo exigido en el detalle tiene precedencia sobre lo exigido a la combinación.
    effective = [conditions.get(k) or conditions.get(r) or ZERO for k, r in zip(keys, ramas)]
    shown = table[group_cols + ["Créditos"]].rename(columns=DETALLE_COLS)
    shown["Avalista"] = [int(e.get("avalista", 0)) for e in effective]
    shown["Garantía"] = [int(e.get("garantia", 0)) for e in effective]
    shown["FGA"] = [int(e.get("fga", 0)) for e in effective]
    if vista == "Detalle":
        shown["Desistir"] = [int(e.get("desistir", 0)) for e in effective]
    # Cumple: % de créditos de la fila con los mitigantes exigidos; las filas sin avalista ni garantía no se evalúan.
    rate = EN_CONDICIONES.groupby(key_col)["cumple"].agg(lambda c: c.astype(float).mean() * 100 if c.notna().any() else np.nan)
    shown[CUMPLE] = pd.Series(keys).map(rate).astype(float)
    shown[NO_CUMPLE] = 100 - shown[CUMPLE]
    fixed_cols = [DETALLE_COLS.get(c, c) for c in group_cols] + ["Créditos", CUMPLE, NO_CUMPLE]
    filtros = "_".join(",".join(map(str, st.session_state.get(f"mit_filtro_{c}", []))) for c in ["Tipo", "Nivel perfil", "Nivel vehículo", "Vehículo", "RIE"])
    # En un formulario: lo editado se aplica al pulsar «Guardar configuración de mitigantes».
    form = st.form("mit_condiciones_form", border=False)
    edited = form.data_editor(shown, width="stretch", hide_index=True, num_rows="fixed",
        height=min(38 + 35 * len(shown), 720),
        # La llave cambia con la vista y los filtros para que una edición no pase a otra fila.
        key=f"mit_condiciones_editor_{selected_segment}_{vista}_{zlib.crc32(filtros.encode())}",
        disabled=fixed_cols,
        column_config={"Créditos": st.column_config.NumberColumn("Créditos", format="localized"),
                       "Avalista": st.column_config.SelectboxColumn("Avalista", options=[1, 0], required=True),
                       "Garantía": st.column_config.SelectboxColumn("Garantía", options=[1, 0], required=True),
                       "FGA": st.column_config.SelectboxColumn("FGA", options=[1, 0], required=True,
                           help="Con Garantía en 1, la solicitud sin garantía idónea cumple pidiendo FGA."),
                       "Desistir": st.column_config.SelectboxColumn("Desistir", options=[1, 0], required=True,
                           help="En 1, la fila se envía a estudio sin evaluar avalista, garantía ni FGA."),
                       CUMPLE: st.column_config.NumberColumn(CUMPLE, format="%.1f%%"),
                       NO_CUMPLE: st.column_config.NumberColumn(NO_CUMPLE, format="%.1f%%")})
    form.caption(MIT_CAPTION.format(filas=format_n(len(shown))))
    form.form_submit_button("Guardar configuración de mitigantes", type="primary")
    changed = False
    for i, (key, eff) in enumerate(zip(keys, effective)):
        # Las columnas que no se muestran en la vista (Desistir en Combinación) conservan su valor.
        new = {m: int(edited[c].iloc[i]) if c in edited else int(eff.get(m, 0)) for c, m in EDIT_COLS.items()}
        if new != {m: int(eff.get(m, 0)) for m in ZERO}:
            conditions[key] = new
            changed = True
    # Tras guardar se recalculan una vez las columnas de cumplimiento y las tarjetas.
    if changed:
        st.rerun()


# ---------------- Decisión final ----------------
st.markdown('<div class="fa-section">Decisión final</div>', unsafe_allow_html=True)
final = {label: DECIDED["decision_final"].eq(label) for label in [APROBADO, A_ESTUDIO]}
total_decided = len(DECIDED)
for col, (label, mask) in zip(st.columns(2, gap="medium"), final.items()):
    n = int(mask.sum())
    col.metric(label, format_n(n), format_pct(n, total_decided), delta_color="off", border=True)
n_rest = total_decided - int(final[APROBADO].sum() + final[A_ESTUDIO].sum())
n_out = total - total_decided
st.caption(f"Porcentajes sobre {format_n(total_decided)} créditos del segmento con combinación completa (tipo, nivel "
           "perfil y nivel vehículo). Aprobado: celdas con decisión Aprobado más los créditos de celdas con Condiciones "
           "que cumplen los mitigantes exigidos. A estudio: celdas con decisión A estudio más los que no cumplen."
           + (f" {format_n(n_rest)} créditos quedan fuera: celdas sin decisión o con Condiciones sin mitigante exigido." if n_rest else "")
           + (f" De los aprobados, {format_n(n_fga)} ({format_pct(n_fga, int(final[APROBADO].sum()))}) cumplen pidiendo "
              "FGA (sin garantía idónea)." if (n_fga := int(DECIDED["cumple_por_fga"].sum())) else "")
           + (f" {format_n(n_out)} créditos del segmento no tienen combinación completa (sin nivel de perfil o de "
              "vehículo, o sin dato de productivo) y no entran." if n_out else ""))

version_sidebar()
