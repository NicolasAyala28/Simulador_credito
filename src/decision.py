"""Decisión final por crédito, compartida por las hojas Mitigantes y Decisión.

1. Rama del árbol (Segmento, RIE, Licencia, Condición) y su decisión en la hoja Árbol.
2. En las ramas con "Condiciones", el crédito pasa a Aprobado si tiene los mitigantes
   exigidos a la rama en la hoja Mitigantes (avalista y/o garantía idóneos) y a A estudio si no.
"""
import numpy as np
import pandas as pd
import streamlit as st

from src.common import financed_amount, monthly_payment
from src.parametros import A_ESTUDIO, APROBADO, CONDICIONES, rie_params
from src.rie import rie_scores

AVALISTAS = [1, 2, 3]
GARANTIAS = [1, 2, 3]
# Reglas de idoneidad de cada garantía: no prendada, máximo 10 años y valor superior
# al % del valor del vehículo de config/garantia.json.
GARANTIA_MAX_ANTIGUEDAD = 10
# El crédito tiene garantía idónea si sus garantías idóneas suman más de este % del valor a financiar.
GARANTIA_MIN_COBERTURA = 0.5

# Ramas del árbol: mismas reglas y llaves que la hoja Árbol.
SEGMENT_ORDER = ["Empleado", "Independiente Formal", "Independiente Informal", "Transportador"]
RIE_GROUPS = {0: "0-1", 1: "0-1", 2: "2", 3: "3"}
RIE_ORDER = ["0-1", "2", "3"]
LICENSE_ORDER = ["Particular", "Público"]
CONDITION_ORDER = ["Nuevo", "Usado"]
TREE_LEVELS = ["Segmento", "RIE", "Licencia", "Condición"]
SIN_DECISION = "Sin decisión"
FINAL_ORDER = [APROBADO, A_ESTUDIO, SIN_DECISION]

def branch_key(values):
    return " | ".join(str(v) for v in values)

def tree_branch(series, order):
    values = series.astype("string").str.strip()
    return values.where(values.isin(order))

def credit_mitigants(data, aval_cfg, gar_cfg):
    """Agrega avalista_idoneo, garantia_idonea y la rama del árbol de cada crédito."""
    data = data.copy()
    data["valor_financiar"] = financed_amount(data)
    # Mismos parámetros que la hoja RIE en esta sesión: el plazo no viene en la base.
    params = rie_params()
    data["cuota_calculada"] = monthly_payment(data, params["plazo_meses"])

    # Avalista idóneo: Acierta y capacidad de pago (ingreso / cuota) con los mínimos de config/avalista.json.
    aval_ok = pd.Series(False, index=data.index)
    for i in AVALISTAS:
        acierta = pd.to_numeric(data[f"Avalista{i}Acierta"], errors="coerce")
        income = pd.to_numeric(data[f"Avalista{i}IngresoTotalMensual"].astype("string"), errors="coerce")
        capacidad = income.div(data["cuota_calculada"].where(data["cuota_calculada"] > 0))
        aval_ok |= (acierta.ge(aval_cfg["acierta"]) & capacidad.ge(aval_cfg["capacidad_pago"])).fillna(False)
    data["avalista_idoneo"] = aval_ok

    # Garantía idónea: no prendada, máximo 10 años y valor superior al % del valor del vehículo.
    current_year = pd.Timestamp.today().year
    vehicle = pd.to_numeric(data["ValorVh"], errors="coerce")
    eligible = pd.Series(0.0, index=data.index)
    for i in GARANTIAS:
        value = pd.to_numeric(data[f"RPV{i}Valor"].astype("string"), errors="coerce").fillna(0)
        model_year = pd.to_numeric(data[f"RPV{i}Modelo"], errors="coerce")
        # Un campo vacío no permite verificar la regla: la garantía no es idónea.
        not_pledged = data[f"RPV{i}Prendado"].astype("string").str.strip().str.upper().eq("NO").fillna(False)
        recent = (current_year - model_year).le(GARANTIA_MAX_ANTIGUEDAD).fillna(False)
        big_enough = value.gt(vehicle.where(vehicle > 0) * gar_cfg["valor"]).fillna(False)
        eligible += value.where(not_pledged & recent & big_enough, 0)
    financiar = data["valor_financiar"].where(data["valor_financiar"] > 0)
    data["garantia_idonea"] = eligible.gt(financiar * GARANTIA_MIN_COBERTURA).fillna(False)

    # Rama del árbol de cada crédito, con los mismos parámetros de RIE que la hoja RIE.
    rie = rie_scores(data, params)
    data["Segmento"] = tree_branch(data["perfil_label"], SEGMENT_ORDER)
    data["RIE"] = rie["Normalización"].map(RIE_GROUPS)
    data["Licencia"] = tree_branch(data.get("licencia_label", pd.Series(pd.NA, index=data.index)), LICENSE_ORDER)
    data["Condición"] = tree_branch(data.get("condicion_label", pd.Series(pd.NA, index=data.index)), CONDITION_ORDER)
    return data

def meets(frame, need):
    """True/False si el crédito tiene los mitigantes exigidos; None si la rama exige 0/0."""
    need_aval, need_gar = int(need.get("avalista", 0)), int(need.get("garantia", 0))
    if not (need_aval or need_gar):
        return pd.Series(pd.NA, index=frame.index, dtype="boolean")
    ok = pd.Series(True, index=frame.index)
    if need_aval:
        ok &= frame["avalista_idoneo"]
    if need_gar:
        ok &= frame["garantia_idonea"]
    return ok.astype("boolean")

def final_decisions(data, decisions, conditions):
    """Créditos con rama completa (RIE calculable), con su decisión en Árbol (decision_arbol),
    si cumplen los mitigantes exigidos (cumple) y la decisión final (decision_final)."""
    branched = data.dropna(subset=TREE_LEVELS).copy()
    branched["rama"] = branched[TREE_LEVELS].astype(str).agg(" | ".join, axis=1)
    branched["decision_arbol"] = branched["rama"].map(decisions)
    branched["cumple"] = pd.Series(pd.NA, index=branched.index, dtype="boolean")
    for key, group in branched[branched["decision_arbol"].eq(CONDICIONES)].groupby("rama"):
        branched.loc[group.index, "cumple"] = meets(group, conditions.get(key, {}))
    decision = branched["decision_arbol"]
    cumple = branched["cumple"]
    branched["decision_final"] = np.select(
        [decision.eq(APROBADO) | (decision.eq(CONDICIONES) & cumple.eq(True).fillna(False)),
         decision.eq(A_ESTUDIO) | (decision.eq(CONDICIONES) & cumple.eq(False).fillna(False))],
        [APROBADO, A_ESTUDIO], SIN_DECISION)
    return branched

