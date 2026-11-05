# Simulador de crédito vehicular

Aplicación Streamlit para análisis de población, distribución de variables y matrices de score, exposición y riesgo.

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Base de datos (solicitudes 2024-01 a 2025-04)

El simulador lee `data/solicitudes_2024_2025.parquet` (celda de guardado en `motor_decision/generacion_base.ipynb`):
solicitudes de `frank_requests` con la respuesta del motor (`frank_responses`: `Decision`, `RIE`) y, en las
desembolsadas, `credito`, `mora_max_15m` y `desembolsado` (1/0). `src/data_loader.py::normalize_solicitudes`:

- Renombra a los nombres del simulador: `Acierta`→`acierta`, `IngresoTotalMensual`→`ingresos`, `TasaMV`→`tasa_nominal`,
  `ValorCuotaCST`→`ValorCuotaSectorTelcos`, `Licencia`/`Condicion`→`licencia_vehiculo`/`condicion_vehiculo`,
  `ClaseVehiculo`→`clase_vehiculo`, `Decision`→`FrankDecision`, `RIE`→`RIE_motor`.
- Traduce códigos: `Ocupacion` con `config/ocupacion_aval.json`; `ClaseVehiculo` (1–28) y `EstadoCivil` (1 casado,
  2 soltero, 3 unión libre, 4 separado/viudo/divorciado) con `config/codigos_solicitud.json`, extraído del diccionario
  `config/Variables Frank Oriana_v5.3.xlsx`; tipo de crédito con la columna `productivo` de la base y, donde venga vacía, `DestinoCredito` (P productivo, C consumo). Los códigos sin mapeo quedan
  como «Código N sin mapeo».
- Asume que ninguna garantía está prendada (el dato de las solicitudes no es confiable).
- Excluye las solicitudes de 2024 sin respuesta del motor y descarta identificadores que no usa (`Avalista1AVId`).
- Alcance: `prepare_data` omite las solicitudes con valor a financiar (`ValorVh − MontoCtaInicial`) mayor a 180 millones (`MAX_FINANCIACION` en `src/data_loader.py`); Portada y Árbol muestran cuántas se omiten. Los quintiles de valor del vehículo se calculan después de esa exclusión.

Matriz de vehículo: una por tipo de crédito (productivo/consumo), con filas rango de valor del vehículo (V1–V5,
quintiles de `ValorVh` sobre toda la base, con su intervalo en millones) y columnas licencia/condición (40 celdas;
niveles por defecto en `config/apetito_default.json`: el nivel por tipo y licencia/condición se repite en los cinco
rangos, y `por_valor` permite fijarlo por rango). La clase de vehículo ya no entra en la decisión: tiene muy pocos
eventos de mora por clase para calibrarla. En el Árbol, la concentración usa todas las solicitudes y la mora solo las
desembolsadas. Mitigantes evalúa con la solicitud: avalista 1 idóneo (`config/avalista.json`), garantías RPV1–RPV3
idóneas (`config/garantia.json`, sin prenda) y FGA: se puede pedir siempre (1 en todas las solicitudes) y solo reemplaza a la garantía cuando la combinación la exige con FGA en 1 y la solicitud no tiene garantía idónea. La cuota (RIE y capacidad del avalista) usa el plazo real `PlazoMeses` y la tasa mensual `TasaMV` (en %); el plazo de la hoja RIE solo se usa si la solicitud no trae plazo.

## Diseño visual

La identidad visual está centralizada en `src/theme.py` y `.streamlit/config.toml`. La aplicación usa una cabecera verde corporativa, barra lateral de marca, paneles claros y categorías AA (verde), A (amarillo) y AE (rojo).

## Árbol (antes Matrices)

- **Versiones de parámetros (barra lateral de RIE, Árbol, Mitigantes y Decisión):** una versión reúne los parámetros RIE, la decisión por rama del Árbol y los mitigantes por rama. Lo editado en una hoja se aplica en las demás durante la sesión. Al abrir la app se carga la versión 1 (`config/versiones/base_v1.json`, fija). «Guardar como nueva versión» crea `config/versiones/<nombre>_v<N>.json` sin sobrescribir otras; cada usuario solo elimina sus propias versiones.
- **Árbol (MVP de apetito):** sin diagrama Sankey; la hoja es la clasificación de apetito, en este orden: Vehículo, Perfil, Decisión por tipo de crédito y la gráfica de distribución de la decisión. Cada matriz tiene un filtro de mora (> 30, > 60, > 90 sobre `mora_max_15m`) y dos tablas: cantidad y proporción, y la misma solo con los créditos con mora del filtro (Vehículo: proporción por fila; Perfil: por segmento; Decisión: por productivo/consumo). Debajo de Vehículo y de cada segmento de Perfil, una tabla con la proporción de créditos clasificada en Bajo, Medio y Alto. Los valores editables se guardan con la versión de parámetros (`apetito`):
  1. **Perfil**, por segmento: filas RIE (0-1, 2, 3) × columnas P10…P100, deciles de `acierta` calculados dentro de cada segmento sobre toda la base del segmento. Si la matriz está vacía se llena con la tabla de `config/apetito_default.json`, igual para todos los segmentos. Con `"calibrar": true` en ese JSON, cada segmento se calibra con la mora > 90 a 15 meses (`perfil_sugerido` en `src/apetito.py`: tasa de la celda suavizada hacia su fila RIE; Bajo si ≤ 0,8 × la del segmento, Alto si > 1,3 ×). La hoja abre con Mora > 90 y antigüedad ≥ 15 meses; si la base no trae `meses_observados`, la antigüedad se calcula con `ventana`.
  2. **Vehículo:** filas `nombre_linea` × columnas Público/Nuevo, Público/Usado, Particular/Nuevo, Particular/Usado. Si está vacía se llena con `config/apetito_default.json`, por nombre de línea.
  3. **Decisión perfil × vehículo**, una matriz para productivos y otra para consumo (`productivo`): filas nivel perfil, columnas nivel vehículo y en cada celda la decisión Aprobado (verde), Condiciones (naranja) o A estudio (rojo). Las celdas en Condiciones pasan a Mitigantes. Si está vacía se llena con las decisiones por defecto de `config/apetito_default.json`. La lógica por crédito está en `src/apetito.py`. La hoja tiene filtros de segmento y antigüedad mínima.
- **Árbol (versión anterior, ya no editable en la hoja):** Segmento → RIE (normalización agrupada en 0-1, 2 y 3) → Licencia → Condición, con diagrama y tabla de concentración de `mora_max_15m` en rangos de 30 días (columna Mora > 30 = % de créditos de la rama con mora mayor a 30 días; los rangos 31–60 a 150+ reparten esa mora y suman 100%). La tabla tiene filtros por Segmento, RIE, Licencia y Condición, y una columna Decisión editable (Aprobado, Condiciones, A estudio) que se guarda por rama con la versión de parámetros. Al final, tarjetas con los créditos Aprobados, en Condiciones y A estudio (cantidad y % sobre el total de la tabla). Replica la hoja 1 de `arbol.xlsx`. Los créditos sin RIE calculable se excluyen y se informa su cantidad.
- El puntaje RIE se calcula en `src/rie.py`, compartido con la página RIE.


## Página RIE (versión 2)

Se agregó `pages/3_RIE.py` antes de Matrices. Incluye Respaldo (LTV), Ingresos (PTI, DTI y EI), Experiencia, distribuciones de densidad, tarjetas de registros sin información y rangos editables temporalmente durante la sesión. La cuota mensual se estima con la fórmula de amortización francesa usando `tasa_nominal` y un plazo predeterminado de **60 meses**. El plazo permanece editable temporalmente hasta incorporar la variable al conjunto de datos. Los umbrales de PTI/DTI deben validarse con la política antes de usar resultados operativos. **Experiencia en licencia Pública:** además de monto, antigüedad y calificación, alguna garantía debe ser de servicio público (`RPV1Servicio`–`RPV3Servicio` con valor que empieza por «PUB», con o sin tilde). Si la base no trae esas columnas, el requisito se da por cumplido (supuesto anterior).
# Simulador_credito

## Página Mitigantes

**Detalle de la tabla:** con «Exigir mitigantes por: Detalle», cada combinación en Condiciones se abre por licencia/condición y RIE, con filtros. Lo exigido a una fila de detalle tiene precedencia sobre lo exigido a su combinación (vista «Combinación»); la regla está en `matrix_decisions` / `decide` de `src/decision.py`.
En la vista Detalle, la columna **Desistir** (1/0) envía esa fila a A estudio sin evaluar avalista, garantía ni FGA; se guarda con los mitigantes (clave `desistir`).
Los filtros se aplican con «Aplicar filtros» y los mitigantes con «Guardar configuración de mitigantes» (formularios: la hoja no se recarga en cada selección o edición).

**Versión actual:** la tabla muestra las combinaciones tipo (productivo/consumo) × nivel perfil × nivel vehículo con decisión Condiciones en la hoja Árbol, con los créditos de cada una, los mitigantes exigidos (Avalista, Garantía, FGA) y el % que cumple / no cumple. Los mitigantes de cada crédito salen de campos de la base: `avalista`, `garantia_adicional` y `FGA` (lo tiene si el valor es mayor a 0 o S/SI; null = 0). Si una combinación exige varios, el crédito debe tener todos. Ya no se usan `config/avalista.json` ni `config/garantia.json` ni los campos Avalista1–3 / RPV1–3 para la idoneidad. La decisión final usa la matriz de la hoja Árbol (`matrix_decisions` en `src/decision.py`). Lo que sigue describe la versión anterior por ramas del árbol, que aún usa la hoja Decisión.

`pages/5_Mitigantes.py` muestra, para el segmento seleccionado:

- **Tarjetas:** créditos con avalista(s) idóneo(s), con garantía(s) idónea(s), con ambos y con FGA (cantidad y % sobre los créditos del segmento).
- **Avalista idóneo:** Acierta ≥ `acierta` y capacidad de pago (`ingreso del avalista / cuota calculada`) ≥ `capacidad_pago` de `config/avalista.json`; basta con uno de sus avalistas (hasta 3).
- **Garantía idónea:** cada garantía (RPV1–RPV3) debe estar no prendada (`RPVxPrendado = NO`), tener máximo 10 años y un valor superior al `valor` de `config/garantia.json` (20 %) del valor del vehículo. El crédito tiene garantía idónea si sus garantías idóneas suman más del 50 % del valor a financiar (`ValorVh − MontoCtaInicial`).
- **Tabla:** las ramas (Segmento, RIE, Licencia, Condición) con decisión "Condiciones" en la hoja Árbol. Las columnas editables Avalista y Garantía (1/0) definen el mitigante exigido; Decisión - Cumple / No cumple es el % de créditos de la rama que tienen o no los mitigantes exigidos. Con solo Avalista en 1 basta un avalista idóneo. La columna FGA (1/0) respalda la garantía: en las ramas con Garantía y FGA en 1, el crédito sin garantía idónea cumple si tiene FGA (columna `FGA` de la base en 1); con Garantía en 0 no tiene efecto. Las ramas con 0/0 no se evalúan. Las condiciones se guardan con la versión de parámetros.
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

**Versión actual:** usa la misma base y reglas que Mitigantes (`matrix_decisions`): Aprobado y A estudio según la celda de la matriz perfil × vehículo de la hoja Árbol; en las celdas con Condiciones, Aprobado si el crédito cumple los mitigantes exigidos en Mitigantes y A estudio si no. Lo que sigue describe la versión anterior por ramas del árbol.

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
