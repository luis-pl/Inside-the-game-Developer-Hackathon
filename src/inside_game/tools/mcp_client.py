"""Cliente del MCP remoto con destino y credencial definidos por el servidor.

El SDK MCP 2 usa httpx2 para su transporte; las cabeceras se configuran en ese
cliente, nunca como argumentos que el modelo pueda ver o cambiar.
"""

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True)
class DataMcpSettings:
    url: str
    key: str = field(default="", repr=False)

    def __post_init__(self):
        url = urlsplit(self.url)
        local = url.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path != "/mcp"
            or url.scheme not in {"https", "http"}
            or (not local and (url.scheme != "https" or len(self.key) < 32))
        ):
            raise ValueError(
                "Configure an MCP /mcp URL and a private key for remote access"
            )

    @classmethod
    def from_env(cls):
        key = os.getenv("INSIDE_GAME_DATA_MCP_KEY", "")
        private_file = os.getenv("INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE", "")
        if not key and private_file:
            credential = json.loads(Path(private_file).read_text(encoding="utf-8"))
            if credential.get("credential_id") != "agent-data":
                raise ValueError("Use the individual agent-data credential file")
            key = credential["key"]
        return cls(
            url=os.getenv("INSIDE_GAME_DATA_MCP_URL", "http://127.0.0.1:8001/mcp"),
            key=key,
        )


@asynccontextmanager
async def connect_data_mcp(settings: DataMcpSettings):
    headers = {"Authorization": "Bearer " + settings.key} if settings.key else {}
    async with httpx2.AsyncClient(
        headers=headers,
        timeout=90,
        trust_env=False,
        follow_redirects=False,
    ) as http:

        @asynccontextmanager
        async def transport():
            async with streamable_http_client(
                settings.url, http_client=http
            ) as streams:
                yield streams

        async with Client(transport(), read_timeout_seconds=90) as client:
            yield client
