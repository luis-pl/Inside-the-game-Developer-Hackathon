# Inside the game
<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Equipo y jurado de una hackathon de analítica de fútbol. El usuario solicita
informes y modificaciones en lenguaje natural y explora los resultados.

## Product Purpose
Convertir una pregunta sobre partidos en una página autocontenida con gráficos,
análisis textual, referencias y límites de la evidencia.

## Operating Context
Cuatro agentes: intérprete de cara al usuario, Data, analista e Insights. El usuario
pidió conversaciones a la izquierda, documento central y chat a la derecha,
similar a su forma de trabajar con ChatGPT y Visual Studio.

## Capabilities and Constraints
Catálogo controlado de consultas SQL y herramientas MCP. Origen sintético y real
siempre explícito; geometría no equivale a probabilidades o juicios tácticos.
Modelo Beam Free con precios cero verificados; sin habilitar consumo de pago.
La demo local conserva conversaciones en memoria una hora; los HTML descargados
son portables. No se afirma persistencia después de reiniciar el servidor.

## Brand Commitments
Inside the game. El usuario solicitó modos negro y blanco. Los informes y sus
colores por equipo ya fueron aprobados; conservarlos dentro del documento.

## Evidence on Hand
Base Azure SQL documentada en database/azure-sql. Cinco ejecuciones del flujo en
.temp/insights/five-flow-examples. Frontend React existente con visor topológico.
