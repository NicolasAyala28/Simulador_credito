"""Clasificación de apetito por crédito, compartida por las hojas Apetito, Mitigantes y Decisión final.

1. Perfil: Segmento x RIE x decil de acierta (calculado por segmento), con nivel Bajo/Medio/Alto asignado en la
   hoja Apetito. El nivel por defecto sale de config/apetito_default.json; opcionalmente se calibra en cada segmento
   con la mora > 90 a 15 meses (perfil_sugerido).
2. Vehículo: una matriz por tipo de crédito (productivo/consumo) con filas rango de valor a financiar (quintiles
   V1-V5 sobre toda la base) y columnas licencia/condición, con nivel Bajo/Medio/Alto.
3. Matriz nivel perfil x nivel vehículo, una para productivos y otra para consumo, con la
   decisión Aprobado, Condiciones o A estudio. Las combinaciones en Condiciones pasan a Mitigantes.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Deciles de acierta dentro de cada segmento: P10 es el 10 % más bajo, ..., P100 el 10 % más alto.
PERCENTILES = [f"P{d}" for d in range(10, 101, 10)]
# Columnas de versiones anteriores del perfil (quintiles y rangos de percentil) -> deciles que cubren.
PERFIL_ANTERIOR = {
    "Q1": ["P10", "P20"], "Q2": ["P30", "P40"], "Q3": ["P50", "P60"], "Q4": ["P70", "P80"], "Q5": ["P90", "P100"],
    "P0–P10": ["P10"], "P10–P25": ["P20"], "P25–P50": ["P30", "P40", "P50"], "P50–P75": ["P60", "P70"],
    "P75–P100": ["P80", "P90", "P100"],
}
# Rangos de valor a financiar (ValorVh - MontoCtaInicial): quintiles sobre toda la base (V1 = los montos más bajos).
VALOR_RANGOS = [f"V{v}" for v in range(1, 6)]
VEHICULO_ORDER = ["Público/Nuevo", "Público/Usado", "Particular/Nuevo", "Particular/Usado"]
PRODUCTIVO_ORDER = ["Productivo", "Consumo"]
# La columna productivo puede llegar como 1/0, S/N o texto; lo no reconocido queda como "Sin dato".
PRODUCTIVO_SI = {"1", "1.0", "S", "SI", "SÍ", "TRUE", "Y", "YES", "PRODUCTIVO"}
PRODUCTIVO_NO = {"0", "0.0", "N", "NO", "FALSE", "CONSUMO", "CONSUMO_ORDINARIO", "CONSUMO ORDINARIO", "NO PRODUCTIVO"}
PRODUCTIVO_SIN_DATO = "Sin dato"
# Calibración del perfil por defecto: evento = mora máxima a 15 meses > 90 días, en créditos con al menos
# 15 meses de vida; las celdas se suavizan hacia su fila RIE con un peso equivalente a 50 créditos.
CALIBRACION_MORA = 90
CALIBRACION_MESES = 15
CALIBRACION_PESO = 50
# Valores por defecto de las matrices de la hoja Apetito (perfil, vehículo y decisión por tipo de crédito).
DEFAULTS_PATH = Path(__file__).resolve().parents[1] / "config" / "apetito_default.json"
# Llave de cada combinación de la matriz: tipo de crédito, nivel perfil y nivel vehículo.
COMBINACION_LEVELS = ["Tipo", "Nivel perfil", "Nivel vehículo"]
# Detalle dentro de cada combinación (hoja Mitigantes): licencia/condición y RIE.
DETALLE_LEVELS = ["Vehículo", "RIE"]

def combinacion_key(values):
    return " | ".join(str(v) for v in values)

def percentil_acierta(data):
    """Decil (P10 a P100) de acierta dentro de cada segmento (perfil_label); P10 es el 10 % más bajo. Los empates
    quedan en el mismo decil; sin acierta no hay decil. Solo reparte el perfil, no se muestra como variable."""
    acierta = pd.to_numeric(data.get("acierta", pd.Series(np.nan, index=data.index)), errors="coerce")
    decil = np.ceil(acierta.groupby(data["perfil_label"]).rank(pct=True, method="max") * 10)
    return decil.map(lambda d: f"P{int(d) * 10}" if pd.notna(d) else pd.NA).astype("string")

def valor_financiar(data):
    """Valor a financiar = ValorVh - MontoCtaInicial (solo con valor del vehículo positivo)."""
    vehiculo = pd.to_numeric(data.get("ValorVh", pd.Series(np.nan, index=data.index)), errors="coerce")
    cuota = pd.to_numeric(data.get("MontoCtaInicial", pd.Series(np.nan, index=data.index)), errors="coerce")
    return (vehiculo - cuota).where(vehiculo > 0)

def valor_rango(data):
    """Rango de valor a financiar (V1 a V5): quintil del valor a financiar > 0 sobre las filas de data. Los empates
    quedan en el mismo rango; sin valor no hay rango."""
    valor = valor_financiar(data)
    q = np.ceil(valor.where(valor > 0).rank(pct=True, method="max") * 5)
    return q.map(lambda v: f"V{int(v)}" if pd.notna(v) else pd.NA).astype("string")

def valor_etiquetas(data, rangos):
    """Etiqueta de cada rango con su intervalo de valor a financiar en millones, por ejemplo 'V2 · 45–68 M'."""
    valor = valor_financiar(data) / 1e6
    out = {}
    for r in VALOR_RANGOS:
        v = valor[rangos.eq(r).fillna(False)]
        out[r] = f"{r} · {v.min():,.0f}–{v.max():,.0f} M".replace(",", ".") if len(v) else r
    return out

def perfil_sugerido(frame, segmentos):
    """Nivel por defecto de cada celda Segmento x RIE x rango de percentil, calibrado en cada segmento con la mora > 90
    a 15 meses de los créditos con al menos 15 meses de vida.
    - Tasa de la celda suavizada hacia la de su fila RIE (peso CALIBRACION_PESO créditos), para que las celdas
      con poco volumen no queden en un extremo por pocos eventos.
    - Bajo si la tasa es <= 0,8 x la tasa del segmento; Alto si es > 1,3 x; Medio en otro caso.
    frame: Segmento, RIE, Percentil, mora_max_15m y meses_vida (si falta meses_vida, entran todos)."""
    d = frame.dropna(subset=["Segmento", "RIE", "Percentil"]).copy()
    if "meses_vida" in d:
        d = d[pd.to_numeric(d["meses_vida"], errors="coerce").ge(CALIBRACION_MESES).fillna(False)]
    mora = pd.to_numeric(d.get("mora_max_15m", pd.Series(np.nan, index=d.index)), errors="coerce")
    d["evento"] = mora.gt(CALIBRACION_MORA).astype(float).where(mora.notna())
    d = d.dropna(subset=["evento"])
    out = {}
    for s in segmentos:
        seg = d[d["Segmento"].eq(s)]
        if seg.empty or not seg["evento"].sum():
            continue
        tasa_seg = seg["evento"].mean()
        fila = seg.groupby("RIE")["evento"].mean()
        celdas = seg.groupby(["RIE", "Percentil"])["evento"].agg(["sum", "count"])
        for (rie, q), (eventos, n) in celdas.iterrows():
            tasa = (eventos + CALIBRACION_PESO * fila[rie]) / (n + CALIBRACION_PESO)
            out[f"{s} | {rie} | {q}"] = "Bajo" if tasa <= 0.8 * tasa_seg else "Alto" if tasa > 1.3 * tasa_seg else "Medio"
    return out

def seed_defaults(levels, segmentos, frame=None):
    """Llena las matrices de perfil, vehículo y decisión que estén vacías. Perfil: la tabla de
    config/apetito_default.json, igual para todos los segmentos; si el JSON tiene calibrar = true, cada segmento
    se recalibra con la mora de frame (perfil_sugerido). Vehículo y decisión:
    config/apetito_default.json. Un perfil guardado por quintiles o rangos de percentil se pasa a deciles; un
    vehículo guardado sin rango de valor se repite en todos los rangos; otros formatos anteriores se reemplazan."""
    with open(DEFAULTS_PATH, encoding="utf-8") as f:
        defaults = json.load(f)
    # Perfil guardado con columnas anteriores: cada columna pasa su nivel a los deciles que cubre.
    for k in [k for k in levels["perfil"] if k.rsplit(" | ", 1)[-1] in PERFIL_ANTERIOR]:
        base, col = k.rsplit(" | ", 1)
        nivel = levels["perfil"].pop(k)
        for d in PERFIL_ANTERIOR[col]:
            levels["perfil"].setdefault(f"{base} | {d}", nivel)
    if levels["perfil"] and not any(k.rsplit(" | ", 1)[-1] in PERCENTILES for k in levels["perfil"]):
        levels["perfil"].clear()
    if not levels["perfil"]:
        perfil = defaults["perfil"]
        levels["perfil"].update({f"{s} | {r} | {q}": v for s in segmentos
                                 for r, fila in perfil["filas"].items() for q, v in zip(perfil["columnas"], fila)})
        # La calibración por segmento solo se aplica si el JSON la activa (calibrar = true).
        if frame is not None and perfil.get("calibrar", False):
            levels["perfil"].update(perfil_sugerido(frame, segmentos))
    # Vehículo guardado como tipo | licencia/condición (sin valor): se repite en todos los rangos de valor.
    for k in [k for k in levels["vehiculo"] if k.count(" | ") == 1 and k.split(" | ")[0] in PRODUCTIVO_ORDER]:
        tipo, veh = k.split(" | ")
        nivel = levels["vehiculo"].pop(k)
        for r in VALOR_RANGOS:
            levels["vehiculo"].setdefault(f"{tipo} | {r} | {veh}", nivel)
    if levels["vehiculo"] and not any(k.count(" | ") == 2 and k.split(" | ")[1] in VALOR_RANGOS for k in levels["vehiculo"]):
        levels["vehiculo"].clear()
    if not levels["vehiculo"]:
        vehiculo = defaults["vehiculo"]
        # Cada tipo de crédito tiene una fila por licencia/condición; por_valor permite niveles distintos por rango.
        for tipo, fila in vehiculo["filas"].items():
            for r in VALOR_RANGOS:
                fila_r = vehiculo.get("por_valor", {}).get(tipo, {}).get(r, fila)
                levels["vehiculo"].update({f"{tipo} | {r} | {c}": v for c, v in zip(vehiculo["columnas"], fila_r)})
    if not levels["matriz"]:
        matriz = defaults["matriz"]
        levels["matriz"].update({combinacion_key([tipo, nivel_p, nivel_v]): v for tipo in PRODUCTIVO_ORDER
                                 for nivel_p, fila in matriz[tipo].items() for nivel_v, v in zip(matriz["columnas"], fila)})

def add_apetito(data, levels):
    """Agrega Vehículo, Valor, Percentil, Tipo, Nivel perfil, Nivel vehículo y Combinación.
    data debe traer Segmento, RIE, Licencia y Condición (ramas del árbol), y percentil_acierta o perfil_label
    para calcular el decil; valor_rango o ValorVh y MontoCtaInicial para el rango de valor a financiar."""
    data = data.copy()
    empty = pd.Series(pd.NA, index=data.index, dtype="string")
    # El percentil se puede calcular antes (sobre toda la base del segmento) y pasar en percentil_acierta.
    data["Percentil"] = data["percentil_acierta"].astype("string") if "percentil_acierta" in data else percentil_acierta(data)
    data["Vehículo"] = (data["Licencia"].astype("string") + "/" + data["Condición"].astype("string")
                        ).where(lambda v: v.isin(VEHICULO_ORDER))
    # El rango de valor se puede calcular antes (sobre toda la base) y pasar en valor_rango.
    data["Valor"] = data["valor_rango"].astype("string") if "valor_rango" in data else valor_rango(data)
    productivo = data.get("productivo", empty).astype("string").str.strip().str.upper()
    data["Tipo"] = PRODUCTIVO_SIN_DATO
    data.loc[productivo.isin(PRODUCTIVO_SI).fillna(False), "Tipo"] = "Productivo"
    data.loc[productivo.isin(PRODUCTIVO_NO).fillna(False), "Tipo"] = "Consumo"
    data["Nivel perfil"] = (data["Segmento"].astype("string") + " | " + data["RIE"].astype("string") + " | "
                           + data["Percentil"]).map(levels["perfil"])
    # Nivel de vehículo por tipo de crédito, rango de valor y licencia/condición.
    data["Nivel vehículo"] = (data["Tipo"].astype("string") + " | " + data["Valor"] + " | "
                              + data["Vehículo"]).map(levels["vehiculo"])
    complete = data[COMBINACION_LEVELS].notna().all(axis=1) & data["Tipo"].isin(PRODUCTIVO_ORDER)
    data["Combinación"] = data[COMBINACION_LEVELS].astype(str).agg(" | ".join, axis=1).where(complete)
    detalle_ok = complete & data[DETALLE_LEVELS].notna().all(axis=1)
    data["Detalle"] = data[COMBINACION_LEVELS + DETALLE_LEVELS].astype(str).agg(" | ".join, axis=1).where(detalle_ok)
    return data
