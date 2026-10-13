# Simulador de crédito vehicular

Aplicación Streamlit para análisis de población, distribución de variables y matrices de score, exposición y riesgo.

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Diseño visual

La identidad visual está centralizada en `src/theme.py` y `.streamlit/config.toml`. La aplicación usa una cabecera verde corporativa, barra lateral de marca, paneles claros y categorías AA (verde), A (amarillo) y AE (rojo).

## Matrices

- **Score:** Acierta vs. Frank, con deciles 0–1000, matriz principal editable, restablecimiento y guardado local.
- **Exposición:** cuota inicial vs. valor del vehículo, con matriz editable por deciles de la población.
- **Riesgo:** estructura editable de categorización 1–7.
- Las matrices de concentración muestran la proporción de registros por combinación de deciles. La matriz condicionada queda preparada visualmente, sin aplicar filtros ni inventar una regla de negocio mientras esta no se defina.


## Página RIE (versión 2)

Se agregó `pages/3_RIE.py` antes de Matrices. Incluye Respaldo (LTV), Ingresos (PTI, DTI y EI), Experiencia, distribuciones de densidad, tarjetas de registros sin información y rangos editables temporalmente durante la sesión. La cuota mensual se estima con la fórmula de amortización francesa usando `tasa_nominal` y un plazo predeterminado de **60 meses**. El plazo permanece editable temporalmente hasta incorporar la variable al conjunto de datos. Los umbrales de PTI/DTI deben validarse con la política antes de usar resultados operativos.
# Simulador_credito
