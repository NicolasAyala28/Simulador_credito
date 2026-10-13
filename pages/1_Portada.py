import streamlit as st
import pandas as pd
from src.data_loader import load_data, prepare_data

st.set_page_config(page_title="Portada", page_icon="🚘", layout="wide")
from src.theme import apply_finanzauto_theme
apply_finanzauto_theme()

df = prepare_data(load_data())
st.title("1. Portada")
st.write("Resumen de la base de estudio, periodo, volumen de registros y auditoría de calidad de datos.")

# Periodo y volumen
if "fecha_desembolso" in df.columns and df["fecha_desembolso"].notna().any():
    dates = df["fecha_desembolso"].dropna()
    periodo = f"{dates.min():%Y-%m} a {dates.max():%Y-%m}"
else:
    periodo = "No identificado"
c1, c2, c3 = st.columns(3)
c1.metric("Periodo de estudio", periodo)
c2.metric("Cantidad de registros", f"{len(df):,}".replace(",", "."))
c3.metric("Cantidad de variables", f"{len(df.columns):,}".replace(",", "."))

# Auditoría general: nulos reales y marcadores textuales comunes.
missing_markers = {"", "nan", "none", "null", "n/a", "na", "sin dato"}
missing_mask = df.isna().copy()
for column in df.select_dtypes(include=["object", "string"]).columns:
    missing_mask[column] = missing_mask[column] | df[column].astype("string").str.strip().str.casefold().isin(missing_markers)
missing_by_col = missing_mask.sum().astype(int)
missing_pct_by_col = (missing_by_col / len(df) * 100).round(2) if len(df) else missing_by_col.astype(float)
missing_cells = int(missing_by_col.sum())
total_cells = int(df.shape[0] * df.shape[1])
rows_with_missing = int(missing_mask.any(axis=1).sum())
duplicated_rows = int(df.duplicated().sum())

st.divider()
st.subheader("Auditoría general de datos")
st.caption("Los faltantes incluyen nulos reales y marcadores textuales como vacío, 'nan', 'null' o 'sin dato'. Algunos campos de avalistas y garantías pueden ser opcionales; su ausencia no implica necesariamente un error.")
a1, a2, a3, a4 = st.columns(4)
a1.metric("Celdas faltantes", f"{missing_cells:,}".replace(",", "."))
a2.metric("Faltantes sobre todas las celdas", f"{(missing_cells / total_cells * 100) if total_cells else 0:.2f}%")
a3.metric("Registros con al menos un faltante", f"{rows_with_missing:,}".replace(",", "."))
a4.metric("Filas duplicadas exactas", f"{duplicated_rows:,}".replace(",", "."))

# Licencia: comparar campo fuente y etiqueta derivada sin convertir faltantes en texto aparente.
st.subheader("Completitud de licencia vehicular")
license_cols = [c for c in ["licencia_vehiculo", "licencia_label"] if c in df.columns]
if license_cols:
    rows = []
    for col in license_cols:
        s = df[col].astype("string").str.strip()
        missing = s.isna() | s.str.casefold().isin(missing_markers)
        complete = int((~missing).sum())
        rows.append({"Campo": col, "Registros completos": complete, "Faltantes": int(missing.sum()), "Completitud (%)": round(complete / len(df) * 100, 2) if len(df) else 0.0})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    if "licencia_vehiculo" in df.columns:
        counts = df["licencia_vehiculo"].astype("string").str.strip().fillna("Sin dato").replace({"": "Sin dato"}).value_counts(dropna=False)
        license_dist = pd.DataFrame({"Licencia": counts.index.astype(str), "Cantidad": counts.values})
        license_dist["Porcentaje (%)"] = (license_dist["Cantidad"] / len(df) * 100).round(2) if len(df) else 0
        st.dataframe(license_dist, width="stretch", hide_index=True)

st.subheader("Variables con mayor cantidad de faltantes")
missing_table = pd.DataFrame({"Variable": missing_by_col.index, "Faltantes": missing_by_col.values, "Faltantes (%)": missing_pct_by_col.values})
missing_table = missing_table[missing_table["Faltantes"] > 0].sort_values(["Faltantes", "Variable"], ascending=[False, True]).head(15)
st.dataframe(missing_table, width="stretch", hide_index=True)

# Revisión de claves y consistencia básica
st.subheader("Controles de consistencia")
checks = []
for col in ["credito", "numero_solicitud", "NumeroSolicitud"]:
    if col in df.columns:
        valid = df[col].notna()
        checks.append({"Control": f"Unicidad de {col}", "Resultado": f"{int(df.loc[valid, col].duplicated().sum()):,} duplicados entre valores informados".replace(",", "."), "Interpretación": "Revisar si la clave debe ser única; solicitudes pueden repetirse si la base no está a nivel de solicitud."})
if "id_fecha_desembolso" in df.columns:
    raw = df["id_fecha_desembolso"].astype("string").str.replace(r"\.0$", "", regex=True)
    parsed = pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
    invalid = int((raw.notna() & parsed.isna()).sum())
    checks.append({"Control": "Formato de fecha de desembolso", "Resultado": f"{invalid:,} fechas no interpretables".replace(",", "."), "Interpretación": "Se espera el formato AAAAMMDD."})
if checks:
    st.dataframe(pd.DataFrame(checks), width="stretch", hide_index=True)

st.info("Lectura de auditoría: una tasa alta de faltantes puede deberse a campos condicionales (por ejemplo, segundo/tercer avalista o garantía adicional). Antes de imputar o excluir datos, validar cuáles son obligatorios para cada análisis.")

st.divider()
st.subheader("Primeros cinco registros")
preview = df.head(5).copy()
# Evita errores de serialización Arrow por columnas object con tipos mixtos en la vista previa.
for col in preview.select_dtypes(include=["object", "string"]).columns:
    preview[col] = preview[col].map(lambda value: str(value) if pd.notna(value) else None).astype("string")
st.dataframe(preview, width="stretch", hide_index=True)

st.divider()
st.subheader("Listado de variables")
st.caption(f"La base contiene {len(df.columns)} variables. Se presentan en formato de lista para facilitar su consulta.")
variable_columns = st.columns(3)
for index, variable in enumerate(list(df.columns)):
    with variable_columns[index % 3]:
        st.markdown(f"- `{variable}`")
st.caption("La definición funcional de cada variable debe validarse con el diccionario de datos del área responsable antes de formalizar el estudio.")
