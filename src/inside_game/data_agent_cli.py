"""Ejecuta el agente con texto o un mensaje JSON; imprime evidencia, no secretos."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from pydantic import ValidationError

from inside_game.agents.contracts import DataRequest
from inside_game.agents.data_agent import DataAgent
from inside_game.providers.models import create_model
from inside_game.tools.mcp_client import DataMcpSettings, connect_data_mcp


async def execute(request):
    mcp_settings = DataMcpSettings.from_env()
    async with (
        create_model() as model,
        connect_data_mcp(mcp_settings) as mcp,
    ):
        return await DataAgent(model).run(request, mcp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Solicitud natural, sin credenciales")
    source.add_argument("--request-file", type=Path, help="Mensaje DataRequest JSON")
    parser.add_argument(
        "--output", type=Path, help="Archivo de resultado; stdout por defecto"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.verbose:
        logging.getLogger("inside_game.data_agent").setLevel(logging.INFO)
    try:
        request = DataRequest.model_validate(
            json.loads(args.request_file.read_text(encoding="utf-8"))
            if args.request_file
            else {"request_text": args.text}
        )
    except (OSError, ValueError, ValidationError):
        parser.error("La solicitud debe ser texto o un archivo DataRequest válido.")
    try:
        result = asyncio.run(execute(request))
    except Exception:  # noqa: BLE001 - frontera CLI; no exponer detalles de autenticación SDK.
        # No reflejar errores de SDK con URLs/cabeceras. Revisar configuración
        # mediante los nombres documentados, sin imprimir variables de entorno.
        parser.exit(
            1,
            "No se pudo iniciar el agente: revisa configuración del modelo/MCP y credenciales.\n",
        )
    payload = result.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    raise SystemExit(
        {
            "complete": 0,
            "partial": 3,
            "needs_clarification": 2,
            "unsupported": 2,
            "error": 1,
        }[result.status]
    )


if __name__ == "__main__":
    main()
