"""Artefactos privados de la demo, versiones inmutables y publicación atómica.

Memoria acotada, TTL de una hora. Reiniciar el proceso elimina las páginas;
el anfitrión puede descargar el HTML autocontenido para conservarlo.
"""

import asyncio
import time
from dataclasses import dataclass
from uuid import uuid4


class ReportError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status


@dataclass(frozen=True)
class Snapshot:
    result: object
    context: object


class ReportStore:
    def __init__(
        self, *, ttl_seconds=3600, max_pages_per_owner=20, max_bytes=128 * 1024 * 1024
    ):
        self.ttl, self.max_pages, self.max_bytes = (
            ttl_seconds,
            max_pages_per_owner,
            max_bytes,
        )
        self.pages, self.requests = {}, {}
        self.lock = asyncio.Lock()

    def prune(self):
        now = time.monotonic()
        self.pages = {k: v for k, v in self.pages.items() if v["expires"] > now}
        self.requests = {k: v for k, v in self.requests.items() if v["expires"] > now}

    def begin(self, owner, request_id, digest):
        self.prune()
        key = (owner, str(request_id))
        old = self.requests.get(key)
        if old:
            if old["digest"] != digest:
                raise ReportError("REQUEST_ID_REUSED")
            if old["result"] is None:
                raise ReportError("REQUEST_IN_PROGRESS")
            return old["result"].model_copy(deep=True)
        if len(self.requests) >= 1000:
            raise ReportError("REQUEST_CACHE_FULL", 429)
        self.requests[key] = {
            "digest": digest,
            "result": None,
            "expires": time.monotonic() + self.ttl,
        }
        return None

    def finish(self, owner, result):
        self.requests[(owner, str(result.request_id))]["result"] = result.model_copy(
            update={"html": None, "plan": None, "evidence": []}, deep=True
        )

    def abort(self, owner, request_id):
        self.requests.pop((owner, str(request_id)), None)

    def get(self, owner, report_id, revision=None):
        self.prune()
        page = self.pages.get((owner, str(report_id)))
        if not page:
            raise ReportError("REPORT_NOT_FOUND", 404)
        revision = revision or max(page["versions"])
        if revision not in page["versions"]:
            raise ReportError("REVISION_NOT_FOUND", 404)
        snapshot = page["versions"][revision]
        return Snapshot(
            snapshot.result.model_copy(deep=True),
            snapshot.context.model_copy(deep=True),
        )

    async def publish(self, owner, request, result):
        async with self.lock:
            self.prune()
            report_id = request.report_id or uuid4()
            key = (owner, str(report_id))
            previous = self.pages.get(key)
            if request.report_id:
                self.get(owner, report_id)
                if max(previous["versions"]) != request.expected_revision:
                    raise ReportError("REVISION_CONFLICT")
            elif sum(k[0] == owner for k in self.pages) >= self.max_pages:
                raise ReportError("PAGE_LIMIT_REACHED", 429)
            used = sum(
                len(s.result.html.encode())
                for p in self.pages.values()
                for s in p["versions"].values()
            )
            if used + len(result.html.encode()) > self.max_bytes:
                raise ReportError("ARTIFACT_CAPACITY_REACHED", 507)
            revision = request.expected_revision + 1 if request.report_id else 1
            result = result.model_copy(
                update={
                    "report_id": report_id,
                    "revision": revision,
                    "artifact_url": f"/a2a/v1/reports/{report_id}/revisions/{revision}/html",
                },
                deep=True,
            )
            versions = dict(previous["versions"]) if previous else {}
            versions[revision] = Snapshot(result, request.context.model_copy(deep=True))
            while len(versions) > 5:
                versions.pop(min(versions))
            self.pages[key] = {
                "versions": versions,
                "expires": time.monotonic() + self.ttl,
            }
            return result.model_copy(deep=True)
