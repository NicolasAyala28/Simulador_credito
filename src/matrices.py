"""Tablas de concentración y mora por celda (cantidad y proporción), compartidas por las hojas Apetito.

Cada celda muestra la cantidad y su proporción sobre el total de la tabla (o de la fila con by_row). La tabla
de mora agrega las desembolsadas de la fila y su tasa de mora.
"""
import numpy as np
import pandas as pd
import streamlit as st

def format_int(n):
    return f"{int(n):,}".replace(",", ".")

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

def share_table(data, row_col, col_col, rows, cols, row_name, by_row, row_labels=None, col_labels=None):
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
    # Las columnas se muestran con su etiqueta (por ejemplo, el intervalo de acierta del decil).
    table = table.rename(columns=col_labels or {})
    return table, counts["Total"], pct[cols].rename(columns=col_labels or {})

def mora_separation(data, row_col, col_col, rows, cols, row_name, by_row, base_label, row_labels=None, col_labels=None,
                    mora_label="Mora > 90", key=None):
    """Concentración (todas las solicitudes) y mora (solo desembolsadas) por celda, lado a lado. data necesita
    las columnas desembolsado y con_mora (mora mayor al umbral de mora_label). key distingue las tablas cuando
    la hoja muestra varias con el mismo contenido (por ejemplo, vacías)."""
    data = data.dropna(subset=[row_col, col_col])
    left, right = st.columns(2, gap="medium")
    table, _, pct = share_table(data, row_col, col_col, rows, cols, row_name, by_row, row_labels, col_labels)
    with left:
        st.caption(f"Concentración: solicitudes (proporción sobre {base_label})")
        st.dataframe(styled_gradient(table, pct, SHARE_SCALE), width="stretch", key=key and f"{key}_concentracion")
    desembolsadas = data[data["desembolsado"]]
    _, totals, _ = share_table(desembolsadas, row_col, col_col, rows, cols, row_name, by_row, row_labels, col_labels)
    mora_data = desembolsadas[desembolsadas["con_mora"]]
    mora_table, mora_totals, mora_pct = share_table(mora_data, row_col, col_col, rows, cols, row_name, by_row, row_labels, col_labels)
    rate_col = f"% {mora_label.lower()}"
    rate = pd.Series(mora_totals.to_numpy() / totals.where(totals > 0).to_numpy() * 100, index=mora_table.index)
    mora_table.insert(len(mora_table.columns) - 1, "Desembolsadas", [format_int(t) if t else "–" for t in totals])
    mora_table[rate_col] = [f"{r:.1f}%" if pd.notna(r) else "–" for r in rate]
    mora_pct[rate_col] = rate
    with right:
        st.caption(f"Mora: desembolsadas con {mora_label.lower()} (proporción sobre las desembolsadas con mora de "
                   f"{base_label}); Desembolsadas es el total de la fila y la última columna su % con {mora_label.lower()}")
        st.dataframe(styled_gradient(mora_table, mora_pct, MORA_SCALE), width="stretch", key=key and f"{key}_mora")
