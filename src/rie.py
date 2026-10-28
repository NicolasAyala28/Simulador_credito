"""Puntaje RIE por crédito, compartido por la hoja RIE y la hoja Árbol.

Sigue las ponderaciones de Motor_decision.pptx: Respaldo (LTV, 0-3), Ingresos
(PTI/DTI/EI 33,3% cada uno, 0-3) y Experiencia (0 o 1). Total máximo = 7.
"""
import numpy as np
import pandas as pd

from src.common import financed_amount, monthly_payment

# Valores por defecto de los parámetros editables en la hoja RIE.
DEFAULT_TERM_MONTHS = 60
DEFAULT_EXPERIENCE_PCT = 30.0
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

def rie_scores(data, term_months=DEFAULT_TERM_MONTHS, experience_pct=DEFAULT_EXPERIENCE_PCT):
    """Devuelve un DataFrame con Puntaje (0-7), Normalización (0-3) y Categoría (AA/A/AE).
    Los créditos sin información suficiente quedan con valores nulos."""
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
    for code, bounds in [("PAR", [(0.0, .70, 3), (.70, .75, 2), (.75, .85, 1), (.85, 1.0, 0)]),
                         ("PUB", [(0.0, .75, 3), (.75, .80, 2), (.80, .90, 1), (.90, 1.0, 0)])]:
        lic_mask = all_licenses.eq(code)
        for lo, hi, score_l in bounds:
            # Los intervalos comparten extremos; se conserva el puntaje del intervalo superior.
            mask = lic_mask & ltv_all.ge(lo) & ltv_all.le(hi)
            ltv_score_all.loc[mask] = score_l

    # PTI y DTI: umbrales por licencia y estado civil, páginas 11-12.
    # Los ratios se calculan en escala 0-1 (porcentaje / 100).
    marital = data.get("estado_civil", pd.Series("", index=data.index)).astype("string").str.upper().fillna("")
    married = marital.str.contains("CASAD|UNION|UNIÓN|LIBRE", regex=True)
    particular = all_licenses.eq("PAR")
    public = all_licenses.eq("PUB")

    # Calificación 0 = tramo de mayor ratio; 1 = intermedio; 2 = menor ratio.
    def income_score_by_threshold(values, thresholds):
        out = pd.Series(np.nan, index=data.index, dtype=float)
        for mask, (high, mid) in thresholds:
            out.loc[mask & values.gt(high)] = 0
            out.loc[mask & values.le(high) & values.gt(mid)] = 1
            out.loc[mask & values.le(mid)] = 2
        return out

    pti_score = income_score_by_threshold(pti / 100.0, [
        (particular & married, (.50, .25)),
        (particular & ~married, (.45, .20)),
        (public & married, (.55, .35)),
        (public & ~married, (.50, .30)),
    ])
    dti_score = income_score_by_threshold(dti / 100.0, [
        (particular & married, (.55, .40)),
        (particular & ~married, (.50, .35)),
        (public & married, (.70, .50)),
        (public & ~married, (.65, .45)),
    ])
    # EI tabla página 12: >18 => 0; 12 < EI <=18 => 1; <=12 => 2.
    ei_score = pd.Series(np.nan, index=data.index, dtype=float)
    ei_score.loc[ei.gt(18)] = 0
    ei_score.loc[ei.le(18) & ei.gt(12)] = 1
    ei_score.loc[ei.le(12) & ei.ge(0)] = 2

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
    exp_amount_ok = exp_ratio_all.gt(float(experience_pct))
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
