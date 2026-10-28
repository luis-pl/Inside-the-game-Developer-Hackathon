"""Canal HTTP tipado hacia data. Destino/credencial son del anfitrión, no del LLM."""

from urllib.parse import urlsplit

import httpx

from inside_game.agents.contracts import DataResult
from inside_game.agents.experiments import T
from inside_game.providers.models import ModelFailure


class HttpDataAgent:
    def __init__(self, base_url, key, *, transport=None):
        parsed = urlsplit(base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.scheme not in {"http", "https"}
            or (not local and parsed.scheme != "https")
            or not 32 <= len(key) <= 256
        ):
            raise ValueError("INVALID_DATA_AGENT_CONFIG")
        self.base_url, self.key, self.transport = base_url.rstrip("/"), key, transport

    async def fetch(self, request, *, timeout):
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
                timeout=timeout + 2,
            ) as client:
                async with client.stream(
                    "POST",
                    "/a2a/v1/data",
                    json=request.model_dump(mode="json"),
                    headers={
                        "Authorization": "Bearer " + self.key,
                        "X-Agent-Deadline-Ms": str(
                            max(1000, min(int(T(45000)), int(timeout * 1000)))
                        ),
                        "X-Request-ID": str(request.request_id),
                    },
                ) as response:
                    if response.status_code != 200:
                        raise ModelFailure(
                            {
                                401: "DATA_AGENT_UNAUTHORIZED",
                                403: "DATA_AGENT_FORBIDDEN",
                                429: "DATA_AGENT_BUSY",
                            }.get(response.status_code, "DATA_AGENT_UNAVAILABLE")
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 8 * 1024 * 1024:
                            raise ModelFailure("DATA_AGENT_RESPONSE_TOO_LARGE")
                result = DataResult.model_validate_json(raw)
                if result.request_id != request.request_id:
                    raise ModelFailure("DATA_AGENT_CORRELATION_MISMATCH")
                return result
        except httpx.TimeoutException:
            raise ModelFailure("DATA_AGENT_TIMEOUT") from None
        except httpx.TransportError:
            raise ModelFailure("DATA_AGENT_UNAVAILABLE") from None
