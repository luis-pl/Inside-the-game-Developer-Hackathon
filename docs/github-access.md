# Credenciales de API y MCP en GitHub

Destino: repositorio privado
`luis-pl/Inside-the-game-Developer-Hackathon`, en
Settings → Secrets and variables → Actions.

**Estado:** carga autorizada y completada. Se verificaron los dos secretos
cifrados y las tres variables en GitHub mediante su API, sin mostrar las claves.

| Tipo | Nombre | Contenido |
|---|---|---|
| Repository secret | `INSIDE_GAME_API_KEY` | Clave `team-collaborator-01`, rol `developer` |
| Repository secret | `INSIDE_GAME_DATA_MCP_KEY` | Clave `agent-data`, rol `agent` |
| Repository variable | `INSIDE_GAME_API_URL` | Origen HTTPS publicado en `deployment/cloud.json` |
| Repository variable | `INSIDE_GAME_MCP_API_URL` | Mismo origen de la API, para el puente MCP |
| Repository variable | `INSIDE_GAME_DATA_MCP_URL` | Origen HTTPS seguido de `/mcp` |

Las claves se validaron contra `/api/whoami` y caducan el
6 de noviembre de 2026 a las 14:28:18 de Colombia. Las consultas conservarán
la identidad de la clave utilizada. Los datos de la demo son sintéticos.

Además se probó una consulta `get_shots` por API con la clave de desarrollo,
el listado de las 34 herramientas MCP con la clave del agente y la misma
consulta por MCP. Ambas consultas devolvieron los seis tiros a puerta esperados
del equipo 1 en el partido sintético 900001. Evidencia:
[`github-access-verification.json`](github-access-verification.json).
No se ejecutó un workflow de Actions: estas pruebas verifican las credenciales
originales contra Azure y la carga en GitHub, sin probar su inyección en un runner.

## Desarrollo en los equipos locales

Se prepararon dos archivos privados fuera del repositorio: `.env.development.local`
para el titular `team-collaborator-01` y `.env.agent.local` para el servicio
`agent-data`. Cada archivo tiene las URLs y sólo la clave individual de su titular,
asignada a las variables de API y MCP porque ambos transportes aceptan esa identidad.
Entregar cada archivo únicamente a su titular por un canal privado. Para nuevos
compañeros, emitir credenciales individuales siguiendo [azure-demo.md](azure-demo.md).

Los valores `INSIDE_GAME_API_KEY` e `INSIDE_GAME_DATA_MCP_KEY` contienen la clave
cruda. El prefijo `Bearer ` se añade al construir la cabecera:

```python
headers = {"Authorization": "Bearer " + key}
```

Si una herramienta pide **Bearer token**, pegar sólo la clave. Si pide una
cabecera HTTP completa, configurar `Authorization` con `Bearer ` seguido de la
clave. No hace falta un token distinto.

Instalar sólo los clientes en Python 3.12 o superior:

```powershell
python -m pip install "mcp>=2.3,<2.4" "httpx>=0.28,<1" "httpx2>=2.16,<3"
python scripts/check_service_access.py --env-file "RUTA_PRIVADA/.env.development.local"
```

Para probar el archivo del agente, sustituir la ruta por `.env.agent.local`.
El script lee asignaciones del archivo sin ejecutar su contenido y prueba una
consulta por API y MCP sin imprimir claves. La plantilla pública
[`client.env.example`](client.env.example) contiene únicamente marcadores.
Si ya existe un `.env.local`, conservarlo y pasar el archivo privado por su ruta;
no sobrescribir la configuración existente. Los procesos ajenos a este script
deben cargar explícitamente su archivo de entorno o inyectar esas variables.

Se probaron ambos archivos privados con ese script: autenticación y consulta API,
listado de 34 herramientas MCP y consulta MCP correctos para cada titular. En los
dos transportes se obtuvieron los seis tiros a puerta esperados del partido
sintético. Una comprobación inicial agotó el tiempo de espera; la repetición y
las consultas posteriores respondieron correctamente. El servicio puede tener
arranques en frío, según los límites de [azure-demo.md](azure-demo.md).

El archivo `.env.local` completo contiene rutas y autenticación locales que no
deben copiarse a GitHub. `.env` y `.env.local` siguen excluidos de Git. No hacen
falta credenciales SQL ni permisos administrativos de Azure para consumir los
servicios publicados.

## Uso desde un workflow existente

Asignar los secretos al paso que ejecute las
llamadas. Ejemplo del bloque `env` de ese paso:

```yaml
env:
  INSIDE_GAME_API_URL: ${{ vars.INSIDE_GAME_API_URL }}
  INSIDE_GAME_API_KEY: ${{ secrets.INSIDE_GAME_API_KEY }}
  INSIDE_GAME_MCP_API_URL: ${{ vars.INSIDE_GAME_MCP_API_URL }}
  INSIDE_GAME_DATA_MCP_URL: ${{ vars.INSIDE_GAME_DATA_MCP_URL }}
  INSIDE_GAME_DATA_MCP_KEY: ${{ secrets.INSIDE_GAME_DATA_MCP_KEY }}
```

Las llamadas HTTP envían `Authorization: Bearer` seguido de la clave correspondiente.
El cliente `DataMcpSettings.from_env()` ya lee las dos variables
`INSIDE_GAME_DATA_MCP_*`. No imprimir claves, cabeceras ni el entorno completo.
No publicar el entorno como artifact de Actions.

El [ejemplo de workflow](examples/check-service-access.yml) contiene una
comprobación lista para usar con esos secretos. Para habilitarlo, copiarlo a
`.github/workflows/check-service-access.yml` de la rama por defecto; sólo se
ejecuta manualmente mediante `workflow_dispatch`. Mantenerlo en `docs/examples/`
permite revisarlo sin iniciar consumo. Ejecutarlo únicamente con un runner
gratuito o minutos gratuitos disponibles, sin habilitar sobreconsumo de pago.

Los secretos de Actions permiten a las automatizaciones usar las claves; la
interfaz de GitHub no permite volver a verlas ni descargarlas para crear un
`.env` local. Para configurar equipos locales, entregar la credencial individual
de cada persona mediante un canal privado. Este trabajo no inicia workflows ni
contrata servicios.

Referencia: [uso de secretos en GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).
