import streamlit as st
from src.data_loader import base_preparada, study_periods
from src.theme import apply_finanzauto_theme

st.set_page_config(page_title="Simulador de crédito vehicular", page_icon="🚘", layout="wide")
apply_finanzauto_theme()

df = base_preparada()

st.markdown("""
<div class="fa-hero">
  <div class="eyebrow">Finanzauto · Herramienta de análisis</div>
  <h1>Simulador de estudio de solicitudes de crédito vehicular</h1>
  <p>Explora la población de créditos, compara la distribución de variables y configura las matrices de score, exposición y riesgo para analizar su concentración y apoyar la evaluación del motor de decisión.</p>
</div>
""", unsafe_allow_html=True)

periodo_sol, periodo_des = study_periods(df)
a, d, b, c = st.columns(4, gap="medium")
a.metric("Periodo de solicitudes", periodo_sol)
d.metric("Periodo de desembolsos", periodo_des)
b.metric("Registros disponibles", f"{len(df):,}".replace(",", "."))
c.metric("Variables disponibles", f"{len(df.columns):,}".replace(",", "."))

st.markdown('<div class="fa-section">Módulos del simulador</div>', unsafe_allow_html=True)
cols = st.columns(3, gap="medium")
cards = [
    ("01", "Base de datos", "Base de solicitudes, periodos, volumen, calidad de datos y registros omitidos.",
     [("pages/1_Base_de_datos.py", "Abrir módulo →")]),
    ("02", "Población", "Segmentos y ocupaciones, y gráficas de distribución de las variables por segmento.",
     [("pages/2_Poblacion.py", "Segmentos y ocupaciones →"), ("pages/2_Poblacion_graficas.py", "Gráficas →")]),
    ("03", "Cosechas", "ICC por cosecha, rodamientos y por qué el default de originación se define a 90 días.",
     [("pages/3_Cosechas_General.py", "General →"), ("pages/3_Cosechas_Segmento.py", "Segmento →")]),
    ("04", "RIE", "Respaldo, Ingresos y Experiencia: reglas, distribuciones y puntaje 0–7.",
     [("pages/4_RIE.py", "Abrir módulo →")]),
    ("05", "Apetito", "Matrices de vehículo y perfil, y decisión perfil × vehículo por tipo de crédito.",
     [("pages/5_Apetito.py", "Abrir módulo →"), ("pages/5_Apetito_2.py", "Cuota inicial y valor del vehículo →")]),
    ("06", "Mitigantes", "Avalista, garantía, FGA y desistir en las combinaciones en Condiciones.",
     [("pages/6_Mitigantes.py", "Abrir módulo →")]),
    ("07", "Decisión final", "Resultado luego de mitigantes: total, por segmento y solicitudes sin decisión.",
     [("pages/7_Decision_final.py", "Abrir módulo →")]),
    ("08", "Evaluar solicitud", "Digita una solicitud y obtén su decisión con los parámetros activos.",
     [("pages/8_Evaluar_solicitud.py", "Abrir módulo →")]),
]
for i, (num, title, desc, links) in enumerate(cards):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"<div style='color:#15966A;font-weight:800;font-size:12px'>{num}</div><h3 style='margin:.2rem 0;color:#0A2F4A'>{title}</h3><p style='color:#5D7890;min-height:52px'>{desc}</p>", unsafe_allow_html=True)
            for page, label in links:
                st.page_link(page, label=label)

st.info("Las reglas de clasificación y la condición de negocio están pendientes de validación. Los resultados de concentración son exploratorios hasta incorporar los criterios oficiales.")
