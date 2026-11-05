import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common import load_config
from src.data_loader import load_data, prepare_data
from src.apetito import add_apetito, percentil_acierta, seed_defaults
from src.decision import (A_ESTUDIO, APROBADO, CONDICIONES, FINAL_ORDER, SEGMENT_ORDER, SIN_DECISION,
    credit_mitigants, matrix_decisions)
from src.parametros import apetito_levels, mitigante_conditions, version_sidebar
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Decisión final", page_icon="▦", layout="wide")
apply_finanzauto_theme()

TEXT = "#0A2F4A"
# Verde corporativo para Aprobado, ámbar para A estudio y gris neutro para los créditos sin decisión.
DECISION_COLORS = {APROBADO: "#087A55", A_ESTUDIO: "#E0A030", SIN_DECISION: "#9AA9B5"}

def format_n(n):
    return f"{int(n):,}".replace(",", ".")

st.markdown("""
<div class="fa-hero" style="padding:17px 24px;min-height:0;margin-bottom:12px">
  <div class="eyebrow">Finanzauto · Motor de decisión</div>
  <h1 style="font-size:27px">Decisión final</h1>
  <p>Decisión de cada crédito luego de mitigantes: Aprobado y A estudio según su celda de la matriz perfil × vehículo
  de la hoja Apetito y, en las celdas con "Condiciones", Aprobado si cumple los mitigantes exigidos en Mitigantes y A estudio si no.</p>
</div>
""", unsafe_allow_html=True)

# Misma base y reglas que Mitigantes: combinación (tipo, nivel perfil, nivel vehículo) de cada crédito,
# decisión de su celda en la matriz de la hoja Apetito y mitigantes exigidos en la hoja Mitigantes.
PREPARED = prepare_data(load_data()).reset_index(drop=True)
MITIGATED = credit_mitigants(PREPARED, load_config("avalista"), load_config("garantia"))
MITIGATED["percentil_acierta"] = percentil_acierta(MITIGATED)
seed_defaults(apetito_levels(), SEGMENT_ORDER, MITIGATED.assign(Percentil=MITIGATED["percentil_acierta"]))
DATA = add_apetito(MITIGATED, apetito_levels())
FINAL = matrix_decisions(DATA, apetito_levels()["matriz"], mitigante_conditions())
total = len(FINAL)
n_out = len(DATA) - total
if not total:
    st.warning("No hay créditos con combinación perfil × vehículo completa para asignar una decisión.")
    version_sidebar()
    st.stop()
counts = FINAL["decision_final"].value_counts().reindex(FINAL_ORDER, fill_value=0)
# "Sin decisión" solo se muestra si hay créditos en esa situación.
labels = [l for l in FINAL_ORDER if l != SIN_DECISION or counts[l]]

left, right = st.columns([1, 1.4], gap="medium")
with left:
    with st.container(border=True):
        st.markdown('<div class="fa-section">Decisión final</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Pie(
            labels=labels, values=[int(counts[l]) for l in labels], hole=.55, sort=False, direction="clockwise",
            marker=dict(colors=[DECISION_COLORS[l] for l in labels], line=dict(color="white", width=2)),
            texttemplate="%{label}<br>%{percent:.1%}", textposition="outside", textfont=dict(color=TEXT, size=12),
            hovertemplate="%{label}: %{value:,} créditos (%{percent:.1%})<extra></extra>"))
        fig.update_layout(height=380, margin=dict(l=20, r=20, t=30, b=20), showlegend=True,
            legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"),
            annotations=[dict(text=f"<b>{format_n(total)}</b><br>créditos", showarrow=False,
                              font=dict(color=TEXT, size=14))],
            paper_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT), separators=",.")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="decision_torta")

with right:
    with st.container(border=True):
        st.markdown('<div class="fa-section">Decisión final por segmento</div>', unsafe_allow_html=True)
        by_segment = (pd.crosstab(FINAL["Segmento"], FINAL["decision_final"])
                      .reindex(index=[s for s in SEGMENT_ORDER if FINAL["Segmento"].eq(s).any()], columns=labels, fill_value=0))
        shares = by_segment.div(by_segment.sum(axis=1), axis=0).mul(100)
        fig = go.Figure()
        for label in labels:
            fig.add_bar(y=by_segment.index, x=shares[label], name=label, orientation="h",
                marker=dict(color=DECISION_COLORS[label], line=dict(color="white", width=2)),
                customdata=by_segment[label], text=shares[label].map(lambda v: f"{v:.0f}%" if v >= 5 else ""),
                textposition="inside", insidetextanchor="middle", textfont=dict(color="white", size=11),
                hovertemplate="%{y} · " + label + ": %{customdata:,} créditos (%{x:.1f}%)<extra></extra>")
        fig.update_layout(barmode="stack", height=380, margin=dict(l=8, r=8, t=30, b=20),
            legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center", traceorder="normal"),
            xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#E5EFEA", title=None),
            yaxis=dict(autorange="reversed", title=None),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT), separators=",.")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="decision_segmento")

# Vista en tabla de los dos gráficos: cantidad y % por segmento.
table = by_segment.copy()
table.loc["Total"] = counts[labels]
table.insert(0, "Créditos", table.sum(axis=1))
for label in labels:
    table[f"% {label}"] = table[label] / table["Créditos"] * 100
st.dataframe(table.reset_index(names="Segmento"), width="stretch", hide_index=True,
    column_config={**{c: st.column_config.NumberColumn(c, format="localized") for c in ["Créditos"] + labels},
                   **{f"% {l}": st.column_config.NumberColumn(f"% {l}", format="%.1f%%") for l in labels}})
note = (f"Base: {format_n(total)} créditos con combinación completa (tipo productivo/consumo, nivel perfil y nivel "
        "vehículo). Aprobado y A estudio salen de la matriz perfil × vehículo de la hoja Apetito; en las celdas con "
        "Condiciones, el crédito queda Aprobado si cumple los mitigantes exigidos en la hoja Mitigantes (Avalista / "
        "Garantía / FGA, con los datos de la solicitud) y A estudio si no. Se usan los valores de la versión activa (barra lateral) con los cambios de la sesión.")
if counts[SIN_DECISION]:
    note += (f" {format_n(counts[SIN_DECISION])} créditos quedan Sin decisión: su celda no tiene decisión en Apetito "
             "o tiene Condiciones sin mitigante exigido (0/0).")
if n_out:
    note += (f" {format_n(n_out)} créditos no entran: sin RIE calculable, sin nivel de perfil o de vehículo, "
             "o sin dato de productivo.")
st.caption(note)

# ---------------- Solicitudes sin decisión ----------------
# Quedan sin decisión las celdas de la matriz sin valor y las celdas en Condiciones sin avalista ni garantía exigidos:
# un 0 en Mitigantes también es un valor asignado, pero no exige nada y la solicitud no se evalúa.
SIN = FINAL[FINAL["decision_final"].eq(SIN_DECISION)].copy()
if not SIN.empty:
    st.markdown('<div class="fa-section">Solicitudes sin decisión</div>', unsafe_allow_html=True)
    conditions = mitigante_conditions()
    need = [conditions.get(d) or conditions.get(r) or {} for d, r in zip(SIN["detalle"], SIN["rama"])]
    SIN["Avalista"] = [int(n.get("avalista", 0)) for n in need]
    SIN["Garantía"] = [int(n.get("garantia", 0)) for n in need]
    SIN["FGA"] = [int(n.get("fga", 0)) for n in need]
    SIN["Motivo"] = [
        "La celda no tiene decisión en la matriz de la hoja Apetito" if pd.isna(d)
        else "Condiciones sin mitigante exigido en Mitigantes" if d == CONDICIONES
        else "Otro" for d in SIN["decision_arbol"]]
    cols = ["Motivo", "Tipo", "Nivel perfil", "Nivel vehículo", "Vehículo", "RIE", "Avalista", "Garantía", "FGA"]
    pendientes = (SIN.groupby(cols, dropna=False).size().rename("Créditos").reset_index()
                  .rename(columns={"Vehículo": "Licencia/condición"})
                  .sort_values(["Motivo", "Créditos"], ascending=[True, False]))
    st.dataframe(pendientes, width="stretch", hide_index=True,
                 column_config={"Créditos": st.column_config.NumberColumn("Créditos", format="localized")})
    st.caption(f"{format_n(len(SIN))} créditos sin decisión, por combinación y detalle (licencia/condición y RIE). "
               "En Mitigantes, un 0 en Avalista, Garantía y FGA es un valor asignado pero no exige ningún mitigante, así "
               "que esas solicitudes no se evalúan. Para que tengan decisión, exige avalista, garantía o FGA en esas filas, márcalas para desistir (van a estudio) o cambia la decisión de "
               "la celda en la matriz de la hoja Apetito.")

version_sidebar()
