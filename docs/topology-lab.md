# Topology Lab

Dashboard local del hackathon. Consume las operaciones de lectura de la API existente; no accede directamente a SQL ni requiere un modelo de IA.

## Arranque (Windows)

Requisitos: Node.js 26.12.1 o 24.22.1 y Python 3.12+. Desde la raíz:

```powershell
.\scripts\start-dashboard.ps1
```

Abre `http://127.0.0.1:8080`. El launcher instala dependencias si faltan, compila el frontend y sirve la aplicación. Para actualizar dependencias de una instalación previa, usa `cd frontend; npm ci`. Para desarrollo: inicia el servidor Python y, en otra terminal, `cd frontend; npm run dev` (proxy de Vite al puerto 8080).

## Credenciales

En `.env` o `.env.local` (ignorados por Git):

```dotenv
INSIDE_GAME_API_URL=https://<host-del-servicio>
INSIDE_GAME_API_KEY=<clave-bearer-individual>
```

El adaptador también reconoce `INSIDE_GAME_MCP_API_URL` y deriva el origen de `INSIDE_GAME_DATA_MCP_URL`. Las variables del proceso tienen prioridad. No uses prefijo `VITE_` para secretos. Los archivos se vuelven a leer al consultar: añadir o rotar una clave no requiere reiniciar. El frontend no conoce la URL remota ni la clave. Un 401 se muestra como error; no se sustituye silenciosamente por un partido inventado.

El botón «Abrir laboratorio local» carga una geometría pedagógica explícita, no registros de Azure. La fuente permanece visible en la cancha.

## Arquitectura

- `frontend/src/domain`: funciones puras de conectividad, persistencia y espacio libre; sin React ni HTTP.
- `frontend/src/data`: adaptador del contrato `EpisodeRepository` y escenario local separado.
- `frontend/src/hooks`: coordinación de carga, cancelación, playback y estado de análisis.
- `frontend/src/components`: cancha, controles y barcode de persistencia.
- `src/inside_game/dashboard/config.py`: configuración privada del servidor.
- `gateway.py`: interfaz `Operations`, adaptador HTTP y servicio que normaliza el contrato de datos.
- `server.py`: adaptador HTTP local y raíz de composición; permite sólo rutas fijas.

Se aplica inversión de dependencias mediante `EpisodeRepository` y `Operations`. Los cálculos se componen sin herencia ni patrones que no aporten una responsabilidad real. No se modifican las APIs, MCP, agentes ni contratos existentes.

## Definiciones y límites

- Tracking: hasta 5 min dentro de un período, 22 jugadores activos válidos, una muestra original cada 1 s sin interpolación. Se unen consultas de hasta 120 s. Reloj local al período. El run y la dirección proceden del contexto.
- H0/H1: complejo de Vietoris–Rips hasta dimensión 2, coeficientes F2, filtración por longitud de arista y corte a 40 m. Reducción exacta de fronteras; las barras no muertas al corte se muestran censuradas. Se omiten barras de persistencia cero. H1 no equivale a ciclos del grafo sin triángulos. No se calculan cociclos representativos; las dimensiones son las de (co)homología sobre F2.
- Espacio libre: complemento de discos de radio r, discretización de 1 m y cuatro vecinos, sin conexión fuera del rectángulo. Sus regiones son componentes H0 de esa aproximación; no son el H1 de Rips. La malla puede omitir corredores submétricos.
- Ruta: BFS desde el nodo más próximo al balón a x≤5 o x≥100, 24≤y≤44. Si el inicio está cubierto no hay ruta. Se dibuja un camino geométrico; no predice una conducción o un pase ejecutable.
- ε (conectividad) y r (discos) son independientes. Porteros incluidos en discos, excluidos del grafo. «Equipo analizado» es una selección del usuario: no se afirma que defienda en todos los frames.
- Retirada: quitar un nodo y recalcular sin mover los demás. Δ componentes y ranking se calculan contra el baseline completo, no contra una retirada previa.
- Se conservan advertencias upstream; si falla la consulta de eventos se indica que faltan. Sin causalidad, score calibrado o probabilidades de control.

## Pruebas

```powershell
cd frontend
npm test
npm run build
cd ..
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p 'test_dashboard_unit.py' -v
```

Las pruebas matemáticas cubren un cuadrado con H1, un triángulo relleno sin H1, invariancia por traslación/permutación, censura a 40 m, retirada de un puente y conectividad del espacio libre con/sin una barrera completa. Las de servidor cubren configuración, límites, whitelist y cobertura.

El servidor está diseñado para uso local y se enlaza exclusivamente a loopback. Un despliegue público necesita autenticación de usuarios, rate limiting compartido y un servidor de producción; no publicar este servidor local con un túnel.

## Descomposición de Hodge de la red de pases

La sección 05 añade potencial, circulación local y componente armónica. Se calculan sobre los pases completados atribuibles al equipo seleccionado en **toda la ventana cargada**, no sólo hasta el instante de reproducción. Cambiar el frame cambia la posición dibujada de los nodos, pero no agrega ni elimina pases de la ventana. El botón de cada componente y el selector «Hodge en cancha» controlan la misma capa.

### Complejo y producto interno

- Cada pareja con al menos un pase completado forma una arista; su orientación es del ID menor al mayor. Los pares equilibrados mantienen la arista aunque su flujo neto sea cero.
- El flujo es `f_ij = N(i→j) - N(j→i)`, sin pesos adicionales. Una arista puede contener pases de ambos sentidos; el flujo neto pierde deliberadamente esa información, mientras que el contador conserva el total.
- «Triángulos rellenos»: 2-esqueleto del complejo de cliques de interacciones observadas. No se exige una secuencia temporal A→B→C→A. «Sólo grafo»: no hay 2-símplices, de modo que la componente local es cero.
- Con `B1` (nodos × aristas) y `B2` (aristas × triángulos), se tiene `B1 B2 = 0`. La descomposición ortogonal real es `f = B1^T φ + B2 ψ + h`, con `B1 h = 0` y `B2^T h = 0`.
- Se proyecta sobre bases ortonormales mediante Gram–Schmidt modificado con reortogonalización; no se invierten Laplacianos singulares. Se publican residuos relativos de reconstrucción, ortogonalidad, divergencia y rotación. La tolerancia es `1e-8`; un resultado fuera de ella no se dibuja.
- La dimensión armónica es `m - rank(B1) - rank(B2)`, igual a la dimensión de `H^1(K; R)` del complejo de pases. No se identifica con el H1 espacial de Rips sobre F2.

Los porcentajes son fracciones de energía cuadrática, no porcentajes de posesión, avance o rendimiento. Si el flujo neto es cero no se calculan porcentajes. El gradiente no equivale a jugar hacia delante y la circulación no implica ineficacia.

### Integración y cobertura

El servidor consulta `get_passes` con `outcome=complete`, conserva IDs y comprueba pertenencia al equipo. Se recorren cursores firmados hasta un máximo de 1000 pases. Una consulta incompleta, fallida o con paginación repetida devuelve Hodge no disponible; nunca se calcula sobre un truncamiento silencioso. Las omisiones por identidades no atribuibles generan una advertencia explícita.

Se incluyen porteros que participen en los pases. Los nodos sin posición en el frame actual siguen en el cálculo, pero sus flechas no se dibujan. Retirar un jugador excluye sus pases del modelo y se identifica como una perturbación, no una predicción de sustitución.

### Código y pruebas

- `frontend/src/domain/hodge`: construcción del complejo, álgebra lineal y descomposición, sin dependencias de React o HTTP.
- `HodgePanel` y `HodgeOverlay`: presentación y flechas sobre la cancha.
- Las pruebas cubren árboles, triángulo relleno/sin rellenar, cuadrado sin diagonales, tetraedro con fronteras dependientes, energía nula, cambio de orientación, reconstrucción y mezcla con tres componentes no nulas.
- Las pruebas del adaptador cubren paginación, identidades omitidas, pases incompletos y ausencia de datos diferenciada de flujo cero.

Referencia matemática: Jiang, Lim, Yao y Ye, [Statistical ranking and combinatorial Hodge theory](https://arxiv.org/abs/0811.1067). La aplicación a circulación futbolística es una interpretación exploratoria sobre datos sintéticos.

## Lectura visual y aperturas

La vista inicial prioriza la cancha y usa una leyenda común: verde para el bloque analizado, ámbar para el rival, blanco para el balón y amarillo para la zona objetivo. Los detalles H0/H1 siguen disponibles en un desplegable, sin ocupar la vista inicial. Las tres vistas separan aperturas, conectividad y circulación; las selecciones de Hodge también activan la vista de circulación.

Las aperturas A1–A3 son **círculos libres de cobertura**, no agujeros de Rips ni oportunidades de gol estimadas. Se consideran centros de circunferencias vacías definidas por triples no colineales de jugadores de campo, dentro de su envolvente convexa. Se verifica que ningún jugador del bloque (incluido el portero) esté más cerca. El radio mostrado es el mínimo entre distancia al defensor menos radio de cobertura y distancia a las cuatro fronteras del campo. Por desigualdad triangular, el disco no invade ninguna cobertura modelada. Se exige radio libre ≥1 m y se priorizan hasta tres candidatos grandes con supresión de solapamiento; no es un censo exhaustivo de espacios.

Las tarjetas muestran el diámetro y si el centro pertenece a la misma componente del espacio libre que el balón, sobre la malla de cuatro vecinos de 1 m. La conexión puede no existir aunque el círculo sea grande. No se confunde ese acceso con un pase ejecutable. Seleccionar una tarjeta resalta su círculo y actualiza la explicación. Los IDs A1–A3 se asignan de nuevo en cada muestra; no son identidades persistentes en el tiempo.

La serie temporal muestra el mayor diámetro detectado en cada frame con los parámetros y la retirada actuales. «Ir a la mayor apertura» pausa la reproducción, selecciona el máximo de la ventana, activa la vista de aperturas y desplaza la página a la cancha. No busca fuera del episodio ni mezcla períodos. Las barras también pueden mostrar grupos de conectividad. La narración accesible se anuncia al pausar; no se emite continuamente durante la reproducción.

Las pruebas de aperturas cubren círculo central en un cuadrado, cobertura que cierra el espacio, puntos colineales, portero que invalida el candidato, ausencia de conexión cuando el balón está cubierto y límites del campo. Los cálculos permanecen en el dominio, separados de la presentación React.

## Pantalla de partido y red automática (actualización)

La vista inicial es la cancha, reloj, dos señales numéricas y reproducción. No
incluye tarjetas explicativas ni ajustes de distancia. Configuración, evolución,
método, persistencia y Hodge están en desplegables debajo. El indicador dice
«reproduciendo», no «en directo»: son ventanas sintéticas de hasta 5 min, con una muestra original cada 1 s.

### Conectividad sin escala elegida por el usuario

`corridors.ts` calcula adyacencia de Gabriel sobre todas las posiciones de
jugadores y balón: el disco abierto de diámetro AB debe estar vacío. Se conserva
la red inducida por balón y atacantes. Los defensas bloquean candidatos; no son
nodos de enlace. Las coincidencias de balón y atacante se identifican. Una
defensa coincidente con el balón impide corredores de anchura positiva.

La holgura de una arista es la distancia mínima exacta de todos los defensas al
segmento, también limitada por las bandas (incluidas sus tapas). Dos veces la
holgura mide la anchura del corredor vacío. No se fija epsilon ni radio defensivo.
Se usan tolerancias numéricas para coincidencias, no umbrales deportivos.

`clearance-network.ts` ordena aristas por holgura descendente. Kruskal registra
las fusiones H0 de esta filtración de supernivel y produce un bosque máximo que
preserva caminos de máximo cuello de botella. Es topología de un grafo ponderado;
no se afirma que sea la homología del complemento continuo de los defensas.

`tactics.ts` combina el grafo con círculos vacíos de tres defensas (vértices de
Voronoi interiores), recortados por el campo y comprobados contra el portero.
No resta radios de control. Mantiene hasta tres candidatos separados de radio
al menos 1 m como filtro de presentación. Un círculo es un destino terminal,
nunca un intermediario ficticio. Se conecta a nodos alcanzables mediante el mismo
criterio de Gabriel y se maximiza la holgura mínima de la cadena completa.
La pantalla muestra sólo un círculo: primero alcanzable en esta red, luego de
mayor holgura, mayor avance y mayor radio. Si no hay conexión al círculo, puede
mostrar una cadena a un compañero, distinguida de la zona amarilla.

La red no depende del diámetro para conectar jugadores ni de la escala del
diagnóstico Rips. La persistencia Rips H1 a todas las escalas hasta 40 m y la
cohomología real de Hodge de pases históricos permanecen separadas, debajo.

### Interpretación

Defensas puntuales, sin velocidad, radio de control ni tiempo de reacción.
«Libre» describe geometría instantánea, no probabilidad de pase ni de gol.
Ausencia de conexión Gabriel no demuestra ausencia de pase real. No se infiere
posesión: el usuario identifica qué equipo se considera defensor y se muestra
esa elección en la cabecera. No se interpolan muestras para inventar posiciones.

### Verificación

Pruebas de segmento y bandas, bloqueo por defensa, enlace mediante compañero,
conservación de conectividad a todos los niveles críticos del bosque, balón
ausente/coincidente y reflexión geométrica. Comprobación independiente por BFS de
todas las anchuras críticas en 120 redes (60 muestras Azure × 2 equipos), y
validación geométrica de corredores a los círculos. La compilación TypeScript y
las pruebas anteriores se mantienen.



## Reproducción larga y memoria del navegador

Cada carga obtiene hasta 300 segundos de datos mediante tramos disjuntos de 120, 120 y 60 segundos, con stride_s=1. Se valida toda la cronología antes de entregar el episodio. Eventos y pases cubren el intervalo completo. Cerca del descanso, se recorta al fin del período.

El frontend conserva hasta seis episodios completos en una caché LRU en memoria durante la sesión. Volver a cargar la misma ventana reutiliza el objeto; recargar la página vacía la memoria. Los fallos y las cancelaciones no se almacenan. Reproducir, mover el reloj, cambiar el equipo, calcular topología y Hodge no requieren más consultas.

El reloj avanza continuamente según el tiempo real transcurrido y la velocidad seleccionada, con dibujo a unos 30 fps. La interpolación lineal sólo afecta a la representación de jugadores y balón entre muestras contiguas de 1 s; los análisis usan observaciones originales. No se interpolan huecos, identidades ausentes ni transiciones de balón detenido. La barra permite buscar tiempos fraccionarios. Velocidades 0.5×, 1×, 2× (inicial), 4× y 8×. Una ventana 10:00–15:00 contiene 300 muestras originales hasta 14:59.



El rótulo central ESPACIO LIBRE se retiró para no ocultar jugadores. Se mantiene únicamente un contorno y relleno tenue; la medida se lee fuera de la cancha. Auditoría del episodio Azure 900001, 10:00–15:00: 300 timestamps a 1 Hz, 300 posiciones distintas del balón; desplazamiento medio de 5.62 m y máximo de 19.13 m por segundo.


## Nodos atacantes visibles y selección automática

La vista principal muestra todas las aristas Gabriel, no sólo una cadena destacada. Verde continuo y aros verdes: componente del balón; trazos grises discontinuos: aristas y atacantes separados del balón. Los enlaces directos tienen mayor grosor. El contador muestra atacantes enlazados / atacantes presentes y vecinos directos del balón. La cadena hacia el espacio destacado es amarilla. Los extremos de aristas y aros se proyectan por identidad a las posiciones animadas; la identidad espacial de los nodos se conserva.

Por defecto se estima el equipo atacante mediante el jugador más cercano al balón en cada muestra original; se mantiene la estimación anterior cuando falta el balón, está detenido o hay empate entre equipos. La cabecera lo identifica como ATAQUE ESTIMADO. No es posesión observada ni una prueba de control. La configuración permite fijar manualmente la defensa; las simulaciones de retirada fijan el equipo para hacer una comparación coherente. Los colores menta y ámbar quedan ligados a los equipos del episodio y no cambian con el rol.

Pruebas nuevas: redes separadas visibles, balón y jugador coincidentes, conservación de IDs durante animación, cambio de equipo, empates, detenciones y ausencia de balón. Validación sobre las 300 muestras Azure de la ventana.


## Tiempo completo y ritmo de resumen (actualización vigente)

El acceso principal carga un período completo de Azure desde 00:00: hasta 45 minutos y 2700 muestras originales a 1 Hz. La configuración permite 15, 30 o 45 minutos y conserva la elección de período e inicio. El ejemplo geométrico local de una sola jugada queda en la configuración, identificado explícitamente; no es el acceso principal al partido.

La carga divide tracking en tramos de hasta 120 s y pagina todas las acciones (hasta 4000) y los pases completados, sin limitar los eventos a la primera página de 200. La caché en memoria distingue partido, período, inicio y duración. Auditoría de Azure 900001, primer tiempo: 2700 muestras de 00:00 a 44:59, 1219 eventos, 283 pases registrados, 267 completados, 13 tiros y acciones en los 45 minutos.

1× del resumen equivale a 8 segundos de partido por segundo de pantalla, según la preferencia solicitada. Se identifica en el control y pie de cancha; no se presenta como tiempo real. Un período completo se recorre en unos 5 min 37 s. Las opciones 0.5×, 2×, 4× y 8× son múltiplos de ese ritmo base. La interpolación visual mantiene los datos fuente intactos. Próxima acción salta a un evento registrado y reinicia correctamente el reloj de reproducción, incluso mientras se reproduce.

Las cifras de muestras, acciones, pases y tiros son visibles en la pantalla. Los paneles de gráficos se montan sólo al abrirlos, para que miles de barras no se rendericen mientras se ve el partido.


## Escala temporal vigente: tiempo real

Por indicación posterior del usuario, se elimina la base acelerada de resumen. La velocidad inicial 1× significa exactamente 1 segundo de partido por segundo de pantalla; 0.5×, 2×, 4× y 8× son múltiplos literales del tiempo real. El reloj aplica sólo elapsedMs × speed, sin factores ocultos. Se conservan la carga del tiempo completo de 45 minutos, las 2700 muestras originales, todas las acciones y la navegación Próxima acción. La indicación anterior 1× = 8 s/s queda sustituida por esta definición.

