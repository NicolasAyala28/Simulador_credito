"""Decisión final por crédito, compartida por las hojas Mitigantes y Decisión.

1. Rama del árbol (Segmento, RIE, Licencia, Condición) y su decisión en la hoja Árbol.
2. En las ramas con "Condiciones", el crédito pasa a Aprobado si tiene todos los mitigantes
   exigidos en la hoja Mitigantes y a A estudio si no. Los mitigantes se evalúan con los datos de la
   solicitud: avalista 1 idóneo, garantías (RPV1-RPV3) idóneas y FGA.
La misma regla se aplica a las combinaciones de la matriz perfil x vehículo (src/apetito.py):
la decisión sale de la matriz de productivos o de consumo de la hoja Árbol.
"""
import numpy as np
import pandas as pd

from src.common import financed_amount, monthly_payment
from src.parametros import A_ESTUDIO, APROBADO, CONDICIONES, rie_params
from src.rie import rie_scores

# Mitigantes por crédito (columnas calculadas), exigidos desde la hoja Mitigantes con Avalista, Garantía y FGA.
MITIGANTE_COLS = ["avalista_idoneo", "garantia_idonea", "fga"]
GARANTIAS = [1, 2, 3]
# Reglas de idoneidad de cada garantía: máximo 10 años y valor superior al % del valor del vehículo
# de config/garantia.json.
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
    """Agrega avalista_idoneo, garantia_idonea y fga, evaluados con los datos de la solicitud, y la rama del
    árbol de cada crédito. data.attrs["mitigantes_faltantes"] lista los campos que no vienen en la base."""
    data = data.copy()
    missing = [c for c in ["Avalista1Acierta", "Avalista1IngresoTotalMensual", "RPV1Valor", "RPV1Modelo"]
               if c not in data]
    def field(name):
        return pd.to_numeric(data.get(name, pd.Series(np.nan, index=data.index)).astype("string"), errors="coerce")
    data["valor_financiar"] = financed_amount(data)
    # Cuota con el plazo real de la solicitud (PlazoMeses) y, si falta, el plazo por defecto de la hoja RIE.
    params = rie_params()
    data["cuota_calculada"] = monthly_payment(data, params["plazo_meses"])

    # Avalista idóneo: solo el avalista 1 (basta uno para el mitigante), con Acierta y capacidad de pago
    # (ingreso / cuota) mínimos de config/avalista.json.
    capacidad = field("Avalista1IngresoTotalMensual").div(data["cuota_calculada"].where(data["cuota_calculada"] > 0))
    data["avalista_idoneo"] = (field("Avalista1Acierta").ge(aval_cfg["acierta"])
                               & capacidad.ge(aval_cfg["capacidad_pago"])).fillna(False)

    # Garantía idónea: cada garantía con máximo 10 años y valor superior al % del valor del vehículo de
    # config/garantia.json; el crédito la tiene si sus garantías idóneas suman más del 50 % del valor a
    # financiar. La prenda no se evalúa: se asume que ninguna garantía está prendada (data_loader).
    current_year = pd.Timestamp.today().year
    vehicle = pd.to_numeric(data["ValorVh"], errors="coerce")
    eligible = pd.Series(0.0, index=data.index)
    for i in GARANTIAS:
        value = field(f"RPV{i}Valor").fillna(0)
        not_pledged = data.get(f"RPV{i}Prendado", pd.Series("NO", index=data.index)).astype("string").str.strip().str.upper().eq("NO").fillna(False)
        recent = (current_year - field(f"RPV{i}Modelo")).le(GARANTIA_MAX_ANTIGUEDAD).fillna(False)
        big_enough = value.gt(vehicle.where(vehicle > 0) * gar_cfg["valor"]).fillna(False)
        eligible += value.where(not_pledged & recent & big_enough, 0)
    financiar = data["valor_financiar"].where(data["valor_financiar"] > 0)
    data["garantia_idonea"] = eligible.gt(financiar * GARANTIA_MIN_COBERTURA).fillna(False)
    # FGA: siempre se puede pedir (1 para todas las solicitudes). Solo actúa cuando se exige garantía y la
    # solicitud no tiene garantía idónea (ver meets).
    data["fga"] = True

    # Rama del árbol de cada crédito, con los mismos parámetros de RIE que la hoja RIE.
    rie = rie_scores(data, params)
    data["Segmento"] = tree_branch(data["perfil_label"], SEGMENT_ORDER)
    data["RIE"] = rie["Normalización"].map(RIE_GROUPS)
    data["Licencia"] = tree_branch(data.get("licencia_label", pd.Series(pd.NA, index=data.index)), LICENSE_ORDER)
    data["Condición"] = tree_branch(data.get("condicion_label", pd.Series(pd.NA, index=data.index)), CONDITION_ORDER)
    data.attrs["mitigantes_faltantes"] = missing
    return data

def meets(frame, need):
    """True/False si el crédito tiene los mitigantes exigidos; None si la rama o combinación no exige ninguno.
    Avalista: avalista 1 idóneo. Garantía: garantía idónea o, si la combinación tiene FGA en 1, FGA (se puede
    pedir siempre). El FGA solo reemplaza a la garantía: con Garantía en 0 no tiene efecto.
    Con desistir en 1 no cumple nunca: la fila se envía a estudio."""
    if int(need.get("desistir", 0)):
        return pd.Series(False, index=frame.index, dtype="boolean")
    need_aval, need_gar = int(need.get("avalista", 0)), int(need.get("garantia", 0))
    if not (need_aval or need_gar):
        return pd.Series(pd.NA, index=frame.index, dtype="boolean")
    ok = pd.Series(True, index=frame.index)
    if need_aval:
        ok &= frame["avalista_idoneo"]
    if need_gar:
        ok &= frame["garantia_idonea"] | (frame["fga"] if int(need.get("fga", 0)) else False)
    return ok.astype("boolean")

def meets_by_fga(frame, need):
    """Solicitudes que cumplen solo gracias al FGA: cumplen sin tener garantía idónea."""
    if not (int(need.get("garantia", 0)) and int(need.get("fga", 0))):
        return pd.Series(False, index=frame.index)
    return meets(frame, need).fillna(False).astype(bool) & ~frame["garantia_idonea"]

def final_decisions(data, decisions, conditions):
    """Créditos con rama completa (RIE calculable), con su decisión en Árbol (decision_arbol),
    si cumplen los mitigantes exigidos (cumple), si cumplen solo por el FGA (cumple_por_fga)
    y la decisión final (decision_final)."""
    branched = data.dropna(subset=TREE_LEVELS).copy()
    branched["rama"] = branched[TREE_LEVELS].astype(str).agg(" | ".join, axis=1)
    return decide(branched, decisions, conditions)

def matrix_decisions(data, decisions, conditions):
    """Igual que final_decisions, pero por combinación (tipo, nivel perfil, nivel vehículo) de la
    matriz de la hoja Árbol. Solo entran los créditos con combinación completa (columna Combinación)."""
    combined = data.dropna(subset=["Combinación"]).copy()
    combined["rama"] = combined["Combinación"]
    # Los mitigantes se pueden exigir por combinación o por detalle (licencia/condición y RIE);
    # el detalle tiene precedencia.
    combined["detalle"] = combined.get("Detalle", combined["rama"]).fillna(combined["rama"])
    return decide(combined, decisions, conditions)

def decide(branched, decisions, conditions):
    """Decisión de la rama o combinación (decision_arbol), cumplimiento de mitigantes y decisión final."""
    branched["decision_arbol"] = branched["rama"].map(decisions)
    branched["cumple"] = pd.Series(pd.NA, index=branched.index, dtype="boolean")
    branched["cumple_por_fga"] = False
    key_col = "detalle" if "detalle" in branched else "rama"
    for key, group in branched[branched["decision_arbol"].eq(CONDICIONES)].groupby(key_col):
        need = conditions.get(key) or conditions.get(group["rama"].iloc[0], {})
        branched.loc[group.index, "cumple"] = meets(group, need)
        branched.loc[group.index, "cumple_por_fga"] = meets_by_fga(group, need)
    decision = branched["decision_arbol"]
    cumple = branched["cumple"]
    branched["decision_final"] = np.select(
        [decision.eq(APROBADO) | (decision.eq(CONDICIONES) & cumple.eq(True).fillna(False)),
         decision.eq(A_ESTUDIO) | (decision.eq(CONDICIONES) & cumple.eq(False).fillna(False))],
        [APROBADO, A_ESTUDIO], SIN_DECISION)
    return branched

