# Espacio de análisis

Modo Operate. Composición fijada por la solicitud: conversaciones / documento /
chat. La pregunta de estilo se presentó; mientras no haya una respuesta adicional
se aplica el blanco y negro solicitado, con color reservado a los gráficos.

## Direction contract
THESIS: un espacio de trabajo para preguntar, inspeccionar y corregir un informe.
OWN-WORLD: neutros puros, superficies diferenciadas por tono, tipografía de sistema,
controles compactos, líneas discretas y foco visible. Dos temas equivalentes.
STORY: seleccionar partido, pedir análisis, observar etapas reales y explorar el
documento; continuar con cambios en la misma conversación. La orientación y las
explicaciones de conceptos pueden responderse en el chat sin crear un documento.
FIRST VIEWPORT: navegación estrecha a la izquierda, documento amplio en el centro,
chat a la derecha. Sin página inicial comercial. El formulario siempre accesible.
FORM: distribución inicial solicitada explícitamente por el titular; no hay selección
aleatoria de una composición alternativa. El usuario puede ajustar paneles y mover
el chat a cualquiera de los lados del documento. En móvil se alternan documento y chat.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Comportamiento implementado

La composición inicial conserva historial / documento / chat. El historial parte
de 220px y el chat de 350px. Los separadores permiten arrastrar y ajustar con
teclado: flechas de 10px, Mayús + flechas de 40px, Inicio/Fin y doble clic para
restablecer un ancho. Los límites efectivos respetan el espacio disponible;
historial 170–300px y chat 250–620px. El historial puede contraerse a 62px en
escritorio. Un control mueve el chat al otro lado del documento y otro restablece
la disposición. Se guardan sólo preferencias de diseño en localStorage.

El historial se vuelve una barra de iconos entre 761px y 900px. Hasta 760px usa
un cajón modal con cierre, Escape, foco contenido y devolución al botón de apertura;
se ocultan ajustes de ancho y posición. Documento y chat se alternan sin borrar
su contenido. El formulario permanece al pie del chat.

Una solicitud muestra etapa real, segundos transcurridos y actividad tanto en chat
como sobre el documento. A los 25 segundos cambia la ayuda, sin inventar porcentaje
ni plazo. Puede seguir leyéndose la versión anterior mientras se prepara otra.
El desplazamiento del chat respeta al usuario que está leyendo arriba y ofrece
«Nuevos mensajes» para volver al final.

La publicación avisa exactamente qué cambió: gráficos añadidos, actualizados o
retirados; cuando corresponde, título o análisis. El aviso incluye versión y
«Ver cambios», y el informe ofrece «Ir a los gráficos» y «Leer análisis». El puente
de foco marca bloques nuevos/modificados con «Actualizado» y desplaza al destino
dentro del iframe aislado; no da acceso al origen ni a la red. No se intercambian
HTML, URLs ni credenciales mediante ese puente.
La política de hashes del documento se conserva y un nonce efímero autoriza el
script del puente. El padre habilita la navegación tras la confirmación del DOM
del iframe, validando la ventana emisora y el token vigente.

Los errores muestran recuperación comprensible y conservan el documento ya visible;
el código técnico queda desplegable. Los reintentos diferencian repetir la solicitud
de completar una narración fallida. Una lectura `partial` sin issues, con gráficos
completos, conserva su respuesta deportiva validada y la advertencia de alcance;
no se etiqueta como análisis exhaustivo ni se sustituye por una confirmación genérica.

La conversación ofrece orientación, explica xG o Voronoi sin obligar a generar una
página y plantea como máximo una pregunta cuando necesita aclarar. El catálogo
mantiene una introducción útil y muestra ejemplos por nombres, sin IDs en esa
respuesta; la selección completa sigue disponible en Partido.

Tras analizar, la respuesta breve reutiliza las primeras afirmaciones deportivas
ya contrastadas de una sección analítica útil. Al resumir facts íntegramente
sintéticos lo declara al principio. El informe ordena la lectura en apartados,
priorizando «Lo más importante» o una conclusión deportiva específica. La prosa
no repite etiquetas de tipo de afirmación, aunque se conservan kind, facts y citas.
Procedencia y primera limitación permanecen visibles; el resto del alcance y
«Fuentes y referencias» se despliegan bajo demanda, sin eliminar la evidencia.

La identidad permanece monocroma y plana; los colores de los gráficos pertenecen
al informe. Se usan respuesta breve al pulsar, transición de posición al mover chat,
spinner y foco de destino. El modo de movimiento reducido elimina rotación,
desplazamiento animado y escala al pulsar. DESIGN.md y su sidecar recogen los
valores efectivos, incluidos los ajustes responsivos que sustituyen anchos antiguos.

La QA de esta iteración comprobó siete solicitudes conversacionales y una creación
completa de 35,22 s, seguida de una edición que conservó sus dos bloques. Se
conserva el antecedente `real11ready` de 93,45 s y análisis parcial; no se afirma
que la latencia anterior haya quedado corregida para todas las solicitudes.
