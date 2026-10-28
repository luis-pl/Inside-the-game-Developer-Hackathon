# Recuperación de carga y comprobación del marcador

Revisión del 27 de octubre de 2026 a partir del reporte de que la aplicación
permanecía cargando. Las pruebas anteriores no cubrían suficientemente el arranque
de SQL en frío ni la contradicción narrativa que apareció en la nueva prueba.

## Fallo reproducido

La página y `/api/whoami` de Azure devolvían HTTP200 en 0,34 s y 0,10 s,
respectivamente, pero `list_matches` no contestó dentro de 15 segundos.
El catálogo del workspace terminó en HTTP503 (`MATCH_CATALOG_UNAVAILABLE`).
Azure SQL conservaba AutoPause de 60 minutos y notificó reanudación a las
22:17:23 UTC (17:17:23 en Bogotá). Después de reactivarse, la misma consulta
de catálogo devolvió HTTP200 en 0,65 s. Este comportamiento explica el fallo
de primera carga reproducido, anterior a cualquier inferencia del modelo.
No demuestra que toda solicitud lenta tenga esa misma causa.

Además, las peticiones del navegador no tenían un plazo propio y el sondeo con
`setInterval` podía solapar lecturas lentas. Un error de sondeo sólo mostraba un
aviso, conservando indefinidamente la apariencia de trabajo en curso.

## Corrección

- El catálogo reintenta una sola lectura fija ante timeout o estado transitorio,
  con un máximo total de 55 segundos. No reintenta HTTP401/403 y no acepta como
  catálogo la respuesta de otra operación. La carga y publicación de su caché
  permanecen bajo el mismo bloqueo para evitar peticiones duplicadas entre pestañas.
- Las llamadas de control del navegador esperan hasta 12 segundos; la carga de
  catálogo admite 60 segundos y explica la posible reactivación inicial.
- El sondeo es secuencial. Ante desconexión se detiene la animación y se ofrece
  **Recuperar estado**. No se reenvía la solicitud ni se afirma que el servidor haya
  terminado. La página visible se conserva. HTTP401 devuelve al acceso y HTTP404
  informa de conversación expirada.
- No se desactivó AutoPause, cambió el modelo, alteró la facturación ni publicó
  una nueva revisión de Azure. La instancia local fue reiniciada con respaldo de
  las conversaciones vigentes para cargar el código corregido.

## Error deportivo detectado durante la prueba

Una página nueva se generó en 44,953 segundos, pero el analista escribió que
Mock Objects FC había ganado 1–2. Los hechos originales indicaban un gol local
y dos visitantes: era una interpretación incorrecta de cifras correctas.

Se añadió una validación acotada de afirmaciones explícitas de ganador/perdedor
contra los marcadores citados de `get_match_context`, agrupados por partido y
evidencia. El error `MATCH_RESULT_CONTRADICTS_SCORE` exige corregir la afirmación.
El prompt también explica el orden local/visitante. No se cambiaron marcadores
ni cifras para hacer coincidir el texto. Esta validación no demuestra la validez
de toda posible interpretación táctica o semántica; esa limitación sigue vigente.

## Pruebas finales

| Prueba | Resultado |
|---|---|
| Suite Python completa | 453 pasan; 12,20 s |
| Suite frontend | 51 pasan; TypeScript y build pasan |
| Regresiones específicas de backend | 18 pasan: recuperación, autorización, límite total, caché concurrente y ganador/empate |
| Regresiones nuevas de navegador | 5 pasan: timeout, sesión, parada tras fallo, sondeo secuencial y cancelación |
| Actualizar el análisis del informe anterior | Completo en 36,381 s; ganador correcto; tres gráficos conservados |
| Crear otra página desde petición natural | Completo en 45,655 s; `shot_map` y `xg_story` disponibles |
| Cambiar sólo el título | Completo en 5,675 s; mismo informe, revisión superior y bloques conservados |
| Valores citados tras corregir análisis / crear | 14/14 y 27/27 coinciden con evidencia o métricas del renderer |

La primera prueba se envió desde el navegador. Las tres comprobaciones finales
se ejecutaron por el mismo HTTP del workspace y se verificó después su resultado
en la interfaz, incluido el título y el chat. No se debe atribuir al navegador un
envío que se hizo desde el cliente de pruebas.

El arranque en frío real produjo el fallo inicial. La corrección de su reintento
se probó mediante transporte simulado; las pruebas finales de extremo a extremo
usaron Azure ya activo. No se forzó otra pausa ni se garantiza una latencia fija
para cualquier consulta o disponibilidad del proveedor. Las conversaciones siguen
expirando después de una hora.

La comprobación visual final del cliente disponible fue a 839×831. El intento
de aplicar 390 px no cambió el viewport efectivo, por lo que no se presenta como
una nueva validación móvil. No se observó desbordamiento exterior ni animaciones
de trabajo una vez terminado el informe.

Trazas locales: `.temp/loading-investigation/`, con solicitudes, respuestas,
HTML antes/después y capturas. Resumen sin secretos:
[workspace-loading-verification.json](workspace-loading-verification.json).
