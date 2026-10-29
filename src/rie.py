"""Puntaje RIE por crédito, compartido por la hoja RIE y la hoja Árbol.

Sigue las ponderaciones de Motor_decision.pptx: Respaldo (LTV, 0-3), Ingresos
(PTI/DTI/EI 33,3% cada uno, 0-3) y Experiencia (0 o 1). Total máximo = 7.
"""
import numpy as np
import pandas as pd

from src.common import financed_amount, monthly_payment

# Parámetros editables en la hoja RIE (src/parametros.py los comparte con las demás hojas).
# LTV: rangos [mínimo, máximo] en % por licencia, con calificación 3, 2, 1 y 0.
# PTI y DTI: umbrales en % por licencia y estado civil; EI: umbrales en veces.
# Calificación 2 hasta "medio", 1 hasta "alto" y 0 por encima de "alto".
LICENSES = {"Particular": "PAR", "Público": "PUB"}
MARITAL = {"Casado / unión libre": True, "Otro": False}
LTV_SCORES = [3, 2, 1, 0]
DEFAULT_PARAMS = {
    "plazo_meses": 60,
    "experiencia_pct": 30.0,
    "ltv": {"Particular": [[0.0, 70.0], [70.0, 75.0], [75.0, 85.0], [85.0, 100.0]],
            "Público": [[0.0, 75.0], [75.0, 80.0], [80.0, 90.0], [90.0, 100.0]]},
    "pti": {"Particular": {"Casado / unión libre": {"medio": 25.0, "alto": 50.0}, "Otro": {"medio": 20.0, "alto": 45.0}},
            "Público": {"Casado / unión libre": {"medio": 35.0, "alto": 55.0}, "Otro": {"medio": 30.0, "alto": 50.0}}},
    "dti": {"Particular": {"Casado / unión libre": {"medio": 40.0, "alto": 55.0}, "Otro": {"medio": 35.0, "alto": 50.0}},
            "Público": {"Casado / unión libre": {"medio": 50.0, "alto": 70.0}, "Otro": {"medio": 45.0, "alto": 65.0}}},
    "ei": {"medio": 12.0, "alto": 18.0},
}
# Tabla de normalización literal de página 9: 0-1=>0, 2-3=>1, 4-5=>2, 6-7=>3.
NORMALIZATION_MAP = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 3}
CATEGORY_MAP = {0: "AE", 1: "A", 2: "AA", 3: "AA"}

def num(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    s = series.astype("string").str.strip().str.replace("$", "", regex=False).str.replace(" ", "", regex=False)
    # En esta base las comas de campos monetarios suelen ser separadores de miles.
    s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")

def rie_scores(data, params=None):
    """Devuelve un DataFrame con Puntaje (0-7), Normalización (0-3) y Categoría (AA/A/AE).
    Los créditos sin información suficiente quedan con valores nulos."""
    params = params or DEFAULT_PARAMS
    term_months = params["plazo_meses"]
    def field(name):
        if name not in data:
            return pd.Series(np.nan, index=data.index, dtype=float)
        return num(data[name])

    principal = financed_amount(data)
    payment = monthly_payment(data, term_months)
    income = field("ingresos")
    pti = payment.div(income.where(income > 0)).mul(100)
    dti = (payment + field("ValorCuotaSectorTelcos")).div(income.where(income > 0)).mul(100)
    ei = principal.div(income.where(income > 0))

    all_licenses = data["licencia_vehiculo"].astype("string").str.upper()
    vehicle_all = field("ValorVh")
    ltv_all = principal.div(vehicle_all.where(vehicle_all > 0))  # ratio 0-1, no porcentaje

    # LTV según tabla de página 10 de la presentación.
    ltv_score_all = pd.Series(np.nan, index=data.index, dtype=float)
    for license, code in LICENSES.items():
        lic_mask = all_licenses.eq(code)
        for (lo, hi), score_l in zip(params["ltv"][license], LTV_SCORES):
            # Los intervalos comparten extremos; se conserva el puntaje del intervalo superior.
            mask = lic_mask & ltv_all.ge(lo / 100) & ltv_all.le(hi / 100)
            ltv_score_all.loc[mask] = score_l

    # PTI y DTI: umbrales por licencia y estado civil, páginas 11-12.
    # Los ratios se calculan en escala 0-1 (porcentaje / 100).
    marital = data.get("estado_civil", pd.Series("", index=data.index)).astype("string").str.upper().fillna("")
    married = marital.str.contains("CASAD|UNION|UNIÓN|LIBRE", regex=True)

    # Calificación 0 = tramo de mayor ratio; 1 = intermedio; 2 = menor ratio.
    def income_score_by_threshold(values, thresholds):
        out = pd.Series(np.nan, index=data.index, dtype=float)
        for license, code in LICENSES.items():
            for status, is_married in MARITAL.items():
                mask = all_licenses.eq(code) & married.eq(is_married)
                high, mid = thresholds[license][status]["alto"] / 100, thresholds[license][status]["medio"] / 100
                out.loc[mask & values.gt(high)] = 0
                out.loc[mask & values.le(high) & values.gt(mid)] = 1
                out.loc[mask & values.le(mid)] = 2
        return out

    pti_score = income_score_by_threshold(pti / 100.0, params["pti"])
    dti_score = income_score_by_threshold(dti / 100.0, params["dti"])
    # EI tabla página 12: > alto => 0; medio < EI <= alto => 1; <= medio => 2.
    ei_high, ei_mid = params["ei"]["alto"], params["ei"]["medio"]
    ei_score = pd.Series(np.nan, index=data.index, dtype=float)
    ei_score.loc[ei.gt(ei_high)] = 0
    ei_score.loc[ei.le(ei_high) & ei.gt(ei_mid)] = 1
    ei_score.loc[ei.le(ei_mid) & ei.ge(0)] = 2

    # Ponderación explícita de 33,3% por subítem y reescalado del promedio 0-2 al
    # componente Ingresos 0-3, como define la tabla general RIE (página 9).
    income_scores = pd.concat([pti_score, dti_score, ei_score], axis=1)
    income_component = (income_scores.mean(axis=1, skipna=False) * 1.5)

    # Experiencia: según página 13, deben cumplirse los criterios de monto >30% del
    # valor a financiar, antigüedad >=1 año y calificación <4. Por instrucción del usuario,
    # se asume provisionalmente que la garantía 1 tiene licencia Pública; por tanto, el
    # requisito adicional de garantía pública se considera cumplido para el segmento Público.
    max_amount_all = field("MontoMaxSolicGeneral")
    exp_ratio_all = max_amount_all.div(principal.where(principal > 0)).mul(100)
    date_request_all = pd.to_datetime(data.get("FechaProceso", pd.Series(pd.NaT, index=data.index)), format="mixed", errors="coerce")
    date_open_all = pd.to_datetime(data.get("FechaAperturaMontoMax", pd.Series(pd.NaT, index=data.index)), format="mixed", errors="coerce")
    # Supuesto temporal solicitado: imputar la fecha de hoy cuando la fecha de apertura falta o no es válida.
    today = pd.Timestamp.today().normalize()
    date_open_all = date_open_all.mask(date_open_all.isna() | (date_open_all.dt.year <= 1901), today)
    rating_all = field("CalificacionMontoMax")
    exp_amount_ok = exp_ratio_all.gt(float(params["experiencia_pct"]))
    exp_age_ok = date_request_all.notna() & date_open_all.notna() & date_open_all.dt.year.gt(1901) & ((date_request_all - date_open_all).dt.days >= 365)
    exp_rating_ok = rating_all.lt(4)
    exp_eval = exp_ratio_all.notna() & date_request_all.notna() & date_open_all.notna() & date_open_all.dt.year.gt(1901) & rating_all.notna() & principal.gt(0)
    exp_pass = exp_amount_ok & exp_age_ok & exp_rating_ok
    experience_component = pd.Series(np.where(exp_eval, exp_pass.astype(float), np.nan), index=data.index, dtype=float)

    score_total = ltv_score_all + income_component + experience_component
    score_total = score_total.where(score_total.between(0, 7) & score_total.notna()).round()
    score_total = score_total.astype("Int64")
    normalized = score_total.map(NORMALIZATION_MAP).astype("Int64")
    category = normalized.map(CATEGORY_MAP)
    return pd.DataFrame({"Puntaje": score_total, "Normalización": normalized, "Categoría": category})
