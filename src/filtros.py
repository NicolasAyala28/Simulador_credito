"""Filtro de base (Solicitudes / Desembolsos) y filtros de desembolso, compartidos por las hojas RIE, Apetito
y Evaluar solicitud.

- Solicitudes: toda la base, sin los filtros de desembolso.
- Desembolsos: solo los desembolsos que tienen concesionario, canal comercial, marca y categoría (campos de
  master_desembolsos); los que no tienen alguno se omiten. Sobre ellos se filtran esos cuatro campos.
"""
import numpy as np
import pandas as pd
import streamlit as st

from src.data_loader import base_preparada

BASES = ["Solicitudes", "Desembolsos"]
TODOS = "Todos"
# Columna creada -> (columna de la base, etiqueta sin dato, nombre en las notas, título del filtro).
FILTROS_DESEMBOLSO = {
    "concesionario_label": ("nombre_concecionario", "Sin concesionario", "concesionario", "Concesionario"),
    "canal_label": ("canal_comercial", "Sin canal", "canal comercial", "Canal comercial"),
    "marca_label": ("marca_vehiculo", "Sin marca", "marca", "Marca de vehículo"),
    "categoria_label": ("categoria", "Sin categoría", "categoría", "Categoría"),
}

def _fmt(n):
    return f"{int(n):,}".replace(",", ".")

def desembolsado(data):
    """Marca desembolsado de la base; sin esa columna, se toman como desembolsadas las que tienen mora."""
    if "desembolsado" in data:
        return pd.to_numeric(data["desembolsado"], errors="coerce").eq(1)
    mora = pd.to_numeric(data.get("mora_max_15m", pd.Series(np.nan, index=data.index)), errors="coerce")
    return mora.notna()

def preparar_filtros(data):
    """Copia de data con las columnas *_label de los filtros (vacío o ausente = etiqueta sin dato),
    desembolsado_base y filtrable_desembolso (desembolso con los cuatro campos)."""
    data = data.copy()
    data["desembolsado_base"] = desembolsado(data)
    sin_dato = pd.Series(False, index=data.index)
    for label_col, (col, sin, _, _) in FILTROS_DESEMBOLSO.items():
        s = data[col] if col in data else pd.Series(pd.NA, index=data.index)
        data[label_col] = s.astype("string").str.strip().replace("", pd.NA).fillna(sin)
        sin_dato |= data[label_col].eq(sin)
    data["filtrable_desembolso"] = data["desembolsado_base"] & ~sin_dato
    return data

@st.cache_data(show_spinner=False, max_entries=2)
def base_filtrable():
    """Base preparada con las columnas de preparar_filtros, en caché (índice 0..n-1)."""
    return preparar_filtros(base_preparada().reset_index(drop=True))

def selector_base(key, container=None):
    """Radio Solicitudes / Desembolsos."""
    return (container or st).radio("Base", BASES, horizontal=True, key=key,
        help="Solicitudes: toda la base. Desembolsos: solo desembolsos con concesionario, canal comercial, marca y "
             "categoría, que además se pueden filtrar; se omiten los desembolsos sin alguno de esos datos.")

def filtros_desembolso(data, base, key_prefix):
    """Aplica la base elegida y, en Desembolsos, muestra y aplica los cuatro filtros. data debe venir de
    preparar_filtros. Devuelve (data filtrada, valores elegidos por columna)."""
    elegidos = {c: TODOS for c in FILTROS_DESEMBOLSO}
    if base != "Desembolsos":
        return data, elegidos
    data = data[data["filtrable_desembolso"]]
    for col_widget, (label_col, (_, _, _, titulo)) in zip(st.columns(len(FILTROS_DESEMBOLSO), gap="medium"),
                                                         FILTROS_DESEMBOLSO.items()):
        with col_widget:
            opciones = [TODOS] + sorted(data[label_col].unique().tolist())
            elegidos[label_col] = st.selectbox(titulo, opciones, key=f"{key_prefix}_{label_col}_filter")
    for label_col, valor in elegidos.items():
        if valor != TODOS:
            data = data[data[label_col].eq(valor)]
    return data, elegidos

def nota_desembolsos(data):
    """Nota sobre los desembolsos omitidos en la base Desembolsos (data de preparar_filtros, sin filtrar)."""
    des = data["desembolsado_base"]
    n_des, n_ok = int(des.sum()), int(data["filtrable_desembolso"].sum())
    omitidos = n_des - n_ok
    detalle = ", ".join(f"{_fmt((data[c].eq(sin) & des).sum())} sin {nombre}"
                        for c, (_, sin, nombre, _) in FILTROS_DESEMBOLSO.items())
    return (f"Base Desembolsos: se omiten {_fmt(omitidos)} de {_fmt(n_des)} desembolsos "
            f"({omitidos / n_des * 100 if n_des else 0:.1f}%) porque no tienen concesionario, canal comercial, marca o "
            f"categoría ({detalle}; un desembolso puede faltar en más de uno). Las solicitudes no desembolsadas no "
            "tienen esos datos y no entran en esta base.")
