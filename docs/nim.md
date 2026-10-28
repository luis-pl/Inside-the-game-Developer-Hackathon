# Modelo en la nube con NVIDIA NIM

Proveedor opcional que usa el endpoint gratuito de NVIDIA NIM
(build.nvidia.com), compatible con Chat Completions. Se selecciona sólo de forma
explícita con `INSIDE_GAME_MODEL_PROVIDER=nim`; no reemplaza a Beam Free ni actúa
como fallback de otro proveedor.

El destino es fijo: `https://integrate.api.nvidia.com/v1`. No se usan los
endpoints de socios (Baseten, CoreWeave, Deep Infra…), que son de pago. El
cliente reutiliza el adaptador `AzureChatModel`: historial de llamadas,
expansión de `$ref`, un reintento ante 429/5xx y códigos de error públicos.

## Cuenta y clave

1. Crear una cuenta del NVIDIA Developer Program en build.nvidia.com (gratis,
   sin tarjeta) y aceptar sus condiciones. El endpoint gratuito es para
   desarrollo y prototipos; el uso queda registrado. No enviar datos personales:
   los datos de este proyecto son sintéticos o anonimizados.
2. Elegir un modelo con **Free Endpoint: Available** y **Function Calling:
   Supported**. No usar GPT-OSS (descartado por el titular, ver AGENTS.md).
3. Generar la clave (`nvapi-…`) y guardarla sólo en `.env.local`, ignorado por Git:

```text
INSIDE_GAME_NIM_API_KEY=nvapi-...
```

## Configuración

```text
INSIDE_GAME_MODEL_PROVIDER=nim
# Opcionales; estos son los valores por defecto:
# INSIDE_GAME_NIM_MODEL=nvidia/nemotron-3-ultra-550b-a55b
# INSIDE_GAME_NIM_THINKING=0   # 1 activa el razonamiento del modelo
# INSIDE_GAME_NIM_TIMEOUT=120
```

`INSIDE_GAME_NIM_THINKING` se envía como `chat_template_kwargs.enable_thinking`.
Sin razonamiento las respuestas son más rápidas; con él, el modelo piensa antes
de cada llamada.

## Límites

Las fuentes consultadas (foros de NVIDIA y guías de terceros, no una página
oficial de precios) sitúan el nivel gratuito en unas 40 peticiones por minuto,
según modelo y carga. Comprobar el límite propio en el panel de build.nvidia.com.
El adaptador reintenta una vez ante HTTP 429 respetando `retry-after`.

## Prueba inicial

Con `nvidia/nemotron-3-ultra-550b-a55b` (561B parámetros, 55B activos, contexto 1M)
y dos herramientas simplificadas, las tres preguntas de prueba eligieron la
herramienta y los argumentos correctos: 5,5 s en total sin razonamiento y 9,0 s
con él. Esta prueba no ejecuta el MCP ni equivale a una evaluación del corpus.
