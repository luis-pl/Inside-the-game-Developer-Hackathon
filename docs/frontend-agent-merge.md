# Integración del frontend y revisión del último push de agentes

El 27 de octubre de 2026 se integró `origin/main` (`c9b9e49`, «arreglo frontend»)
en el `main` local, conservando el trabajo validado en `2927ab5`. Se volvió a
consultar el remoto antes de cerrar: `main` y la rama experimental seguían en
los commits revisados. No se hizo push ni despliegue.

## Cambios integrados y conflictos resueltos

Se incorporaron el nuevo workspace, visor, temas compartidos, panel de actividad
de agentes, métricas del partido y cronología que conserva huecos de tracking.
El visor sigue cargándose por separado. La UI principal de este push es inglesa;
la conversación y el análisis conservan español, inglés, portugués, francés,
italiano y alemán según el mensaje.

Se resolvieron ocho archivos en conflicto. Se conservaron la carga con plazo,
el sondeo secuencial y su recuperación, la evidencia original, el control de
ventanas, la carga progresiva de herramientas, la compactación y la validación
de citas. Se evitó duplicar el componente de iconos y la función HTTP anterior.
El nuevo pipeline detiene su estado animado ante desconexión y dice que hay que
recuperar el estado, en vez de afirmar que terminó o que está listo.

`main` también cambiaba los prompts y la copia del backend a inglés obligatorio.
Esas partes se resolvieron manteniendo el contrato de idioma solicitado por el
usuario. Las pruebas de copia inglesa ahora declaran `language="en"`; el español
sigue siendo el valor por defecto de los endpoints directos.

Se conservaron dos mejoras de compatibilidad: la procedencia desconocida se
presenta como **desconocida**, en los seis idiomas, y las notas antiguas conservan
fuentes y límites desplegables aunque su idioma difiera del idioma de presentación.

## Selección de la rama experimental

Se revisó `origin/experimento/agentes-nim`, incluido su nuevo commit `d534334`.
Se trasladó su diagnóstico acotado: `FACT_BUDGET_EXCEEDED`,
`EVIDENCE_BUDGET_EXCEEDED` y `EVIDENCE_MATCH_MISMATCH` permanecen distinguibles.
Una lista exacta evita publicar mensajes arbitrarios de excepciones. Las pruebas
comprueban tanto los tres códigos públicos como la ocultación de un error privado.

No se hizo merge completo de esa rama ni se afirma que todos sus cambios estén
integrados. Se descartaron para esta integración:

- El resumen de muestras usa `/data/samples_summary`, ruta que no existe en la
  evidencia original, y agrupa muestras sin separar explícitamente todos sus
  alcances. Requiere un contrato de hechos derivados antes de poder citarlo.
- El atajo para añadir gráficos decide por palabras y operaciones disponibles;
  no representa completamente filtros, instantes o múltiples gráficos de una
  misma receta solicitados en distintos idiomas. Se mantiene la edición tipada.
- El calentamiento periódico consulta Azure cada cuatro minutos incluso sin
  trabajo del usuario y puede impedir la pausa de SQL. No se activó ese consumo.
- No se importaron NIM, restricciones de capacidades ni aumentos de presupuesto
  de los experimentos anteriores.

## Pruebas del conjunto integrado

| Comprobación | Resultado |
| --- | --- |
| Python completo | **563 pasan**, 20,81 s |
| Frontend | **55 pasan** |
| TypeScript y build de producción | Pasan; entrada principal 262,26 kB / 83,04 kB gzip |
| Ruff y formato de Python modificado | Pasan |
| Detector Impeccable sobre las superficies nuevas | Sin hallazgos automáticos |
| Crear informe desde el navegador | Completo en **57,342 s**; dos gráficos, tres fuentes y 16 hechos citados verificados |
| Cambiar sólo el título desde el navegador | Completo en **5,789 s**; mismo informe, revisión 2 → 4; gráficos, evidencia y análisis idénticos; sin delegación a Data |
| Canario de pases después de integrar | Completo en **46,194 s**; `pass_map`, `structural_pass`, `play_replay`, 100 observaciones a 5 Hz, enlaces y cifras verificados |
| Workspace a 1280×900 y 390×844 | Sin desbordamiento exterior observado; controles y composición utilizables |
| Temas e historial | Claro/oscuro, cierre móvil con Escape, retorno del foco y recuperación del informe después de recargar funcionan |
| Navegación del documento | «View update» abre el informe móvil y enfoca los cambios; actividad muestra los cuatro agentes registrados |
| Visor con Metrica real | Un minuto, 300 muestras a 5 Hz; reproducir y buscar 30 s funciona; sincroniza muestra 150 de la cronología |
| Ausencias del visor | Conserva 15 observaciones sin balón y sus advertencias; no fabrica posiciones |
| Consola del navegador | Sin errores observados en workspace y visor |

Las dos solicitudes de creación/edición se enviaron desde la UI. La comparación
exacta de planes, JSON y citas se hizo posteriormente por HTTP con el mismo
propietario. El canario compuesto usó el harness HTTP, sin atribuir su envío al
navegador. No se repitió toda la matriz de recetas e idiomas de la fase anterior.

## Revisión técnica de interfaz

| Dimensión | Puntuación | Evidencia y límite |
| --- | ---: | --- |
| Accesibilidad | 3/4 | Foco visible, drawer con Escape y retorno, nombres accesibles y estados reales; no es una certificación con lectores de pantalla |
| Rendimiento | 3/4 | Visor separado, gráficos con huecos y búsqueda por tiempo; sin un benchmark de dispositivos lentos |
| Responsive | 3/4 | Se verificaron ambos tamaños reales; algunos controles compactos quedan por debajo de la recomendación de 44 px |
| Temas | 4/4 | Ambos modos observados; conserva los colores analíticos y los roles del tema |
| Integridad | 3/4 | Estados basados en actividad registrada y procedencia visible; algunos detalles de jerarquía de encabezados siguen mejorables |
| **Total** | **16/20** | **Buena integración, sin bloqueos funcionales detectados en lo probado** |

Hallazgos menores, fuera de los conflictos funcionales: **[P2]** ciertos botones
compactos de `frontend/src/analyst-workspace.css` y `workspace.css` miden 32–36 px;
44 px ofrece más comodidad táctil. **[P3]** `FieldPanel.tsx` mantiene un `h1` de
estado vacío dentro de un visor que ya tiene título principal. Ninguno produjo
un bloqueo en las pruebas, ni el detector automático sustituye esta revisión.
Si se continúa el acabado, corresponde una pasada acotada de
`$impeccable adapt` para objetivos táctiles y `$impeccable polish` al cerrar.

Las mejoras útiles a conservar son la separación de paneles, las ausencias
visibles, la identidad de cada equipo, la actividad basada en registros y la
recuperación del documento anterior cuando falla una nueva solicitud.

## Evidencia y reproducción

Resumen sin credenciales: [frontend-agent-merge-verification.json](frontend-agent-merge-verification.json).
Trazas y HTML completos locales: `.temp/frontend-merge/`. Capturas versionadas:
`docs/verification-images/frontend-merge-desktop.png` y
`docs/verification-images/frontend-merge-mobile.png`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd test
npm.cmd run build
cd ..
.\.venv\Scripts\python.exe scripts/qa_agents_quality.py --live --case structural-passes-es --port 8132 --output-dir .temp/frontend-merge/repeated-canary
```

Las inferencias usaron exclusivamente Beam Free en Go con precio cero verificado
antes de cada llamada; el proveedor reportó `cost=0`. No se cambiaron facturación,
modelo, cuota ni servicios. Las consultas reales usan el acceso ya autorizado;
el presupuesto de seguimiento de Azure no corta consumo. Las mediciones son de
ejecuciones concretas y no garantizan una latencia o tasa de acierto en producción.
