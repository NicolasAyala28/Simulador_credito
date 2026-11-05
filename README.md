# Simulador de crédito vehicular

Aplicación Streamlit del área de Riesgo para experimentar con la política de originación: calcula el RIE, clasifica
el apetito por perfil y por vehículo, define la decisión por tipo de crédito, evalúa mitigantes y muestra la decisión
final sobre una foto fija de solicitudes. Es experimental: sus resultados no son decisiones operativas hasta la
aprobación del comité.

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Después de cambiar archivos de `src/` hay que reiniciar Streamlit; los cambios en `pages/` se ven al recargar.

## Hojas

Orden del menú: 1 Base de datos · 2 Población (segmentos y ocupaciones, y gráficas) · 3 Cosechas (General y Segmento)
· 4 RIE · 5 Apetito · 6 Mitigantes · 7 Decisión final · 8 Evaluar solicitud.

## Base de datos (solicitudes 2024-01 a 2025-04)

El simulador lee `data/solicitudes_2024_2025.parquet`, que genera `motor_decision/generacion_base.ipynb` (celda de
guardado de la base del simulador): solicitudes de `frank_requests` con la respuesta del motor (`frank_responses`:
`Decision`, `RIE`) y, en las desembolsadas, `credito`, `id_fecha_desembolso`, `ventana`, `mora_max_15m`,
`PlanFinanciacion` y `desembolsado` (1/0). `src/data_loader.py::normalize_solicitudes`:

- Renombra a los nombres del simulador: `Acierta`→`acierta`, `IngresoTotalMensual`→`ingresos`, `TasaMV`→`tasa_nominal`,
  `ValorCuotaCST`→`ValorCuotaSectorTelcos`, `Licencia`/`Condicion`→`licencia_vehiculo`/`condicion_vehiculo`,
  `ClaseVehiculo`→`clase_vehiculo`, `Decision`→`FrankDecision`, `RIE`→`RIE_motor`.
- Traduce códigos con el diccionario `Variables Frank Oriana_v5.3.xlsx` (extraído a `config/codigos_solicitud.json`):
  `ClaseVehiculo` (1–28), `EstadoCivil` (1 casado, 2 soltero, 3 unión libre, 4 separado/viudo/divorciado),
  `Licencia` (1 PAR, 2 PUB), `Condicion` (1 N, 2 U) y `CalificacionMontoMax` (1 AA … 10 «-»). `Ocupacion` se traduce
  con `config/ocupacion_aval.json`. Los códigos sin mapeo quedan como «Código N sin mapeo».
- Tipo de crédito: la columna `productivo` de la base y, donde venga vacía, `DestinoCredito` (P productivo, C consumo).
- Asume que ninguna garantía está prendada (el dato de las solicitudes no es confiable).
- Excluye las solicitudes de 2024 sin respuesta del motor y descarta identificadores que no usa (`Avalista1AVId`).

`prepare_data` aplica además:

- **Alcance:** omite las solicitudes con valor a financiar (`ValorVh − MontoCtaInicial`) mayor a 180 millones
  (`MAX_FINANCIACION`) o menor a 10 millones, incluidos los negativos (`MIN_FINANCIACION`). Base de datos y Apetito muestran
  cuántas se omiten en «Notas sobre registros omitidos», al final de la hoja (`exclusion_notes`); en Apetito esa
  sección reúne también los demás avisos (RIE no calculable, desembolsadas fuera de la mora del vehículo, mora
  ausente). La hoja Evaluar solicitud no evalúa solicitudes fuera de ese rango.
- **Calidad de datos (`clean_data`):** `ValorVh` toma `valor_garantia_inicial` cuando es mayor a 0; la cuota inicial (%)
  es `MontoCtaInicial / ValorVh` y solo vale si es menor a 100 %; el ingreso solo vale entre 1 y 100 millones.
- **Segmento:** ocupación del titular con `config/segmentacion.json`; Ama de casa y Universitario toman el segmento
  del avalista 1 o, si no lo tiene, Independiente Informal. Las demás ocupaciones sin segmento quedan «Sin dato» y se
  excluyen.
- **Meses de vida:** desde el desembolso hasta la fecha de corte inferida con `meses_observados` o `ventana`; se usa
  en el filtro de antigüedad de Apetito, que solo aplica a las desembolsadas.
- **`veh`:** licencia/condición (Público/Nuevo, Público/Usado, Particular/Nuevo, Particular/Usado).

Inicio y Base de datos muestran el periodo de solicitudes (`FechaProceso`) y el de desembolsos (`id_fecha_desembolso`).

## Parámetros y versiones

Una versión reúne los parámetros RIE, las matrices de apetito y decisión de la hoja Apetito y los mitigantes exigidos. Lo
editado en una hoja se aplica en las demás durante la sesión. Al abrir la app se carga `na_v4` (`INITIAL_VERSION` en
`src/parametros.py`) o, si ese archivo no existe, la versión 1 (`config/versiones/base_v1.json`, fija). «Guardar como nueva versión» (barra lateral) crea
`config/versiones/<nombre>_v<N>.json` sin sobrescribir otras; cada usuario solo elimina sus versiones. Las matrices
vacías se llenan con `config/apetito_default.json`. La lógica está en `src/parametros.py`, `src/apetito.py` y
`src/decision.py`.

## Hoja RIE

`pages/4_RIE.py` y `src/rie.py`: puntaje 0–7 = Respaldo (LTV por licencia, 0–3) + Ingresos (PTI, DTI y EI, 0–2 cada
uno, promedio × 1,5) + Experiencia (0 o 1). Grupos del árbol: puntaje 0–3 → «0-1», 4–5 → «2», 6–7 → «3».

- La cuota usa el plazo real `PlazoMeses` y la tasa mensual `TasaMV` (en %); el plazo de la hoja solo se usa si la
  solicitud no trae plazo.
- PTI y DTI usan umbrales por licencia y estado civil (casado / unión libre u otro).
- Experiencia: monto máximo > 30 % del valor a financiar, antigüedad de al menos un año y calificación AA, A o BB.
  En licencia pública, además, alguna garantía debe ser de servicio público (`RPV1Servicio`–`RPV3Servicio`).
- `rie_scores(..., detail=True)` devuelve los componentes (lo usa la hoja Evaluar solicitud).

## Hoja Apetito

`pages/5_Apetito.py`: clasificación de apetito, con filtros de segmento y antigüedad mínima (por defecto ≥ 15 meses) y un
filtro de mora (> 30, > 60, > 90; por defecto > 90). En cada matriz, la concentración usa todas las solicitudes y la
mora solo las desembolsadas. Lo editado se aplica con «Guardar configuración».

1. **Vehículo**, una pestaña por tipo de crédito: filas rango de valor a financiar (V1–V5, quintiles de
   `ValorVh − MontoCtaInicial` sobre toda la base, con su intervalo en millones) × columnas licencia/condición, con nivel Bajo, Medio o Alto. En
   el JSON, `filas` da el nivel por tipo y licencia/condición (igual en los cinco rangos) y `por_valor` permite fijarlo
   por rango.
2. **Perfil**, una pestaña por segmento: filas RIE (0-1, 2, 3) × columnas P10…P100, deciles de `acierta` dentro del
   segmento, con nivel Bajo, Medio o Alto. Con `"calibrar": true` en el JSON, cada segmento se calibra con la mora > 90
   (`perfil_sugerido`).
3. **Decisión**, una pestaña por tipo de crédito: filas nivel perfil × columnas nivel vehículo, con Aprobado,
   Condiciones o A estudio. Las celdas en Condiciones pasan a Mitigantes.
4. **Distribución de la decisión:** proporción de Aprobado, Condiciones y A estudio por tipo de crédito, para todas
   las solicitudes y para las desembolsadas.

Vehículo y perfil se muestran en 2 × 2 (concentración y mora; nivel de apetito y proporción por nivel); la decisión,
con concentración y mora arriba y la matriz editable abajo.

## Hoja Mitigantes

`pages/6_Mitigantes.py`, con los datos de la solicitud:

- **Avalista idóneo:** avalista 1 con Acierta y capacidad de pago (ingreso / cuota) mínimos de `config/avalista.json`.
- **Garantía idónea:** garantías RPV1–RPV3 con máximo 10 años y valor superior al % del vehículo de
  `config/garantia.json`; la solicitud la tiene si suman más del 50 % del valor a financiar.
- **FGA:** se puede pedir siempre. Con Garantía y FGA en 1 se exige garantía o FGA; con FGA solo (sin Garantía) se
  exige FGA. Una fila sin ningún mitigante exigido ni Desistir queda Sin decisión.
- **Tabla:** combinaciones en Condiciones, por **Combinación** (tipo × nivel perfil × nivel vehículo) o por **Detalle**
  (además licencia/condición y RIE). Lo exigido al detalle tiene precedencia sobre la combinación. Con Avalista y
  Garantía en 1 se exigen los dos. En el detalle, **Desistir** (1/0) envía la fila a estudio sin evaluar mitigantes.
  Los filtros se aplican con «Aplicar filtros» y lo editado con «Guardar configuración de mitigantes»; «Guardar y
  crear nueva versión» aplica lo editado y guarda la versión (con el nombre de la barra lateral) en un solo paso.
  «Guardar como nueva versión» de la barra lateral guarda los mitigantes por combinación y por detalle ya aplicados.
- **Decisión final:** Aprobado = celdas Aprobado + Condiciones que cumplen; A estudio = celdas A estudio + Condiciones
  que no cumplen o desistidas.

## Hoja Decisión final

`pages/7_Decision_final.py`: misma regla que Mitigantes (`matrix_decisions` en `src/decision.py`) sobre todas las
solicitudes con combinación completa; torta total, barras y tabla por segmento.

## Hoja Evaluar solicitud

`pages/8_Evaluar_solicitud.py`: formulario para digitar una solicitud (valor del vehículo, cuota inicial, tasa MV, plazo 12–72,
cuota con telcos, ingresos, puntaje Acierta, ocupación del titular y del avalista, estado civil, monto máximo, su fecha
y su calificación AA…K, licencia, condición, destino y mitigantes 1/0 que se suponen idóneos). «Evaluar solicitud»
aplica las reglas de la versión activa: segmento, RIE, decil del puntaje en su segmento y quintil de valor a financiar (con la
base del simulador), niveles de perfil y vehículo, decisión de la matriz y mitigantes, y muestra la decisión final. La
sección «Factores del RIE» detalla cada componente con su valor, su calificación y la regla. En licencia pública se
asume cumplido el requisito de garantía de servicio público.

## Hojas Cosechas · General y Cosechas · Segmento

`pages/3_Cosechas_General.py` y `pages/3_Cosechas_Segmento.py` replican las secciones 3, 4.2, 5 y 6 del notebook
`Score/default/default.ipynb`. Leen la base crédito-mes `data/cosechas_2022_092025_ST.parquet` (sin traslados, con
`Avalista1Ocupacion`); los cálculos están en `src/cosechas.py`.

- **Filtros:** mora medida (ICC 60 / ICC 90), que define el umbral de días de mora; cosechas; corte del ICC en la
  última altura completa de cada cosecha; y, en Segmento, los segmentos.
- **Exclusiones:** créditos con algún corte anterior al desembolso (altura −1) y créditos con segmento *Sin dato*.
- **Cosecha:** ICC = saldo de capital con mora mayor al umbral ÷ desembolso de la cosecha, por altura.
- **Default (rodamientos):** roll rate por rango de mora anterior; se indica el rango desde el cual el deterioro supera
  a la recuperación.
- **Acumulación por monto:** acumulación, por altura, del monto de los créditos que superan el umbral por primera vez,
  con las cosechas 2022–2024.
- **Justificación:** por qué el default de originación se define a 90 días y el de seguimiento a 60.

## Diseño visual

La identidad visual está centralizada en `src/theme.py` y `.streamlit/config.toml`: cabecera verde corporativa, barra
lateral de marca y paneles claros. En las matrices, Bajo / Aprobado en verde, Medio / Condiciones en naranja y
Alto / A estudio en rojo.
