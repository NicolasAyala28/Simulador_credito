import pandas as pd
import streamlit as st

from src.cosechas import (ALTURA_MAXIMA, BANDA_OBJETIVO, COSECHAS_PATH, ETIQUETAS_RANGO, UMBRALES_MORA,
                          calcular_icc, calcular_roll_rate, curva_acumulada, grafico_curvas, grafico_roll_rate,
                          load_cosechas, rango_cruce, tabla_ventana, transiciones_mora)
from src.distribucion import PAGE_STYLE, format_n
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Cosechas · General", page_icon="📈", layout="wide")
apply_finanzauto_theme()
st.markdown(PAGE_STYLE, unsafe_allow_html=True)


def pct(x, decimales=1):
    return f"{x * 100:.{decimales}f} %".replace(".", ",")


def altura(x):
    return "—" if x != x else f"{int(x)}"


st.title("Cosechas · General")
st.write(
    "Deterioro de las cosechas de desembolsos (crédito vehicular, persona natural, sin traslados). "
    "La **cosecha** es el año de desembolso y la **altura**, el mes de vida del crédito (altura 0 = mes del desembolso)."
)

if not COSECHAS_PATH.exists():
    st.error(f"No se encontró la base de cosechas en `data/{COSECHAS_PATH.name}`.")
    st.stop()

df, exclusiones = load_cosechas()
ultimo_corte = df["fecha_corte"].max()

with st.container(border=True):
    st.markdown("**Filtros**")
    c1, c2, c3 = st.columns([1.2, 1.4, 1.4])
    etiqueta_mora = c1.radio("Mora medida", list(UMBRALES_MORA), horizontal=True, key="cos_gen_mora")
    cosechas = sorted(df["cosecha"].unique().tolist())
    elegidas = c2.multiselect("Cosechas", cosechas, default=cosechas, key="cos_gen_cosechas")
    completas = c3.checkbox(
        "ICC: cortar cada cosecha en su última altura completa", value=True, key="cos_gen_completas",
        help="Al final de cada curva solo quedan los créditos desembolsados a comienzo de año, pero el "
             "denominador sigue siendo el desembolso de toda la cosecha, y el ICC cae de forma artificial.",
    )
umbral = UMBRALES_MORA[etiqueta_mora]

if not elegidas:
    st.info("Selecciona al menos una cosecha.")
    st.stop()
datos = df[df["cosecha"].isin(elegidas)]

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

# 1. Cosecha: ICC por cosecha y altura
st.markdown(f'<h3 class="section-title">Cosecha: ICC {umbral} por cosecha</h3>', unsafe_allow_html=True)
st.caption(f"ICC {umbral} = saldo de capital de los créditos con más de {umbral} días de mora en cada altura "
           "÷ monto desembolsado de la cosecha.")
icc = calcular_icc(datos, umbral, solo_alturas_completas=completas)
with st.container(border=True):
    st.plotly_chart(grafico_curvas(icc, y="icc", serie="cosecha", y_titulo=f"ICC {umbral}"),
                    width="stretch", key="cos_gen_icc")

# 2. Default: rodamientos (matriz de transición y roll rate)
st.markdown('<h3 class="section-title">Default: rodamientos (matriz de transición y roll rate)</h3>',
            unsafe_allow_html=True)
st.caption("Se compara el rango de mora de cada crédito con el del mes anterior (solo meses consecutivos). "
           "Rangos de 30 días: al día, 1–30, 31–60, …, más de 330.")

transiciones = transiciones_mora(datos)
roll_rate = calcular_roll_rate(transiciones)
cruce = rango_cruce(roll_rate)

with st.container(border=True):
    st.markdown("**Roll rate: recuperación vs. deterioro**")
    st.caption("**Recuperación:** el crédito baja de rango o se mantiene. **Deterioro:** sube de rango. "
               f"La zona sombreada son los rangos con mora mayor a {umbral} días.")
    st.plotly_chart(grafico_roll_rate(roll_rate, umbral=umbral), width="stretch", key="cos_gen_roll")

    if cruce is not None:
        st.caption(f"El deterioro supera a la recuperación desde el rango **{ETIQUETAS_RANGO[cruce]} días**: "
                   "a partir de ahí, lo más probable es que el crédito empeore el mes siguiente.")

def tabla_monto(tabla):
    out = tabla.rename(columns={"cosecha": "Cosecha"})
    out["Desembolso (MM)"] = (out["total"] / 1e6).map(lambda x: format_n(round(x)))
    out[f"Monto con evento a {ALTURA_MAXIMA} m (MM)"] = (out["eventos"] / 1e6).map(lambda x: format_n(round(x)))
    out["% del desembolso"] = out["tasa"].map(pct)
    out["Altura 60 %"] = out["altura_60"].map(altura)
    out["Altura 80 %"] = out["altura_80"].map(altura)
    out["Capturado al mes 15"] = out["captura"].map(lambda x: pct(x, 0))
    return out.drop(columns=["creditos", "total", "eventos", "tasa", "altura_60", "altura_80", "captura"])


# 3. Acumulación del default por monto desembolsado
st.markdown(f'<h3 class="section-title">Acumulación del default por monto desembolsado (mora &gt; {umbral} días)</h3>',
            unsafe_allow_html=True)
st.caption(
    f"Altura en la que cada crédito supera por primera vez {umbral} días de mora, acumulando su monto desembolsado. "
    f"La proporción se mide sobre el monto con evento hasta el mes {ALTURA_MAXIMA}, así que cada curva termina en 100 %. "
    f"Las cosechas que aún no cumplen {ALTURA_MAXIMA} meses (2024 en parte, 2025) son preliminares. "
    f"La banda verde marca el rango objetivo {pct(BANDA_OBJETIVO[0], 0)}–{pct(BANDA_OBJETIVO[1], 0)}."
)
datos = datos[datos['cosecha'].isin([2024,2023,2022])]
curva_m = curva_acumulada(datos, umbral, por_monto=True)
with st.container(border=True):
    st.plotly_chart(grafico_curvas(
        curva_m, y="proporcion", serie="cosecha", y_titulo="% acumulado del monto con evento", formato_y=".0%",
        banda=BANDA_OBJETIVO, customdata=lambda d: d[["acumulado"]].to_numpy() / 1e6,
        hover="<br>Monto acumulado (MM): %{customdata[0]:,.0f}",
    ), width="stretch", key="cos_gen_monto")

    st.dataframe(tabla_monto(tabla_ventana(curva_m)), width="stretch", hide_index=True)

# 4. Justificación del umbral de default
st.markdown('<h3 class="section-title">Justificación: default a 90 días para originación y 60 días para seguimiento</h3>',
            unsafe_allow_html=True)


def tasa_rango(rango, columna):
    fila = roll_rate.loc[roll_rate["rango_anterior"].eq(rango), columna]
    return pct(fila.iloc[0]) if not fila.empty else "—"


def tasa_cura(rango):
    # Cura: del rango indicado vuelve a estar al día el mes siguiente.
    desde = transiciones[transiciones["rango_anterior"].eq(rango)]
    return pct(desde["rango_actual"].eq(0).mean()) if len(desde) else "—"


with st.container(border=True):
    t1, t2, t3 = st.columns(3)
    t1.metric("Deterioro desde 31–60", tasa_rango(60, "deterioro"))
    t2.metric("Deterioro desde 61–90", tasa_rango(90, "deterioro"))
    t3.metric("Cura (vuelve al día) desde 31–60 / 61–90", f"{tasa_cura(60)} / {tasa_cura(90)}")
    st.caption("Calculado sobre los rodamientos de la sección 2 y las cosechas seleccionadas.")
    st.markdown(f"""
Los rodamientos muestran que el deterioro supera a la recuperación desde el rango
**{ETIQUETAS_RANGO[cruce] if cruce is not None else "31–60"} días**: es el punto donde un crédito tiene más probabilidad
de seguir rodando que de normalizarse. Aun así, para definir el **default del score de originación** se recomienda
**mora mayor a 90 días**, y reservar los **60 días para el score de seguimiento**.

**Por qué 90 días y no 60 para la definición de default (originación):**

1. **El evento es más estable.** Un crédito que pasa de 60 días todavía tiene una probabilidad real de curarse
   (ver la tasa de cura arriba). Marcarlo como malo mezcla en el objetivo a clientes con un atraso transitorio
   (estacionalidad de ingresos de independientes y transportadores, retrasos operativos de pago) con clientes que
   realmente incumplen. A 90 días la cura es menor y el evento se acerca a la pérdida: el score aprende a separar
   a quien no paga, no a quien paga tarde.
2. **Coherencia regulatoria y contable.** 90 días es la definición de incumplimiento para crédito de consumo en
   el modelo de referencia de la Superintendencia Financiera (SARC) y el estándar de Basilea e IFRS 9. Usar el
   mismo umbral alinea el score con provisiones, pérdida esperada (PD, LGD) y reportes, y permite comparar con el
   mercado.
3. **Menos falsos malos, mejor decisión de negocio.** Con 60 días la tasa de malos se infla con clientes que
   después se normalizan; un score de originación entrenado así rechaza o castiga a clientes rentables. A 90 días
   la tasa de malos es menor, pero con la ventana de {ALTURA_MAXIMA} meses las cosechas acumulan suficientes eventos
   para estimar el modelo.
4. **El rodamiento confirma el punto de no retorno.** Si el deterioro ya supera a la recuperación desde 31–60,
   al llegar a 61–90 la probabilidad de seguir rodando es todavía mayor: el crédito que alcanza 90 días ya pasó
   el punto de quiebre y su evento es consistente.

**Por qué 60 días para el score de seguimiento (comportamiento):**

1. **Alerta temprana.** El objetivo del seguimiento es actuar antes de que el crédito llegue al incumplimiento.
   Como el cruce de los rodamientos está alrededor de los 60 días, es el último punto donde la gestión de cobranza
   todavía puede cambiar el resultado.
2. **Más eventos y ventanas cortas.** El seguimiento usa ventanas de desempeño cortas (meses) y necesita eventos
   frecuentes para recalibrarse; 60 días ofrece más eventos que 90 sin caer en el ruido de los atrasos de 1–30.
3. **Complementa al de originación.** El score de originación decide a quién prestar con un evento de pérdida
   (90 días); el de seguimiento prioriza la gestión de la cartera vigente con un evento temprano (60 días).
""")
