# Machine learning del demo

Última actualización: 2026-10-14. **DATOS DE DEMOSTRACIÓN**: todo lo que se describe aquí se entrena y
evalúa con datos sintéticos generados por el propio demo. Nada de lo que muestran estos modelos es una
observación de una operación real.

## 1. Qué hay

| Modelo | Puerto (aplicación) | Adaptador (scikit-learn) | Para qué sirve |
|---|---|---|---|
| Pronóstico diario de demanda por corredor (P50 y P90) | `DemandForecaster` | `SklearnDemandForecaster` (`HistGradientBoostingRegressor`, pérdida por cuantiles) | Comparar contra el percentil histórico en el tablero de capacidad |
| Anomalías en esperas y tiempos de servicio por cliente | `AnomalyDetector` | `SklearnAnomalyDetector` (`IsolationForest`) | Señalar dónde mirar, con una frase legible |
| Riesgo de retraso (probabilidad de salir de la ventana) | `DelayRiskPredictor` | `SklearnDelayRiskPredictor` (`HistGradientBoostingClassifier`) | Priorizar la atención de clientes en riesgo |
| Segmentación de clientes | `PatternMiner` | `SklearnPatternMiner` (`KMeans`, k por silueta) | Describir grupos de comportamiento parecido |

El dominio (`domain/ml`) solo conoce tipos propios (`Forecast`, `Anomaly`, `DelayRisk`, `Segment`,
`ModelMetadata`) y funciones puras (festivos de Colombia, MAE/MAPE/Brier/AUC, partición temporal).
`application/use_cases/ml` contiene `MlService` (`TrainModels` + `DetectPatterns`), los casos de uso de
acceso (`GetPatterns`, `RetrainModels`) y el reentrenamiento programado. Los adaptadores de scikit-learn
viven en `adapters/outbound/ml`; import-linter impide que dominio y aplicación importen `sklearn`.

## 2. Datos (DEMO-ONLY)

`adapters/outbound/demo_data/ml_history.py` genera, con una semilla fija por empresa, 90 días de historia
(2026-07-12 a 2026-10-09) a partir de **los corredores y clientes de esa empresa**:

- Empresa A: 8 corredores, 36 clientes, 2 664 visitas. Empresa B: 8 corredores, 22 clientes, 1 628 visitas.
  `DOCS.MD` §13.5 sugiere ~15 corredores y 40–300 clientes: el demo queda por debajo en clientes y
  corredores porque reutiliza los datos sintéticos ya existentes; no se afirma cumplir ese rango.
- **Patrones sembrados** (la interfaz los declara): picos de demanda los lunes; demanda más alta en los
  días de pago quincenal; menor demanda en festivos; un cliente con esperas largas los viernes entre las
  10:00 y las 12:00; más tráfico y más retrasos en horas pico (07:00–09:00 y 17:00–19:00).
- Los días sin dato son **ausentes**, no cero. La demanda media de cada corredor sale de la serie del
  módulo de capacidad, de modo que las magnitudes son coherentes con el tablero.

## 3. Entrenamiento y evaluación

- Partición **temporal** (el 20 % de días más recientes prueba; lo anterior entrena). Ninguna variable usa
  información del propio día objetivo ni posterior (probado).
- El modelo evaluado se reajusta con toda la historia para producción (mismos hiperparámetros).
- Semilla fija = semilla de la historia de la empresa. Mismo dato + misma semilla = mismas métricas y
  mismos pronósticos (probado).
- **Línea base ingenua del pronóstico:** el valor de hace 7 días. **Del clasificador:** la tasa base.
- Importancia de variables por **permutación** sobre la partición de prueba.

### Resultados de una ejecución (Empresa A, semilla 20261001)

| Modelo | Resultado | Lectura honesta |
|---|---|---|
| Demanda | MAE 2,73 t frente a 5,20 t de la línea base; MAPE 6,2 % frente a 11,6 % | Mejora clara **en este fixture**; los patrones eran sembrados |
| Demanda (P90) | Cobertura 79,6 % en la prueba | **Por debajo del 90 % nominal**: el P90 es optimista; no usarlo como garantía |
| Anomalías | El cliente sembrado (viernes 10:00–12:00, 2,9 veces su patrón) sale primero | Encuentra lo sembrado; no demuestra que encontraría patrones reales |
| Riesgo de retraso | AUC 0,68; Brier 0,179 frente a 0,199 de la tasa base; precisión 58,5 %, recall 25,7 % (umbral 50 %) | Mejor que el azar, **poco potente**; el recall es bajo |
| Segmentos | k = 2, silueta 0,33 | Separación débil: son una descripción, no categorías |

Estas cifras salen de una ejecución local con la semilla fija; las pruebas verifican las
**desigualdades** (modelo mejor que la línea base, AUC > 0,55, el detector encuentra el patrón sembrado), no
estos valores exactos.

## 4. Versionado, integridad y aislamiento

- Cada empresa tiene su propio `MlService`, su propio lector de historia y su propio registro de modelos
  (`InMemoryModelRegistry`, creado en su espacio de trabajo). No existe una operación que reciba un tenant
  ni un nombre de empresa (probado: dos empresas, hashes y clientes distintos; reentrenar una no toca la
  otra).
- Metadatos por versión: nombre, versión, fecha, semilla, métricas, **SHA-256 del artefacto**, descripción
  del conjunto de entrenamiento y versión de la librería.
- Antes de cargar un artefacto se recalcula su hash y se compara con el registrado; si no coincide, **no se
  carga** (`ArtifactIntegrityError`, probado alterando el artefacto). Los artefactos son `pickle` generados
  por el propio adaptador y solo se deserializan tras esa verificación; nunca se carga un archivo que
  venga de un usuario.
- Reentrenamiento: manual (`POST /api/v1/patterns/retrain`, rol gerencia, 3 por minuto, auditado con las
  versiones) y programado cada 24 h para las empresas ya entrenadas (nunca entrena en frío).

## 5. Límites conocidos

1. Datos sintéticos: los patrones son los sembrados; no hay evidencia de rendimiento en operación real.
2. Horizonte de pronóstico de 7 días; no conoce eventos extraordinarios.
3. Cobertura del P90 por debajo del valor nominal en el fixture.
4. El riesgo de retraso es una probabilidad estimada con recall bajo; no es certeza ni sustituye al
   despachador. Se calcula por cliente en condiciones **típicas**; **todavía no** alimenta de forma
   automática la propuesta de re-secuenciación del ruteo (pendiente).
5. Los segmentos son una agrupación útil para la empresa, no categorías objetivas.
6. Las anomalías son asociaciones estadísticas; la interfaz no afirma causas.
7. Los modelos viven en memoria: reiniciar el backend los descarta (se reentrenan al primer uso).
8. No se midió la importancia por segmento ni la calibración con curvas (solo Brier).

## 6. Cómo reproducirlo

```powershell
# desde APP/Backend
.\.venv\Scripts\python.exe -m pytest tests/ml tests/integration/test_ml_service.py tests/security/test_patterns_http.py
```
