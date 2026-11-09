"""Escenarios de apetito: niveles de perfil, vehículo y matriz de decisión guardados por filtro.

Un escenario se define por la base (Solicitudes / Desembolsos) y los filtros de desembolso con un valor específico
(concesionario, canal comercial, marca y categoría; «Todos» no cuenta). Guarda:
- filtros: {"base": ..., "<columna>_label": valor} de los filtros específicos;
- cortes: límites [mínimo, máximo] de cada rango de valor a financiar (V1-V5) y de cada decil de acierta
  (P10-P100), ambos por segmento, calculados sobre la base del escenario al guardar; con ellos todas las hojas ubican
  cada solicitud en el mismo rango;
- perfil, vehiculo y matriz: los niveles y decisiones de la hoja Apetito.

El escenario «general» es la base Solicitudes sin filtros (las versiones anteriores se cargan ahí). Cada crédito
usa el escenario más específico de su base cuyos filtros cumple; si no hay ninguno, el de la base sin filtros y,
si tampoco existe, el general. Segmento y tipo de crédito ya van en las llaves de los niveles.
"""
import copy

import numpy as np
import pandas as pd
import streamlit as st

from src.apetito import (PERCENTILES, VALOR_RANGOS, add_apetito, percentil_acierta, seed_defaults, valor_financiar,
    valor_rango)
from src.filtros import FILTROS_DESEMBOLSO, TODOS, base_filtrable

GENERAL = "general"
MATRICES = ("perfil", "vehiculo", "matriz")

def sembrar(escenarios, segmentos, frame=None):
    """seed_defaults en todos los escenarios: completa matrices vacías y reemplaza formatos anteriores."""
    for esc in escenarios.values():
        seed_defaults(esc, segmentos, frame)

def escenario_filtros(base, elegidos):
    """Filtros que definen el escenario: la base y los filtros de desembolso con un valor específico."""
    return {"base": base, **{c: v for c, v in (elegidos or {}).items() if v != TODOS}}

def escenario_clave(filtros):
    """Nombre legible del escenario, por ejemplo «Desembolsos · Concesionario: CARFIAO»."""
    especificos = [f"{FILTROS_DESEMBOLSO[c][3]}: {filtros[c]}" for c in FILTROS_DESEMBOLSO if c in filtros]
    if filtros.get("base", "Solicitudes") == "Solicitudes" and not especificos:
        return GENERAL
    return " · ".join([filtros["base"]] + especificos)

def nuevo_escenario(filtros, origen=None):
    """Escenario con los filtros dados y una copia de los niveles de origen (sin cortes: se fijan al guardar)."""
    origen = origen or {}
    return {"filtros": dict(filtros), "cortes": {}, **{m: copy.deepcopy(origen.get(m, {})) for m in MATRICES}}

def escenario_activo(escenarios, filtros):
    """(clave, escenario, existe): el escenario de esos filtros o, si no está guardado, uno nuevo copiado del
    escenario de respaldo (la base sin filtros y luego el general)."""
    clave = escenario_clave(filtros)
    if clave in escenarios:
        return clave, escenarios[clave], True
    respaldo = escenarios.get(escenario_clave({"base": filtros["base"]})) or escenarios[GENERAL]
    return clave, nuevo_escenario(filtros, respaldo), False

def escenario_aplicable(escenarios, filtros):
    """(clave, escenario) que se aplica con esos filtros: el suyo si está guardado; si no, el de la base sin
    filtros y luego el general (el mismo respaldo que resolver)."""
    for clave in (escenario_clave(filtros), escenario_clave({"base": filtros["base"]}), GENERAL):
        if clave in escenarios:
            return clave, escenarios[clave]

def base_escenario(full, filtros):
    """Registros de full (con las columnas de preparar_filtros) que forman la base del escenario."""
    data = full[full["filtrable_desembolso"]] if filtros.get("base") == "Desembolsos" else full
    for col, valor in filtros.items():
        if col != "base":
            data = data[data[col].eq(valor)]
    return data

# ---------------- Cortes ----------------
def _limites(values, rangos, orden):
    out = {}
    for r in orden:
        v = values[rangos.eq(r).fillna(False)].dropna()
        if len(v):
            out[r] = [float(v.min()), float(v.max())]
    return out

def calcular_cortes(data):
    """Límites [mínimo, máximo] de V1-V5 (valor a financiar) y de P10-P100 (acierta) por segmento sobre data."""
    valor = valor_financiar(data)
    acierta = pd.to_numeric(data.get("acierta", pd.Series(np.nan, index=data.index)), errors="coerce")
    deciles = percentil_acierta(data)
    rangos, valor = valor_rango(data), valor.where(valor > 0)
    grupos = data.groupby("perfil_label").groups.items()
    return {"valor": {str(s): _limites(valor[idx], rangos[idx], VALOR_RANGOS) for s, idx in grupos},
            "acierta": {str(s): _limites(acierta[idx], deciles[idx], PERCENTILES) for s, idx in grupos}}

@st.cache_data(show_spinner=False, max_entries=64)
def _cortes_cache(filtros_items):
    return calcular_cortes(base_escenario(base_filtrable(), dict(filtros_items)))

def cortes_escenario(filtros):
    """calcular_cortes sobre la base del escenario (base filtrable completa), en caché por filtros."""
    return _cortes_cache(tuple(sorted((filtros or {"base": "Solicitudes"}).items())))

def _asignar(values, limites, orden):
    """Rango de cada valor: el primero cuyo máximo lo cubre; los mayores que todos van al último rango."""
    out = pd.Series(pd.NA, index=values.index, dtype="string")
    labels = [r for r in orden if r in (limites or {})]
    for r in labels:
        out[out.isna() & values.notna() & values.le(limites[r][1])] = r
    if labels:
        out[out.isna() & values.notna()] = labels[-1]
    return out

def aplicar_cortes(data, cortes):
    """(percentil_acierta, valor_rango) de cada registro de data con los cortes del escenario."""
    valor = valor_financiar(data).where(lambda v: v > 0)
    acierta = pd.to_numeric(data.get("acierta", pd.Series(np.nan, index=data.index)), errors="coerce")
    decil = pd.Series(pd.NA, index=data.index, dtype="string")
    rango = pd.Series(pd.NA, index=data.index, dtype="string")
    for s, idx in data.groupby("perfil_label").groups.items():
        decil.loc[idx] = _asignar(acierta.loc[idx], cortes.get("acierta", {}).get(str(s)), PERCENTILES)
        rango.loc[idx] = _asignar(valor.loc[idx], cortes.get("valor", {}).get(str(s)), VALOR_RANGOS)
    return decil, rango

def etiquetas(limites, orden, escala=1, sufijo=""):
    """Etiqueta de cada rango con su intervalo, por ejemplo «V2 · 45–68 M» o «P20 · 610–655»."""
    out = {}
    for r in orden:
        if r not in (limites or {}):
            out[r] = r
            continue
        lo, hi = (x / escala for x in limites[r])
        texto = f"{lo:,.0f}" if round(lo) == round(hi) else f"{lo:,.0f}–{hi:,.0f}"
        out[r] = f"{r} · {texto}{sufijo}".replace(",", ".")
    return out

# ---------------- Escenario de cada crédito ----------------
def resolver(data, base, escenarios):
    """Escenario de cada registro: el más específico de la base cuyos filtros cumple; si no, el de la base sin
    filtros y luego el general."""
    candidatos = sorted(((k, e) for k, e in escenarios.items() if e.get("filtros", {}).get("base") == base),
                        key=lambda ke: -len(ke[1]["filtros"]))
    out = pd.Series(pd.NA, index=data.index, dtype="object")
    for clave, esc in candidatos:
        mask = out.isna()
        for col, valor in esc["filtros"].items():
            if col != "base":
                mask &= data[col].eq(valor) if col in data else False
        out[mask] = clave
    return out.fillna(GENERAL)

def asignar_apetito(data, base, escenarios):
    """add_apetito con el escenario de cada registro: decil y rango con sus cortes (o, si no tiene, calculados
    sobre la base del escenario, cortes_escenario) y sus niveles. Agrega Escenario y decision_matriz."""
    claves = resolver(data, base, escenarios)
    partes = []
    for clave in claves.unique():
        esc = escenarios[clave]
        sub = data[claves.eq(clave)].copy()
        cortes = esc.get("cortes") or cortes_escenario(esc.get("filtros"))
        sub["percentil_acierta"], sub["valor_rango"] = aplicar_cortes(sub, cortes)
        sub = add_apetito(sub, esc)
        sub["Escenario"] = clave
        sub["decision_matriz"] = sub["Combinación"].map(esc["matriz"])
        partes.append(sub)
    return pd.concat(partes).loc[data.index] if partes else data.assign(Escenario=pd.NA, decision_matriz=pd.NA)
