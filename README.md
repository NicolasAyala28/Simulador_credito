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

## Calidad de datos

Las reglas acordadas en la auditoría se aplican en `clean_data` (`src/data_loader.py`), que usan todas las páginas a través de `prepare_data`:

- **Valor del vehículo:** `ValorVh` toma `valor_garantia_inicial` cuando este es mayor a 0. Venía en 0 en ~28 % de la base.
- **Cuota inicial (%):** se recalcula como `MontoCtaInicial / valor_garantia_inicial × 100`. Solo se aceptan valores inferiores a 100 %; los demás se tratan como sin dato.
- **Ingreso:** se usa `ingresos`. Solo se aceptan valores entre 1 y 100 millones mensuales; los demás (incluidos los valores en 0) se tratan como sin dato.
- **Cuota sector telcos:** se usa `ValorCuotaSectorTelcos` (numérico, sin separadores).
- **Columnas eliminadas:** `traslado` (constante), `IngresoTotalMensual` y `ValorCuotaCST` (reemplazadas por las anteriores).
- El resto de valores (`acierta = 0`, `FechaAperturaMontoMax = 0001-01-01`, variables de buró) se toman tal como vienen en la base.

Pendientes anotados:

- 6 créditos no cruzan con la solicitud (`NumeroSolicitud` nulo), por lo que no tienen variables del motor.
- `MontoMaxSolicGeneral` tiene 22 valores por encima de 1.000 millones (máximo 16.880 millones).
