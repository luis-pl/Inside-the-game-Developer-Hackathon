# Acceso del equipo y agentes a la demo de Azure

La infraestructura y el estado de publicación se registran en [deployment/cloud.json](../deployment/cloud.json). El proceso cloud combina API y MCP en un contenedor Linux y usa credenciales individuales caducables. Los módulos de agentes y A2A se implementan por separado: este despliegue prepara los servicios de datos que consumirán.

## Identidades

Se eligió esta alternativa porque Azure rechazó la creación de aplicaciones Entra con `Authorization_RequestDenied`: ser Owner de la suscripción no otorgó los permisos del directorio. No se añadieron permisos globales ni se simula inicio de sesión Microsoft.

| ID de credencial | Rol | Titular asignado |
|---|---|---|
| team-owner | developer | Responsable del equipo |
| team-collaborator-01 | developer | Compañero autorizado, entregar sólo su propia clave |
| agent-data | agent | Servicio del agente de datos |

Cada clave tiene más de 256 bits aleatorios y caduca a los 14 días desde su emisión. El archivo privado incluye la fecha exacta de caducidad en Unix UTC. Una clave identifica a su titular asignado por posesión; no verifica por sí sola el correo electrónico de esa persona. No se enviaron correos ni invitaciones Microsoft. No compartir una misma clave entre compañeros: se perdería atribución individual.

Las claves originales se guardaron fuera del repositorio en una carpeta privada del equipo que hizo la configuración, con acceso restringido al usuario de Windows y SYSTEM. El servidor sólo recibe hashes SHA256, identificador, rol, operaciones permitidas, caducidad y estado habilitado. No hay contraseñas SQL en ese archivo ni en las respuestas.

## Uso

Las direcciones son `https://<public_host>/docs`, `/api/operations`, `/api/whoami` y `/mcp`; el host real está en `deployment/cloud.json`. Swagger permite introducir una clave mediante Authorize. El esquema público no incluye datos de partidos ni credenciales; las consultas necesitan Bearer.

Para probar desde este repositorio sin copiar la clave a la consola:

```powershell
.\.venv\Scripts\python.exe scripts/cloud_client.py --private-file "RUTA_PRIVADA/inside-game-credentials.json" --identity team-owner
.\.venv\Scripts\python.exe scripts/cloud_client.py --private-file "RUTA_PRIVADA/inside-game-credentials.json" --identity agent-data
```

Cada compañero recibe sólo su clave, la URL HTTPS y las instrucciones, por un canal privado. El cliente del agente debe obtener su clave de un secreto de Container Apps o del entorno, y enviar `Authorization: Bearer <clave>` en API y MCP. No ponerla en prompts, en código, en URLs o en Git. El receptor no necesita permisos de la suscripción Azure ni acceso al firewall de SQL.

Este MCP usa autenticación Bearer de claves privadas y no ofrece un flujo OAuth de inicio de sesión. El cliente debe permitir configurar cabeceras HTTP. MCP expone las herramientas autorizadas de la credencial; A2A es el protocolo entre agentes y también necesitará validar identidades cuando se implementen esos endpoints.

## Límites y trazabilidad

El contenedor cloud exige credenciales individuales y deshabilita el bypass local y la clave global. Comprueba caducidad, revocación y lista de operaciones. Los permisos de cada clave se aplican tanto al POST canónico como a los GET de conveniencia. La identidad se conserva del MCP a la API, sin sustituirla por una clave interna compartida.

Los logs incluyen ID de credencial, rol, operación, identificador de solicitud, partido, resultado y duración. Nunca incluyen la clave, Authorization o el cuerpo completo. Se envían a Log Analytics, con 30 días de retención y cuota diaria de ingesta de 0,1 GB. Si se alcanza la cuota, puede dejar de ingerirse auditoría: es un límite de coste, no una garantía de registro ilimitado.

Hay hasta 120 consultas por minuto e identidad y cuatro consultas activas por proceso; la demo limita el despliegue a una réplica. Un despliegue con varias réplicas necesitaría un limitador compartido. Se mantienen ventanas, tamaños y consultas predeterminadas. Identificarse no garantiza buena intención; estos límites acotan el uso y los registros permiten investigarlo.

## SQL y costes

SQL usa una identidad administrada exclusiva, `id-inside-game-api`, con un usuario miembro de `football_reader`. No se usa la sesión personal de Azure CLI dentro del contenedor. El runtime comprueba que no tiene permisos administrativos ni de escritura. Sólo se añaden al firewall las IP de salida declaradas por Azure para el contenedor.

Container Apps se configura en consumo, entre cero y una réplica, 1 CPU y 2 GiB. Puede haber un arranque en frío; antes de la demostración se debe probar una consulta real. La oferta gratuita de SQL conserva `AutoPause` al agotar su cupo. Registro privado de imágenes, cómputo y logs pueden consumir crédito: cero réplicas no elimina el coste del registro o almacenamiento. No se promete coste cero ni se amplía el cupo SQL automáticamente.

## Revocar una credencial

Para añadir otro compañero o agente, emitir una identidad nueva y aplicar el registro en Azure:

```powershell
.\.venv\Scripts\python.exe scripts/manage_credentials.py --private-file "RUTA_PRIVADA/inside-game-credentials.json" --issue-id team-companero-02 --name "Companero 02" --role developer --days 14
.\.venv\Scripts\python.exe scripts/sync_cloud_credentials.py --private-file "RUTA_PRIVADA/inside-game-credentials.json"
```

Para un servicio de agente usar `--role agent` y un ID distinto para cada servicio. El archivo administrativo contiene todas las claves; compartir con el nuevo titular únicamente su registro correspondiente. El archivo administrativo permanece en la máquina del responsable.

Para revocar:

```powershell
.\.venv\Scripts\python.exe scripts/manage_credentials.py --private-file "RUTA_PRIVADA/inside-game-credentials.json" --revoke team-collaborator-01
.\.venv\Scripts\python.exe scripts/sync_cloud_credentials.py --private-file "RUTA_PRIVADA/inside-game-credentials.json"
```

El primer comando cambia el registro local; el segundo aplica los hashes y crea una nueva revisión en Azure. La revocación es efectiva al activarse esa revisión. Verificar que la clave revocada obtiene 401 y que las otras siguen funcionando. No reactivar una clave comprometida; emitir una nueva.

## Construcción y pruebas

El Dockerfile instala el driver Linux y ejecuta Python con un usuario sin privilegios. `.dockerignore` permite únicamente los archivos de empaquetado y `src/`. No se suben configuraciones locales, credenciales, backups ni el historial Git.

Las pruebas de `tests/test_cloud_access.py` verifican identidad, permisos, caducidad, revocación, rechazo de claves erróneas y preservación de identidad entre MCP y API. El informe remoto se genera después de publicar y consultar la base desde Azure.
