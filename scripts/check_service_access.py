"""Prueba API y MCP con variables de Actions o archivos .env privados.

No ejecuta el contenido del .env ni imprime claves, cabeceras o cuerpos de error.
Los resultados de las consultas corresponden al dataset sintético de la demo.
"""

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

NAMES = {
    "INSIDE_GAME_API_URL",
    "INSIDE_GAME_API_KEY",
    "INSIDE_GAME_DATA_MCP_URL",
    "INSIDE_GAME_DATA_MCP_KEY",
}
QUERY = {"match_id": 900001, "team_id": 1, "outcome": "on_target", "view": "summary"}


def configuration(files):
    values = {name: os.environ[name] for name in NAMES if name in os.environ}
    for path in files:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, separator, value = line.partition("=")
            name = name.strip()
            if separator and name in NAMES:
                values[name] = value.strip().strip('"').strip("'")
    return values


def destination(values, url_name, key_name, path):
    url, key = values.get(url_name, ""), values.get(key_name, "")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != path
    ):
        raise ValueError("Invalid service URL")
    if not 32 <= len(key) <= 256 or any(char.isspace() for char in key):
        raise ValueError("Missing or invalid raw bearer key")
    return url, key


def check_result(result):
    if result.get("data", {}).get("total") != 6:
        raise ValueError("Unexpected synthetic query result")
    if result.get("provenance", {}).get("is_synthetic") is not True:
        raise ValueError("Missing synthetic provenance")


async def check_api(values):
    url, key = destination(values, "INSIDE_GAME_API_URL", "INSIDE_GAME_API_KEY", "")
    async with httpx.AsyncClient(
        base_url=url,
        headers={"Authorization": "Bearer " + key},
        timeout=90,
        trust_env=False,
        follow_redirects=False,
    ) as http:
        identity = await http.get("/api/whoami")
        identity.raise_for_status()
        result = await http.post("/api/operations/get_shots", json=QUERY)
        result.raise_for_status()
        check_result(result.json())
        return {
            "transport": "api",
            "credential_id": identity.json()["credential_id"],
            "total": 6,
            "is_synthetic": True,
            "passed": True,
        }


async def check_mcp(values):
    url, key = destination(
        values, "INSIDE_GAME_DATA_MCP_URL", "INSIDE_GAME_DATA_MCP_KEY", "/mcp"
    )
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + key},
        timeout=90,
        trust_env=False,
        follow_redirects=False,
    ) as http:

        @asynccontextmanager
        async def transport():
            async with streamable_http_client(url, http_client=http) as streams:
                yield streams

        async with Client(transport(), read_timeout_seconds=90) as client:
            tools = (await client.list_tools()).tools
            if "get_shots" not in {tool.name for tool in tools}:
                raise ValueError("Required MCP tool not available")
            result = await client.call_tool("get_shots", QUERY)
            if result.is_error or not result.structured_content:
                raise ValueError("MCP query failed")
            check_result(result.structured_content)
            return {
                "transport": "mcp",
                "tools": len(tools),
                "total": 6,
                "is_synthetic": True,
                "passed": True,
            }


async def verify(values, transport):
    for name, operation in (("api", check_api), ("mcp", check_mcp)):
        if transport not in ("both", name):
            continue
        try:
            result = await operation(values)
        except Exception as error:  # noqa: BLE001 -- SDK errors must be redacted at the CLI boundary.
            # HTTP/SDK errors may embed request details; do not print exceptions.
            failure = {
                "transport": name,
                "passed": False,
                "error": "Check the private configuration and service availability",
                "error_type": type(error).__name__,
            }
            if isinstance(error, httpx.HTTPStatusError):
                failure["http_status"] = error.response.status_code
            print(json.dumps(failure), flush=True)
            return 1
        print(json.dumps(result), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, action="append", default=[])
    parser.add_argument("--transport", choices=("api", "mcp", "both"), default="both")
    args = parser.parse_args()
    try:
        values = configuration(args.env_file)
    except (OSError, UnicodeError):
        print("Cannot read private configuration; no credentials were printed")
        return 1
    return asyncio.run(verify(values, args.transport))


if __name__ == "__main__":
    raise SystemExit(main())
