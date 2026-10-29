import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common import load_config
from src.data_loader import load_data, prepare_data
from src.decision import (A_ESTUDIO, APROBADO, FINAL_ORDER, SEGMENT_ORDER, SIN_DECISION, arbol_decisions,
    credit_mitigants, final_decisions, mitigante_conditions)
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Decisión", page_icon="▦", layout="wide")
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
  <p>Decisión de cada crédito luego de mitigantes: la de su rama en el árbol y, en las ramas con "Condiciones",
  Aprobado si cumple los mitigantes exigidos y A estudio si no.</p>
</div>
""", unsafe_allow_html=True)

DATA = credit_mitigants(prepare_data(load_data()).reset_index(drop=True),
                        load_config("avalista"), load_config("garantia"))
FINAL = final_decisions(DATA, arbol_decisions(), mitigante_conditions())
total = len(FINAL)
if not total:
    st.warning("No hay créditos con RIE calculable para asignar una decisión.")
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
note = (f"Base: {format_n(total)} créditos con RIE calculable y rama completa en el árbol. Las decisiones se toman de la "
        "columna Decisión de la hoja Árbol y de las condiciones (Avalista / Garantía) de la hoja Mitigantes: las de la "
        "sesión si se editaron, o si no las guardadas.")
if counts[SIN_DECISION]:
    note += (f" {format_n(counts[SIN_DECISION])} créditos quedan Sin decisión: su rama no tiene decisión en Árbol "
             "o tiene Condiciones sin mitigante exigido (0/0).")
st.caption(note)
