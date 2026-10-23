"""Credenciales individuales de la demo: sólo hashes en el servidor y auditoría.

Una clave identifica a su titular asignado, no verifica una dirección de correo.
El archivo privado se entrega por un canal seguro. El registro de hashes permite
caducar o revocar claves sin compartir contraseñas entre personas y agentes.
"""

import hashlib
import json
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass

from inside_game.service import OPERATIONS

# Sólo vive durante una petición MCP autenticada; no aparece en resultados/logs.
mcp_credential = ContextVar("mcp_credential", default="")
mcp_principal = ContextVar("mcp_principal", default=None)


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    role: str
    expires_at: int
    operations: frozenset[str]


class KeyRegistry:
    def __init__(self, records=()):
        self.entries = []
        seen = set()
        for item in records:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not 1 <= len(item["id"]) <= 80
                or item["id"] in seen
                or item.get("role") not in ("developer", "agent")
                or not isinstance(item.get("name"), str)
                or not 1 <= len(item["name"]) <= 100
                or type(item.get("expires_at")) is not int
                or type(item.get("enabled", True)) is not bool
            ):
                raise ValueError("Invalid individual credential configuration")
            digest = item.get("sha256", "")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Only SHA256 credential digests are accepted")
            operations = frozenset(item.get("operations", OPERATIONS))
            if not operations or not operations <= OPERATIONS.keys():
                raise ValueError("Credential contains unregistered operations")
            seen.add(item["id"])
            principal = Principal(
                item["id"], item["name"], item["role"], item["expires_at"], operations
            )
            self.entries.append((digest, item.get("enabled", True), principal))

    def verify(self, key):
        if not isinstance(key, str) or not 32 <= len(key) <= 256:
            return None
        digest = hashlib.sha256(key.encode()).hexdigest()
        found = None
        for expected, enabled, principal in self.entries:
            matches = secrets.compare_digest(digest, expected)
            if matches and enabled and principal.expires_at > time.time():
                found = principal
        return found


def credential_records(value):
    records = json.loads(value)
    if not isinstance(records, list) or len(records) > 100:
        raise ValueError("Expected at most 100 individual credential records")
    return tuple(records)
