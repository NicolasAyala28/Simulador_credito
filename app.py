import streamlit as st
from src.data_loader import load_data, prepare_data
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Simulador de crédito vehicular", page_icon="🚘", layout="wide")
apply_finanzauto_theme()

df = prepare_data(load_data())

st.markdown("""
<div class="fa-hero">
  <div class="eyebrow">Finanzauto · Herramienta de análisis</div>
  <h1>Simulador de estudio de solicitudes de crédito vehicular</h1>
  <p>Explora la población de créditos, compara la distribución de variables y configura las matrices de score, exposición y riesgo para analizar su concentración y apoyar la evaluación del motor de decisión.</p>
</div>
""", unsafe_allow_html=True)

period = "No identificado"
if "fecha_desembolso" in df and df["fecha_desembolso"].notna().any():
    period = f"{df['fecha_desembolso'].min():%b %Y} – {df['fecha_desembolso'].max():%b %Y}"

a, b, c = st.columns(3, gap="medium")
a.metric("Periodo de estudio", period)
b.metric("Registros disponibles", f"{len(df):,}".replace(",", "."))
c.metric("Variables disponibles", f"{len(df.columns):,}".replace(",", "."))

st.markdown('<div class="fa-section">Módulos del simulador</div>', unsafe_allow_html=True)
cols = st.columns(3, gap="medium")
cards = [
    ("01", "Portada", "Periodo, población, primeras observaciones y calidad de datos."),
    ("02", "Distribución de variables", "Segmentos y ocupaciones, y gráficas de distribución por segmento."),
    ("03", "RIE", "Reglas de Respaldo, Ingresos y Experiencia con distribuciones y faltantes."),
    ("04", "Árbol", "Segmento, RIE, licencia y condición con concentración de mora."),
    ("05", "Mitigantes", "Avalistas y garantías que cumplen los criterios configurados."),
    ("06", "Decisión", "Decisión final luego de mitigantes: total y por segmento."),
    ("07", "Cosechas", "ICC por cosecha y acumulación del default por créditos y por monto."),
]
for i, (num, title, desc) in enumerate(cards):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"<div style='color:#15966A;font-weight:800;font-size:12px'>{num}</div><h3 style='margin:.2rem 0;color:#0A2F4A'>{title}</h3><p style='color:#5D7890;min-height:52px'>{desc}</p>", unsafe_allow_html=True)
            if title == "RIE":
                st.page_link("pages/3_RIE.py", label="Abrir módulo →")
            elif title == "Portada":
                st.page_link("pages/1_Portada.py", label="Abrir módulo →")
            elif title == "Distribución de variables":
                st.page_link("pages/2_Distribucion.py", label="Segmentos y ocupaciones →")
                st.page_link("pages/2_Distribucion_graficas.py", label="Gráficas →")
            elif title == "Árbol":
                st.page_link("pages/4_Arbol.py", label="Abrir módulo →")
            elif title == "Mitigantes":
                st.page_link("pages/5_Mitigantes.py", label="Abrir módulo →")
            elif title == "Cosechas":
                st.page_link("pages/7_Cosechas_General.py", label="General →")
                st.page_link("pages/7_Cosechas_Segmento.py", label="Segmento →")
            else:
                st.page_link("pages/6_Decision.py", label="Abrir módulo →")

st.info("Las reglas de clasificación y la condición de negocio están pendientes de validación. Los resultados de concentración son exploratorios hasta incorporar los criterios oficiales.")
