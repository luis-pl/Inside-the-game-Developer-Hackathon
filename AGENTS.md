# Inside the game: Developer Hackathon

Este repositorio prepara un sistema de analítica deportiva con cuatro agentes:
intérprete de solicitudes, agente de datos, analista deportivo y constructor de
dashboards. El paquete Python es `inside_game` y vive en `src/inside_game/`.

La estructura inicial contiene módulos reservados, sin implementación de agentes,
contratos, orquestación, API, CLI, proveedores de modelos ni servidores MCP/A2A.
Desarrollar esas funciones cuando la tarea correspondiente lo solicite.

La base Azure SQL, su esquema y los datos sintéticos existentes están documentados
en `database/azure-sql/`. Consultar su `README.md` y `DATA-QUALITY.md` al trabajar
con datos; conservar la identificación explícita de su procedencia sintética.
No guardar credenciales en el repositorio.

Consultar `docs/repository-structure.md` para localizar los módulos. Los archivos
de `drafts/` son referencias de diseño.
