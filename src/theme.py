import streamlit as st

def apply_finanzauto_theme():
    """Identidad visual compartida para todas las páginas del simulador."""
    st.markdown("""
    <style>
    :root {
      --fa-green-950:#063D30; --fa-green-900:#064B39; --fa-green-800:#086448;
      --fa-green-700:#087A55; --fa-green-600:#15966A; --fa-green-500:#35AD78;
      --fa-green-300:#91D4A5; --fa-green-100:#EAF5EE; --fa-green-050:#F5FAF7;
      --fa-border:#D7E9DE; --fa-text:#153C32; --fa-muted:#5D7890;
    }
    .stApp {background:#F8FBF9;color:var(--fa-text);}
    [data-testid="stHeader"] {background:rgba(248,251,249,.96);}
    .block-container {padding-top:1.15rem;padding-bottom:1.6rem;max-width:1900px;}
    [data-testid="stSidebar"] {
      background:linear-gradient(180deg,#F0F8F3 0%,#E2F2E9 58%,#CFE8D9 100%);
      border-right:1px solid #D3E7DB;
    }
    [data-testid="stSidebar"] > div:first-child {padding-top:.65rem;}
    [data-testid="stSidebar"] * {color:#103F32;}
    .fa-side-brand {
      display:flex;align-items:center;gap:10px;padding:10px 8px 18px 8px;
      border-bottom:1px solid #C9E1D2;margin-bottom:14px;
    }
    .fa-side-brand .fa-car {
      width:42px;height:42px;display:flex;align-items:center;justify-content:center;
      color:#087A55;font-size:34px;line-height:1;
    }
    .fa-side-brand .fa-brand-title {font-size:17px;font-weight:800;line-height:1.05;color:#092F26;}
    .fa-side-brand .fa-brand-sub {font-size:12px;color:#41695A;margin-top:4px;}
    [data-testid="stSidebar"] [aria-current="page"] {
      background:linear-gradient(90deg,#064B39,#087A55)!important;border-radius:9px;
    }
    [data-testid="stSidebar"] [aria-current="page"] * {color:#fff!important;}
    h1,h2,h3,h4 {color:#0A2F4A!important;letter-spacing:-.02em;}
    h1 {border-left:6px solid #087A55;padding-left:.6rem;line-height:1.12;}
    h2 {font-weight:750;}
    [data-testid="stMetric"] {
      background:#F0F8F3;border:1px solid #D7E9DE;border-radius:11px;padding:11px 14px;
    }
    [data-testid="stMetricLabel"] {color:#42695A;}
    [data-testid="stMetricValue"] {color:#064B39;}
    [data-testid="stVerticalBlockBorderWrapper"] {
      border-color:#D7E9DE!important;border-radius:12px!important;background:rgba(255,255,255,.84);
    }
    div[data-testid="stDataFrame"] {border:1px solid #D7E9DE;border-radius:9px;overflow:hidden;}
    .stButton > button,.stDownloadButton > button {
      border:1px solid #087A55;border-radius:8px;color:#fff;background:#087A55;font-weight:650;
    }
    .stButton > button:hover,.stDownloadButton > button:hover {
      background:#064B39;border-color:#064B39;color:#fff;
    }
    div[data-baseweb="select"] > div,div[data-baseweb="input"] > div,div[data-baseweb="textarea"] > div {
      border-color:#C9E1D2;border-radius:8px;
    }
    [data-testid="stAlert"] {border-radius:10px;}
    hr {border-color:#D7E9DE;}
    .fa-hero {
      position:relative;overflow:hidden;border:1px solid #D4E8DC;border-radius:18px;
      padding:25px 28px;background:linear-gradient(112deg,#F5FBF7 0%,#E6F4EB 56%,#D5EBDD 100%);
      margin-bottom:16px;min-height:170px;
    }
    .fa-hero:after {
      content:"";position:absolute;right:-65px;bottom:-115px;width:420px;height:220px;
      border-radius:50%;border:26px solid rgba(8,122,85,.12);transform:rotate(-12deg);
      box-shadow:0 -26px 0 -4px rgba(8,122,85,.08),0 -53px 0 -9px rgba(8,122,85,.06);
    }
    .fa-hero .eyebrow {font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#087A55;font-weight:800;}
    .fa-hero h1 {font-size:31px;margin:.35rem 0 .5rem;border:0;padding:0;color:#0A2F4A!important;}
    .fa-hero p {font-size:15px;max-width:850px;color:#526F8E;margin:0;line-height:1.55;}
    .fa-section {
      border-left:5px solid #087A55;padding-left:11px;margin:3px 0 12px;
      font-weight:800;color:#0A2F4A;font-size:20px;
    }
    .fa-summary-card {
      border-radius:8px;padding:7px 8px;min-height:64px;text-align:center;
      display:flex;flex-direction:column;justify-content:center;line-height:1.15;
    }
    </style>
    """, unsafe_allow_html=True)
    # Persistent brand banner in the navigation rail.
    st.sidebar.markdown("""
    <div class="fa-side-brand">
      <div class="fa-car">🚘</div>
      <div><div class="fa-brand-title">Simulador</div>
      <div class="fa-brand-title">Crédito Vehicular</div>
      <div class="fa-brand-sub">Análisis y decisión</div></div>
    </div>
    """, unsafe_allow_html=True)
