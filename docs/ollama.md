# Modelo local con Ollama

Proveedor opcional para ejecutar los agentes con un modelo en un equipo propio,
sin claves de pago ni cuotas externas. Se selecciona sólo de manera explícita con
`INSIDE_GAME_MODEL_PROVIDER=ollama`; no sustituye a Beam Free como modelo
predeterminado ni actúa como fallback de otro proveedor.

El cliente usa la API compatible con Chat Completions de Ollama y reutiliza el
adaptador de `AzureChatModel`: historial de llamadas, expansión de `$ref`, un
reintento ante 429/5xx y códigos de error públicos. No envía cabeceras de
autenticación ni `reasoning_effort`.

## Equipo verificado

Prueba del 26 de octubre de 2026 en Windows 11, Ollama 0.40.10:

| Componente | Valor |
|---|---|
| CPU | Intel Core i7-14700 (20 núcleos) |
| RAM | 32 GB DDR5-6000 |
| GPU | NVIDIA RTX 4060 Ti, 8 GB |
| Modelo | `qwen3:30b-a3b-instruct-2507-q4_K_M` (MoE, ~3B activos, sin razonamiento) |

El modelo ocupa 21 GB con contexto de 40.960 tokens: unos 6,7 GB en la GPU y el
resto en RAM (70 % CPU / 30 % GPU). Con el modelo cargado quedaron unos 8 GB de
RAM libres. Generación: 35–39 tokens/s.

## Configuración del servidor Ollama

El prompt del agente de datos y los esquemas de sus 34 herramientas ocupan unos
16.600 tokens por turno, antes de añadir resultados. Con 16.384 tokens de
contexto, Ollama rechazó la petición con HTTP 400. La API compatible
no permite elegir el contexto por petición: se configura en el servidor.

Variables de usuario de Windows (reiniciar Ollama después, cerrándolo desde la
bandeja del sistema):

```powershell
setx OLLAMA_CONTEXT_LENGTH 40960
setx OLLAMA_KEEP_ALIVE 24h
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
```

Comprobar con `ollama ps` que la columna CONTEXT muestra 40960. Si una
conversación larga supera el contexto, subirlo a 49152 cuesta unos 0,4 GB más.

## Configuración del proyecto

En `.env.local`:

```text
INSIDE_GAME_MODEL_PROVIDER=ollama
# Opcionales; estos son los valores por defecto:
# INSIDE_GAME_OLLAMA_URL=http://127.0.0.1:11434/v1
# INSIDE_GAME_OLLAMA_MODEL=qwen3:30b-a3b-instruct-2507-q4_K_M
# INSIDE_GAME_OLLAMA_TIMEOUT=300
```

El modelo debe estar descargado antes (`ollama pull <modelo>`); el cliente no
descarga modelos ni modifica la configuración de Ollama.

`INSIDE_GAME_OLLAMA_URL` sólo acepta este equipo, direcciones privadas de la red
local o direcciones Tailscale (100.64.0.0/10), sin credenciales ni parámetros.
Ollama no tiene autenticación: no publicar el puerto 11434 en Internet. Para que
otro miembro del equipo use el modelo, conectar ambos equipos por Tailscale,
iniciar Ollama con `OLLAMA_HOST=0.0.0.0:11434` y limitar el firewall a esa red.

## Resultados

Una llamada al modelo por pregunta, con el prompt y las 34 herramientas reales
del agente de datos, sin ejecutar el MCP:

| Pregunta | Llamada propuesta | Tiempo |
|---|---|---|
| Tiros a puerta del equipo 1 en 900001 | `get_match_context` (paso previo del prompt) | 33,0 s |
| Mapa de calor del jugador 15 en 900002 | `get_heatmap` con partido, jugador y rejilla | 2,5 s |
| Goles del equipo 2 en 900001 | `get_events` con `event_types=[3]` | 1,6 s |

La tercera llamada es incorrecta: el tipo 3 no corresponde a tiros y el prompt
indica `get_shots`. Esta prueba no equivale a la evaluación del corpus completo;
queda pendiente `scripts/verify_data_agent.py` con este proveedor y el MCP real.

## Tiempos y límites

- La primera petición tras arrancar carga el modelo (unos 48 s) y procesa el
  prompt completo (unos 60 s a ~310 tokens/s). Las siguientes reutilizan el
  prefijo en caché de Ollama y tardan unos 2 s. Calentar el modelo con una
  pregunta antes de una demostración.
- Ollama conserva en caché un único prefijo con la configuración por defecto.
  Alternar entre agentes con prompts distintos (datos e insights) puede obligar
  a procesar de nuevo los ~16.600 tokens: unos 30–60 s.
- El planificador de insights limita cada ejecución a 40 s y la página a 55 s.
  Con el modelo frío esos límites pueden agotarse; con el modelo caliente no.
- En la primera petición tras arrancar se observó una vez
  `CUDA error: unknown error` (HTTP 500). El reintento del adaptador lo cubre;
  no se repitió en las peticiones siguientes.
