import pandas as pd
import streamlit as st

from src.cosechas import (ALTURA_MAXIMA, BANDA_OBJETIVO, COSECHAS_PATH, ETIQUETAS_RANGO, RANGOS_MORA, UMBRALES_MORA,
                          calcular_icc, calcular_roll_rate, curva_acumulada, grafico_curvas, grafico_roll_rate, load_cosechas,
                          rango_cruce, tabla_ventana, transiciones_mora)
from src.distribucion import PAGE_STYLE, SEGMENT_ORDER, format_n
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Cosechas · Segmento", page_icon="📈", layout="wide")
apply_finanzauto_theme()
st.markdown(PAGE_STYLE, unsafe_allow_html=True)

TOTAL = "Total"
# Igual que en la hoja General: la acumulación por monto usa las cosechas con la ventana de 24 meses (casi) completa.
COSECHAS_MONTO = [2022, 2023, 2024]


def pct(x, decimales=1):
    return "—" if x != x else f"{x * 100:.{decimales}f} %".replace(".", ",")


def altura(x):
    return "—" if x != x else f"{int(x)}"


st.title("Cosechas · Segmento")
st.write(
    "Deterioro de las cosechas abierto por segmento (crédito vehicular, persona natural, sin traslados). "
    "La **cosecha** es el año de desembolso y la **altura**, el mes de vida del crédito (altura 0 = mes del desembolso)."
)

if not COSECHAS_PATH.exists():
    st.error(f"No se encontró la base de cosechas en `data/{COSECHAS_PATH.name}`.")
    st.stop()

df, exclusiones = load_cosechas()
ultimo_corte = df["fecha_corte"].max()

with st.container(border=True):
    st.markdown("**Filtros**")
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.8, 1.3])
    etiqueta_mora = c1.radio("Mora medida", list(UMBRALES_MORA), horizontal=True, key="cos_seg_mora")
    cosechas = sorted(df["cosecha"].unique().tolist())
    elegidas = c2.multiselect("Cosechas", cosechas, default=cosechas, key="cos_seg_cosechas")
    segmentos_base = [s for s in SEGMENT_ORDER if s in set(df["segmento"])]
    segmentos = c3.multiselect("Segmentos", segmentos_base, default=segmentos_base, key="cos_seg_segmentos")
    completas = c4.checkbox(
        "ICC: cortar cada cosecha en su última altura completa", value=True, key="cos_seg_completas",
        help="Al final de cada curva solo quedan los créditos desembolsados a comienzo de año, pero el "
             "denominador sigue siendo el desembolso de toda la cosecha, y el ICC cae de forma artificial.",
    )
umbral = UMBRALES_MORA[etiqueta_mora]

if not elegidas or not segmentos:
    st.info("Selecciona al menos una cosecha y un segmento.")
    st.stop()
datos = df[df["cosecha"].isin(elegidas) & df["segmento"].isin(segmentos)]

creditos = datos.drop_duplicates("credito")
m1, m2, m3 = st.columns(3)
m1.metric("Créditos", format_n(len(creditos)))
m2.metric("Desembolso (mil MM COP)", f"{creditos['valor_desembolso'].sum() / 1e9:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."))
m3.metric("Último corte", f"{ultimo_corte:%Y-%m}")
st.caption(
    f"Se excluyen {format_n(exclusiones['total'])} créditos: {format_n(exclusiones['altura_negativa'])} con algún "
    f"corte anterior al desembolso (altura −1) y {format_n(exclusiones['sin_dato'])} sin segmento (sin ocupación "
    "o \"Independiente\" genérico)."
)

# 1. Cosecha: ICC por segmento, un panel por cosecha
st.markdown(f'<h3 class="section-title">Cosecha: ICC {umbral} por cosecha en cada segmento</h3>', unsafe_allow_html=True)
st.caption(f"ICC {umbral} = saldo de capital de los créditos con más de {umbral} días de mora en cada altura "
           "÷ monto desembolsado del segmento en la cosecha. Un panel por segmento y una línea por cosecha.")
icc = calcular_icc(datos, umbral, grupo="segmento", solo_alturas_completas=completas)
with st.container(border=True):
    st.plotly_chart(grafico_curvas(icc, y="icc", serie="cosecha", y_titulo=f"ICC {umbral}", faceta="segmento",
                                   paneles=segmentos, orden_series=elegidas, altura=380),
                    width="stretch", key="cos_seg_icc")

# 2. Default: rodamientos por segmento
st.markdown('<h3 class="section-title">Default: rodamientos por segmento (roll rate)</h3>', unsafe_allow_html=True)
st.caption("Se compara el rango de mora de cada crédito con el del mes anterior (solo meses consecutivos). "
           "Rangos de 30 días: al día, 1–30, 31–60, …, más de 330.")
transiciones = transiciones_mora(datos, claves=["cosecha", "segmento"])
# El roll rate junta todas las cosechas seleccionadas de cada segmento.
roll_rate = calcular_roll_rate(transiciones, claves=["segmento"])

print(transiciones)

print(roll_rate)

st.caption("**Recuperación:** el crédito baja de rango o se mantiene. **Deterioro:** sube de rango. "
           f"La zona sombreada son los rangos con mora mayor a {umbral} días. Cada panel usa la tabla de roll rate "
           "de su segmento con todas las cosechas seleccionadas; los rangos altos tienen pocas transiciones, así que "
           "sus tasas son más inestables.")
# Un panel por segmento con el mismo gráfico de la hoja General, calculado con el roll rate del segmento.
for i in range(0, len(segmentos), 2):
    for col, seg in zip(st.columns(2, gap="medium"), segmentos[i:i + 2]):
        rr_seg = roll_rate[roll_rate["segmento"] == seg]
        with col, st.container(border=True):
            st.markdown(f"**{seg}**")
            if rr_seg.empty:
                st.info("Sin transiciones para este segmento.")
                continue
            # Sin rangos por encima del umbral no hay zona que sombrear.
            umbral_seg = umbral if (rr_seg["rango_anterior"] > umbral).any() else None
            st.plotly_chart(grafico_roll_rate(rr_seg, umbral=umbral_seg, altura=380), width="stretch",
                            key=f"cos_seg_roll_{seg}")
            cruce = rango_cruce(rr_seg)
            st.caption("El deterioro supera a la recuperación desde el rango "
                       f"**{ETIQUETAS_RANGO[cruce]} días**." if cruce is not None else
                       "El deterioro no supera a la recuperación en ningún rango.")


def tabla_monto(tabla):
    return pd.DataFrame({
        "Segmento": tabla["segmento"],
        "Créditos": tabla["creditos"].map(format_n),
        "Desembolso (MM)": (tabla["total"] / 1e6).map(lambda x: format_n(round(x))),
        f"Monto con evento a {ALTURA_MAXIMA} m (MM)": (tabla["eventos"] / 1e6).map(lambda x: format_n(round(x))),
        "% del desembolso": tabla["tasa"].map(pct),
        "Altura 60 %": tabla["altura_60"].map(altura),
        "Altura 80 %": tabla["altura_80"].map(altura),
        "Capturado al mes 15": tabla["captura"].map(lambda x: pct(x, 0)),
    })


# 3. Acumulación del default por monto desembolsado, por segmento
st.markdown(f'<h3 class="section-title">Acumulación del default por monto desembolsado por segmento '
            f'(mora &gt; {umbral} días)</h3>', unsafe_allow_html=True)
cosechas_monto = [c for c in elegidas if c in COSECHAS_MONTO]
st.caption(
    f"Altura en la que cada crédito supera por primera vez {umbral} días de mora, acumulando su monto desembolsado, "
    f"sobre el monto con evento hasta el mes {ALTURA_MAXIMA} (cada curva termina en 100 %). Se usan las cosechas "
    f"{', '.join(map(str, COSECHAS_MONTO))} que estén seleccionadas; 2024 es preliminar. "
    f"La banda verde marca el rango objetivo {pct(BANDA_OBJETIVO[0], 0)}–{pct(BANDA_OBJETIVO[1], 0)}."
)
if not cosechas_monto:
    st.info(f"Selecciona alguna de las cosechas {', '.join(map(str, COSECHAS_MONTO))} para ver esta sección.")
else:
    datos_monto = datos[datos["cosecha"].isin(cosechas_monto)]
    curva_m = pd.concat([
        curva_acumulada(datos_monto, umbral, por_monto=True, claves=["segmento"]),
        curva_acumulada(datos_monto.assign(segmento=TOTAL), umbral, por_monto=True, claves=["segmento"]),
    ], ignore_index=True)
    orden = [s for s in segmentos if s in set(curva_m["segmento"])] + [TOTAL]
    with st.container(border=True):
        st.plotly_chart(grafico_curvas(
            curva_m, y="proporcion", serie="segmento", y_titulo="% acumulado del monto con evento", formato_y=".0%",
            orden_series=orden, banda=BANDA_OBJETIVO, customdata=lambda d: d[["acumulado"]].to_numpy() / 1e6,
            hover=" (%{customdata[0]:,.0f} MM)",
        ), width="stretch", key="cos_seg_monto")
        tabla = tabla_ventana(curva_m, claves=["segmento"]).set_index("segmento").reindex(orden).reset_index()
        st.dataframe(tabla_monto(tabla), width="stretch", hide_index=True)

# 4. Indicadores de la justificación del umbral, por segmento
st.markdown('<h3 class="section-title">Justificación por segmento: deterioro y cura en 31–60 y 61–90 días</h3>',
            unsafe_allow_html=True)
rr_segmento = calcular_roll_rate(transiciones, claves=["segmento"])
filas = []
for seg in segmentos:
    t = transiciones[transiciones["segmento"] == seg]
    r = rr_segmento[rr_segmento["segmento"] == seg]
    det = r.set_index("rango_anterior")["deterioro"]
    cura = t.groupby("rango_anterior")["rango_actual"].apply(lambda x: x.eq(0).mean())
    cruce = rango_cruce(r)
    filas.append({
        "Segmento": seg,
        "Deterioro desde 31–60": pct(det.get(60, float("nan"))),
        "Deterioro desde 61–90": pct(det.get(90, float("nan"))),
        "Cura desde 31–60": pct(cura.get(60, float("nan"))),
        "Cura desde 61–90": pct(cura.get(90, float("nan"))),
        "Cruce deterioro > recuperación": "—" if cruce is None else f"{ETIQUETAS_RANGO[cruce]} días",
    })
with st.container(border=True):
    st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)
    st.caption("Mismos indicadores de la hoja General, abiertos por segmento y calculados con las cosechas "
               "seleccionadas. **Cura:** del rango indicado vuelve a estar al día el mes siguiente. Si el patrón se "
               "repite en todos los segmentos, la misma definición de default (90 días para originación, 60 días "
               "para seguimiento) aplica a toda la población.")
