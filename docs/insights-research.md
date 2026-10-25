# Diez extensiones investigadas e implementadas

Fecha de revisión: 24 de octubre de 2026. Las veinte familias anteriores quedan
aprobadas. El registro ejecutable de treinta está en
`src/inside_game/insights/catalog.json`; la propuesta inicial se conserva como
referencia de diseño, no como estado de implementación.

FIFA documentó once métricas EFI para Qatar 2022. Se seleccionaron seis conceptos
que complementan el catálogo existente y se añadieron cuatro extensiones de
investigación/topología. Las implementaciones locales declaran sus diferencias;
no se atribuye a FIFA la validación de nuestros algoritmos o datos.
[Anuncio oficial](https://inside.fifa.com/innovation/media-releases/fifa-to-introduce-enhanced-football-intelligence-at-fifa-world-cup-2022-tm).

| # | Familia | Referencia primaria | Implementación y diferencia explícita |
|---|---|---|---|
| 21 | Altura de la línea defensiva | [FIFA EFI](https://www.fifatrainingcentre.com/en/fwc2022/efi-metrics/efi-metric--defensive-line-height-and-team-length.php) | Mínimo longitudinal de defensores declarados y longitud observada del equipo sin portero; snapshot, sin agregaciones oficiales por fase |
| 22 | Conexión portero-defensa | [Análisis de Qatar 2022](https://www.fifatrainingcentre.com/en/fwc2022/technical-and-tactical-analysis/goalkeeper-height-and-connection-with-the-defensive-line.php) | Altura del portero y separación longitudinal con la línea declarada; requiere identidades y dirección |
| 23 | Entradas al último tercio por carril | [FIFA EFI](https://www.fifatrainingcentre.com/en/fwc2022/efi-metrics/efi-metric--final-third-entries.php) | Cruces de acciones anotadas hacia el tercio ofensivo; cinco carriles iguales según llegada. No reconstruye todas las entradas FIFA |
| 24 | Recepciones entre líneas | [FIFA EFI](https://www.fifatrainingcentre.com/en/fwc2022/efi-metrics/efi-metric--receptions-behind-midfield-and-defensive-lines.php) | Posición final del pase frente a grupos rivales explícitos, usando snapshot cercano al tiempo de llegada; sin inferir roles funcionales |
| 25 | Tiempo de recuperación observado | [FIFA EFI](https://www.fifatrainingcentre.com/en/fwc2022/efi-metrics/efi-metric--ball-recovery-time.php) | Proxy entre eventos seleccionados de control del equipo, pasando por control rival. Se reinicia por período; no es posesión temporal exacta |
| 26 | Recuperaciones precedidas por presión | [FIFA EFI](https://www.fifatrainingcentre.com/en/fwc2022/efi-metrics/efi-metric--forced-turnovers.php) | Secuencia local presión → pérdida anotada rival → recuperación anotada, dentro de ventana configurable. Deduplicada por recuperación; no certifica causalidad ni equivalencia a forced turnovers FIFA |
| 27 | Ventaja estructural del pase | [Karakuş et al., preprint v3, 14 octubre 2026](https://arxiv.org/abs/2603.28916v3) | LBS y SGM sobre posiciones observadas de pasador, receptor y rivales al inicio. Alineación con tolerancia explícita; no reproduce SDI, TIV, estandarización ni clustering entrenado |
| 28 | Descomposición Hodge del flujo de pases | [Jiang et al.](https://arxiv.org/abs/0811.1067), [Chacoma et al., preprint junio 2026](https://arxiv.org/abs/2606.21814) | Port de la descomposición de pases existente en el frontend: flujo neto no ponderado, complejos graph/clique, gradiente/curl/armónico. El paper reciente analiza redes entre equipos; nuestra adaptación es entre jugadores y no reproduce su ranking |
| 29 | Cambio temporal topológico | [GUDHI: bottleneck distance](https://gudhi.inria.fr/python/latest/bottleneck_distance_user.html) | Distancia bottleneck H1 entre snapshots comparables; corta ante cambios de identidades, períodos, huecos o censura. Es extensión del método Rips existente, no una métrica aplicada oficialmente por FIFA |
| 30 | Anchura de conexión libre desde el balón | Implementación existente `frontend/src/domain/clearance-network.ts` y `corridors.ts` | Port local de grafo Gabriel, separación de segmentos respecto a defensores y límites del campo, y caminos maximin por bosque de expansión máxima. No es probabilidad de pase ni simulación dinámica |

## Revisión matemática y del código existente

- Hodge conserva la orientación canónica por IDs y el soporte de pares equilibrados.
  El flujo cero tiene fracciones indefinidas, no porcentajes cero inventados.
  Las pruebas distinguen el ciclo triangular como curl en clique y armónico en graph,
  comprueban reconstrucción, ortogonalidad y conservación de energía.
- Persistencia reutiliza `inside_game.tools.topology.persistence`: Rips, F2, H0/H1,
  corte de distancia 40 m. Para comparar H1 se excluyen diagramas censurados; no se
  convierten muertes desconocidas en 40 m. Se informa cuántos pares son comparables.
- Corredores conservan el límite del campo y defensores puntuales. Una posición de
  balón coincidente con jugador se trata como identidad espacial compartida. Los
  tests verifican radio y anchura completa; un cuello de botella es un radio,
  su anchura completa es el doble.
- LBS compara los rivales más cerca de la portería por coordenada longitudinal,
  no una formación reconstruida. SGM usa distancia al rival más cercano del receptor
  dividida entre el máximo de 1,5 m y la distancia del pasador. Los dos participantes
  se toman del tracking de inicio, no del destino futuro del balón.
- Las fuentes de Metrica/SkillCorner actuales no tienen todos los roles ni la presión
  requeridos por las seis familias EFI. La disponibilidad se verifica por bloque;
  no se rellenan esas anotaciones para hacer funcionar una visualización.

No se entrenaron ni descargaron modelos, ni se adquirieron datos o servicios.
Las fuentes respaldan los conceptos; el comportamiento de nuestras adaptaciones
se verifica mediante casos controlados y datos originales del agente.

## Fuera de alcance científico

No se implementó pitch control probabilístico, xG real, predicción de intercepción,
TIV entrenado, clasificación completa de fases FIFA ni un score de impenetrabilidad.
No hay datos de partidos del Mundial cargados por esta tarea: el Mundial es la
referencia metodológica, no la procedencia de nuestros ejemplos.
