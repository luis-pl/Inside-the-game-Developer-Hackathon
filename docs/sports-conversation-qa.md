# Revisión de la conversación deportiva

Se probaron siete solicitudes cotidianas con el intérprete real y Beam Free Go,
sin pedir al usuario nombres de herramientas, IDs ni consultas técnicas. Los
contextos seleccionados se proporcionaron desde la interfaz simulada de la prueba.
No se ejecutaron las delegaciones de creación ni se modificaron páginas.

Esta es una revisión cualitativa del comportamiento observado, no un estudio con
usuarios humanos ni una validación estadística de todas las respuestas posibles.
Las siete llamadas terminaron en esta ejecución; eso no corrige los fallos de
tiempo del flujo completo documentados en `workspace-qa-latest.md`.

| Solicitud | Resultado observado | Evaluación |
|---|---|---|
| «Hola, ¿qué puedo mirar aquí?» | Propone mostrar el catálogo y usa “eventos y tracking”. El servidor sustituye ese saludo por una lista de partidos con IDs. | El mensaje final pierde orientación y cercanía. |
| «¿Qué es el xG? Explícamelo fácil, que no sé mucho de fútbol.» | Da una explicación y ofrece ver ejemplos. Usa “debería haber marcado” e incluye posición del portero sin distinguir qué modelo la utiliza. | Útil, pero requiere lenguaje probabilístico y distinguir el xG ilustrativo del proyecto. |
| «¿Quién fue mejor en este partido? No entiendo mucho de estadísticas.» | Decide buscar al mejor jugador por xG acumulado. | Ambigüedad mal resuelta: el usuario podría referirse a equipos. El xG individual tampoco es una evaluación global. |
| «Muéstrame cómo atacaron los dos equipos.» | Propone tiros, pases ofensivos y conducciones/regates; reconoce que Metrica no aporta xG. | Intención razonable. No se ejecutó la consulta; esto no certifica disponibilidad de todas las acciones propuestas. |
| «Añade el xG y dime quién fue el jugador estrella.» en Metrica | Explica que no hay xG y ofrece mapa de tiros u otro análisis. | Honesto, aunque técnico y centrado en lo que no puede hacer. Descarta al jugador destacado porque lo vincula exclusivamente al xG. |
| «Eso del Voronoi no lo entiendo. ¿Para qué sirve en fútbol?» | Explica cercanía, pero también dice que cada jugador “controla” una región y habla de espacio dominado; luego matiza. | Contradicción deportiva: la cercanía geométrica no acredita control efectivo. |
| «Ese gráfico no me ayuda, quiero algo más sencillo y que me expliques lo importante.» | Pregunta qué gráfico y qué aspecto quiere simplificar, enumerando términos estadísticos. | Demasiada carga para quien acaba de pedir sencillez. Conviene una sola aclaración si hace falta y proponer una lectura básica. |

## Causas comprobadas en el código

- `chat_http.py` reemplaza el saludo del catálogo por filas con IDs.
- Tras publicar un informe, el servidor construye una confirmación genérica con
  el número de gráficos; el chat no recibe una respuesta deportiva breve a la
  pregunta original.
- `sports_analyst.py` antepone etiquetas como “Observación” e “Interpretación
  prudente” a cada afirmación y añade referencias técnicas al mismo texto.
  La trazabilidad es útil, pero su presentación actual se parece a una auditoría.
- El intérprete admite crear, modificar, mostrar catálogo y aclarar. Las
  explicaciones conceptuales quedan clasificadas como aclaraciones, aunque algunas
  sí responden correctamente. No se comprobó un fallo de ejecución por esa etiqueta.

## Ajustes recomendados

1. Mantener el saludo y ofrecer dos o tres caminos concretos: ocasiones, pases y
   espacios. Dejar los identificadores en la selección y la trazabilidad.
2. Entender primero si se comparan equipos o jugadores. Una aclaración breve
   cuando sea imprescindible; evitar elegir un criterio como si fuera universal.
3. Dar primero una respuesta deportiva breve sustentada; después ofrecer la
   página o señalar el gráfico que la explica. Una confirmación de publicación no
   sustituye la respuesta al usuario.
4. Cuando falte una métrica, explicar la ausencia en una frase y ofrecer una
   alternativa concreta disponible, sin prometer un sustituto equivalente.
5. Conservar las citas y límites, separando su presentación de la lectura principal.
   No se propone retirar la validación de cifras ni suavizar hechos incómodos.
6. Explicar xG como probabilidad de gol de un tiro según el modelo, sin afirmar
   que un equipo debía marcar esa cantidad. Explicar Voronoi como cercanía, sin
   presentar sus regiones como posesión o control probado.

## Evidencia

Las solicitudes, respuestas, delegaciones y tiempos exactos están en
`.temp/sports-conversation-qa/responses.json`. Se conserva el hash del prompt usado.
La revisión inicial no modificó los prompts ni el comportamiento de los agentes.

## Cambios implementados y comprobación posterior

Tras la autorización del titular se modificaron los prompts y el comportamiento:

- La acción `answer` resuelve orientación y conceptos sin generar una página.
  Las definiciones revisadas de xG y Voronoi evitan prometer métricas ausentes o
  convertir cercanía en control. La bienvenida respeta el partido seleccionado.
- Una aclaración admite como máximo una pregunta. La prueba «¿quién fue mejor?»
  ahora distingue comparar equipos de buscar un jugador.
- El catálogo conserva la orientación y muestra nombres, con la lista completa
  disponible en el selector; no vuelca los IDs como respuesta inicial.
- El chat usa hasta dos afirmaciones validadas de la primera sección analítica
  útil. Conserva procedencia y alcance; no añade una nueva inferencia para redactar
  esa respuesta ni la sustituye por un recuento de gráficos.
- El informe conserva los hechos y el texto original en su payload. Presenta
  apartados legibles, la procedencia y la primera limitación visibles; referencias
  y detalle de límites se pueden desplegar.
- Una explicación conceptual junto a un informe existente enlaza a «Ver el
  informe», sin afirmar que hubo una actualización.

La comprobación posterior pasó **435 pruebas Python, 46 del frontend, TypeScript,
build y siete casos reales de conversación con Beam Free Go**. Esos casos evaluaron
el intérprete y la respuesta del anfitrión; no ejecutaron sus delegaciones analíticas.
La prueba por navegador sí envió un saludo y creó un informe desde una solicitud
cotidiana, completada en 31,24 s.

Otra ejecución con los prompts finales creó un informe con dos gráficos en
**35,22 s**, conservó esos bloques al editar el título en **4,983 s** y respondió
a la ausencia de xG de Metrica en **2,887 s**, sin producir una página ni cifras de
xG. Ese último caso usó `answer` con estado `complete`: terminar una explicación
no equivale a declarar disponible una métrica. Se actualizó la aserción anterior,
que sólo aceptaba `clarification`, manteniendo las comprobaciones de ausencia de
informe y de explicación explícita de la falta de xG.

La carga del catálogo falló con HTTP 503 en un intento previo a estas siete
preguntas. Un intento de reejecución fue interrumpido por el reinicio local durante
la preparación de la demo; no se cuenta como fallo del modelo. Se conservaron
los antecedentes de plazos agotados en `workspace-qa-latest.md`. Estos resultados
puntuales no garantizan latencia estable ni corrigen por sí solos todos esos casos.

Repetir la comprobación:

```powershell
.venv\Scripts\python.exe scripts\qa_sports_conversation.py
.venv\Scripts\python.exe scripts\qa_workspace.py --output-dir .temp\conversation-e2e
```

La salida estructurada de esta iteración está en
`docs/sports-conversation-verification.json`; solicitudes, delegaciones y páginas
completas permanecen en `.temp/sports-conversation-final/`,
`.temp/conversation-flow-final/` y `.temp/conversation-e2e-final/` sin credenciales.
