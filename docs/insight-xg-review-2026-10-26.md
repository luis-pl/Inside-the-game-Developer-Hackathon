# Revisión de xG y trazabilidad · 26 de octubre de 2026

Se auditó la API en lectura: veinte partidos, 209 tiros sintéticos y 249 tiros
reales. Todos los valores sintéticos coincidieron con `toy-distance-angle-v2`
y con las sumas de la API (tolerancia absoluta 1e-10). Los diez partidos reales
importados no tienen xG: se conserva `null`.

Para el partido 900001: equipo 1 = 1,0615838865393195; equipo 2 =
0,6287962406666504; total = 1,6903801272059698. El marcador 1–2 no exige que el
xG coincida con los goles.

El xG sintético **no está calibrado**: usa sólo distancia y apertura de portería;
ignora portero, defensores, parte del cuerpo y asistencia. El generador fuerza
el primer tiro a `Blocked` para asegurar cobertura. La auditoría comprueba
fórmula e integridad, no demuestra calidad predictiva. No se alteraron sus valores.
Referencia conceptual: [Hudl StatsBomb](https://statsbomb.com/soccer-metrics/expected-goals-xg-explained/).

## Correcciones y comprobaciones

- Los mapas calculan sus métricas sobre los mismos tiros únicos que dibujan;
  no heredan el resumen del partido entero al filtrar equipo, jugador o período.
- Un xG ausente/invalidado no se transforma en cero ni en un total parcial oculto.
- Las series se ordenan, deduplican y rechazan intervalos solapados o alcances
  de participantes que podrían duplicar cifras.
- El acumulado se reinicia por período y se indica en cada gráfico. Se distingue
  el total de todos los períodos del punto final de P2. Los ejes indican que
  terminan en la última acción incluida; no se inventa duración de la fuente.
- 391 pruebas automatizadas pasaron; los controles verifican además los valores
  mostrados contra los tiros de una lectura independiente de la API.

## Nueva ejecución con ambos agentes

Beam Free gratuito, sin fallback de pago: tres páginas y dos modificaciones.
Crear: 20,176 s; añadir red: 31,725 s; configurar: 3,232 s; comparar: 2,549 s;
Voronoi/replay: 34,354 s. No es una garantía para cualquier petición.

Hubo intentos con IDs como strings: el contrato los rechazó y el modelo los
corrigió. Se conservan en la bitácora. Se registraron 31 turnos observables, sin
razonamiento interno ni credenciales. El texto del analista fue un párrafo fijo
de prueba. En la comparación se reutilizó evidencia de Data; no hubo otra
inferencia de Data.

Los prompts completos usados se guardaron con sus SHA-256, junto con solicitudes,
argumentos, respuestas de tools, planes, evidencia y HTML. La traza pertenece a
esta nueva ejecución: no se reconstruyeron mensajes de la ejecución anterior.
Después se recompilaron los mismos planes/evidencias para aclarar las etiquetas,
sin inferencia adicional.

[Resumen verificable JSON](insight-xg-review-2026-10-26.json).

## Abrir los resultados locales

- Índice: `http://127.0.0.1:8083/xg-review/index.html`.
- Carpeta: `.temp/insights/xg-review/` (ignorada por Git).
- `README.md`: trazabilidad legible de cada caso y solicitudes a ambos agentes.
- `trace.json`: intercambio estructurado, errores y evidencia original.
- `prompt-data.md` / `prompt-insights.md`: instrucciones exactas de la ejecución.
- `insight-review.zip`: extraer y abrir `index.html`; las páginas no necesitan
  servidor, autenticación ni internet. No contiene claves.

Para reactivar únicamente el visor:

```powershell
.\.venv\Scripts\python.exe -m http.server 8083 --bind 127.0.0.1 --directory .temp/insights
```

## Reproducir

En una terminal, después de configurar las credenciales privadas existentes:

```powershell
python scripts/qa_insight_trace_server.py
```

En otra terminal:

```powershell
python scripts/audit_xg.py
python scripts/qa_insight_agent.py --base-url http://127.0.0.1:8087 --output-dir .temp/insights/xg-review
python -m pytest -q --junitxml=.temp/insights/xg-review/pytest.xml
python scripts/build_insight_qa_bundle.py .temp/insights/xg-review
```

La generación requiere sesiones/credenciales vigentes y confirmación de precio
cero de Beam Free. La traza de QA es optativa y local; detener su servidor al
terminar para no registrar solicitudes ajenas a la prueba.

## Integración concurrente

Se conservó el push del compañero `306f266` y se integró sin conflictos. La suite posterior al merge pasó **404 pruebas**. Las páginas y los 31 turnos del modelo corresponden a la ejecución anterior al merge (snapshot `2870fd3`); no se inventaron turnos ni se repitió inferencia para esta comprobación.
