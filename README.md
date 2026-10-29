# Simulador de crédito vehicular

Aplicación Streamlit para análisis de población, distribución de variables y matrices de score, exposición y riesgo.

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Diseño visual

La identidad visual está centralizada en `src/theme.py` y `.streamlit/config.toml`. La aplicación usa una cabecera verde corporativa, barra lateral de marca, paneles claros y categorías AA (verde), A (amarillo) y AE (rojo).

## Árbol (antes Matrices)

- **Árbol:** Segmento → RIE (normalización agrupada en 0-1, 2 y 3) → Licencia → Condición, con diagrama y tabla de concentración de `mora_max_15m` en rangos de 30 días (columna Mora > 30 = % de créditos de la rama con mora mayor a 30 días; los rangos 31–60 a 150+ reparten esa mora y suman 100%). La tabla tiene filtros por Segmento, RIE, Licencia y Condición, y una columna Decisión editable (Aprobado, Condiciones, A estudio) que se guarda por rama en `config/arbol_decision.json`. Al final, tarjetas con los créditos Aprobados, en Condiciones y A estudio (cantidad y % sobre el total de la tabla). Replica la hoja 1 de `arbol.xlsx`. Los créditos sin RIE calculable se excluyen y se informa su cantidad.
- El puntaje RIE se calcula en `src/rie.py`, compartido con la página RIE.


## Página RIE (versión 2)

Se agregó `pages/3_RIE.py` antes de Matrices. Incluye Respaldo (LTV), Ingresos (PTI, DTI y EI), Experiencia, distribuciones de densidad, tarjetas de registros sin información y rangos editables temporalmente durante la sesión. La cuota mensual se estima con la fórmula de amortización francesa usando `tasa_nominal` y un plazo predeterminado de **60 meses**. El plazo permanece editable temporalmente hasta incorporar la variable al conjunto de datos. Los umbrales de PTI/DTI deben validarse con la política antes de usar resultados operativos.
# Simulador_credito

## Página Mitigantes

`pages/5_Mitigantes.py` muestra, para el segmento seleccionado:

- **Tarjetas:** créditos con avalista(s) idóneo(s), con garantía(s) idónea(s) y con ambos (cantidad y % sobre los créditos del segmento).
- **Avalista idóneo:** Acierta ≥ `acierta` y capacidad de pago (`ingreso del avalista / cuota calculada`) ≥ `capacidad_pago` de `config/avalista.json`; basta con uno de sus avalistas (hasta 3).
- **Garantía idónea:** cada garantía (RPV1–RPV3) debe estar no prendada (`RPVxPrendado = NO`), tener máximo 10 años y un valor superior al `valor` de `config/garantia.json` (20 %) del valor del vehículo. El crédito tiene garantía idónea si sus garantías idóneas suman más del 50 % del valor a financiar (`ValorVh − MontoCtaInicial`).
- **Tabla:** las ramas (Segmento, RIE, Licencia, Condición) con decisión "Condiciones" en la hoja Árbol. Las columnas editables Avalista y Garantía (1/0) definen el mitigante exigido; Decisión - Cumple / No cumple es el % de créditos de la rama que tienen o no los mitigantes exigidos. Las ramas con 0/0 no se evalúan. Las condiciones se guardan en `config/mitigantes_condiciones.json`.
- **Decisión final (tarjetas al final):** Aprobado = ramas con decisión Aprobado más los créditos de ramas con Condiciones que cumplen los mitigantes exigidos; A estudio = ramas con decisión A estudio más los que no cumplen. % sobre los créditos del segmento con RIE calculable.
- La cuota calculada usa el plazo de la hoja RIE (60 meses por defecto); la fórmula está en `src/common.py`.

## Calidad de datos

Las reglas acordadas en la auditoría se aplican en `clean_data` (`src/data_loader.py`), que usan todas las páginas a través de `prepare_data`:

- **Valor del vehículo:** `ValorVh` toma `valor_garantia_inicial` cuando este es mayor a 0. Venía en 0 en ~28 % de la base.
- **Cuota inicial (%):** se recalcula como `MontoCtaInicial / valor_garantia_inicial × 100`. Solo se aceptan valores inferiores a 100 %; los demás se tratan como sin dato.
- **Ingreso:** se usa `ingresos`. Solo se aceptan valores entre 1 y 100 millones mensuales; los demás (incluidos los valores en 0) se tratan como sin dato.
- **Cuota sector telcos:** se usa `ValorCuotaSectorTelcos` (numérico, sin separadores).
- **Columnas eliminadas:** `traslado` (constante), `IngresoTotalMensual` y `ValorCuotaCST` (reemplazadas por las anteriores).
- **Mora:** se usa `mora_max_15m`, la mora máxima en los primeros 15 meses desde el desembolso (o hasta el corte si el crédito aún no los cumple), con `meses_observados` como meses efectivamente observados.
- **Meses de vida:** `meses_vida` = meses entre el desembolso y la fecha de corte, que se infiere de la base (último mes observado). Es la base del filtro de antigüedad mínima en Árbol; no usa `meses_observados` porque este se reduce cuando el crédito se cancela antes de los 15 meses.
- **Nombres de columnas:** `Frank`, `FGA`, `FrankDecision` y `PlanFinanciacion` se normalizan a esos nombres sin importar las mayúsculas con que lleguen.
- El resto de valores (`acierta = 0`, `FechaAperturaMontoMax = 0001-01-01`, variables de buró) se toman tal como vienen en la base.

Pendientes anotados:

- 6 créditos no cruzan con la solicitud (`NumeroSolicitud` nulo), por lo que no tienen variables del motor.
- `MontoMaxSolicGeneral` tiene 22 valores por encima de 1.000 millones (máximo 16.880 millones).

## Página Decisión

`pages/6_Decision.py` muestra la decisión final de cada crédito luego de mitigantes, con una torta (total) y barras apiladas por segmento, más una tabla con cantidades y %:

- Ramas con decisión Aprobado o A estudio en la hoja Árbol conservan esa decisión.
- En las ramas con Condiciones, el crédito pasa a Aprobado si cumple los mitigantes exigidos en la hoja Mitigantes y a A estudio si no.
- Sin decisión: créditos de ramas sin decisión en Árbol o con Condiciones en 0/0.
- La lógica es compartida con Mitigantes en `src/decision.py`. La base son los créditos con RIE calculable.

## Páginas Cosechas · General y Cosechas · Segmento

`pages/7_Cosechas_General.py` y `pages/7_Cosechas_Segmento.py` replican las secciones 3, 4.2, 5 y 6 del notebook `Score/default/default.ipynb`. Leen la base crédito-mes `data/cosechas_2022_092025_ST.parquet` (sin traslados, con `Avalista1Ocupacion`); los cálculos están en `src/cosechas.py`.

- **Filtros:** mora medida (ICC 60 / ICC 90), que define el umbral de días de mora; cosechas; corte del ICC en la última altura completa de cada cosecha; y, en Segmento, los segmentos.
- **Exclusiones:** créditos con algún corte anterior al desembolso (altura −1) y créditos con segmento *Sin dato* (misma segmentación que el resto del simulador).
- **Cosecha:** ICC = saldo de capital con mora mayor al umbral ÷ desembolso de la cosecha, por altura. En Segmento, un panel por segmento y una línea por cosecha.
- **Default (rodamientos):** roll rate por rango de mora anterior (transiciones entre meses consecutivos). Recuperación = el crédito baja de rango o se mantiene; Deterioro = sube. Se indica el rango desde el cual el deterioro supera a la recuperación. En Segmento, un panel por segmento con la recuperación y el deterioro de todas las cosechas seleccionadas y su rango de cruce.
- **Acumulación por monto:** acumulación, por altura, del monto desembolsado de los créditos que superan el umbral por primera vez, sobre el monto con evento hasta el mes 24, con las cosechas 2022–2024. La tabla muestra el % del desembolso a 24 meses, la altura en que se acumula el 60 % y el 80 %, y lo capturado al mes 15. En Segmento, una línea por segmento más el total.
- **Justificación:** en General, por qué el default de originación se define a 90 días y el de seguimiento a 60, con el deterioro y la cura desde 31–60 y 61–90. En Segmento, esos mismos indicadores por segmento.
