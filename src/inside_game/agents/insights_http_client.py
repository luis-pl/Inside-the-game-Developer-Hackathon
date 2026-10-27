"""Cliente de insights con origen fijo y lectura acotada del HTML autocontenido."""

import json
from html.parser import HTMLParser

import httpx

from inside_game.agents.http_client import HttpDataAgent
from inside_game.agents.insight_contracts import InsightResult
from inside_game.providers.models import ModelFailure


class PayloadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "report-data":
            self.active = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


class HttpInsightsAgent(HttpDataAgent):
    async def _request(
        self, method, path, *, timeout, payload=None, cap=8 * 1024 * 1024
    ):
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
                timeout=timeout + 2,
            ) as client:
                async with client.stream(
                    method,
                    path,
                    json=payload,
                    headers={
                        "Authorization": "Bearer " + self.key,
                        "X-Agent-Deadline-Ms": str(
                            max(1000, min(55000, int(timeout * 1000)))
                        ),
                    },
                ) as response:
                    if response.status_code != 200:
                        raise ModelFailure(
                            {
                                401: "INSIGHTS_UNAUTHORIZED",
                                409: "REVISION_CONFLICT",
                                429: "INSIGHTS_BUSY",
                            }.get(response.status_code, "INSIGHTS_UNAVAILABLE")
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > cap:
                            raise ModelFailure("INSIGHTS_RESPONSE_TOO_LARGE")
                return bytes(raw)
        except httpx.TimeoutException:
            raise ModelFailure("INSIGHTS_TIMEOUT") from None
        except httpx.TransportError:
            raise ModelFailure("INSIGHTS_UNAVAILABLE") from None

    async def preview(self, request, *, timeout):
        import time

        started = time.monotonic()
        raw = await self._request(
            "POST",
            "/a2a/v1/insights",
            timeout=timeout,
            payload=request.model_dump(mode="json"),
        )
        result = InsightResult.model_validate_json(raw)
        if result.request_id != request.request_id:
            raise ModelFailure("INSIGHTS_CORRELATION_MISMATCH")
        if not result.artifact_url or not result.report_id or not result.revision:
            return result, None
        expected = (
            f"/a2a/v1/reports/{result.report_id}/revisions/{result.revision}/html"
        )
        if result.artifact_url != expected:
            raise ModelFailure("INVALID_INSIGHTS_ARTIFACT")
        html = await self._request(
            "GET",
            expected,
            timeout=max(0.01, timeout - (time.monotonic() - started)),
            cap=16 * 1024 * 1024,
        )
        parser = PayloadParser()
        parser.feed(html.decode("utf-8"))
        payload = json.loads("".join(parser.parts))
        metadata = await self._request(
            "GET",
            f"/a2a/v1/reports/{result.report_id}",
            timeout=max(0.01, timeout - (time.monotonic() - started)),
        )
        payload["evidence_catalog"] = json.loads(metadata).get("evidence_catalog", [])
        return result, payload

    async def attach(self, report_id, message, *, timeout):
        raw = await self._request(
            "POST",
            f"/a2a/v1/reports/{report_id}/analysis",
            timeout=timeout,
            payload=message.model_dump(mode="json"),
        )
        result = InsightResult.model_validate_json(raw)
        if (
            result.request_id != message.request_id
            or result.report_id != report_id
            or result.revision != message.expected_revision + 1
        ):
            raise ModelFailure("INSIGHTS_CORRELATION_MISMATCH")
        return result
