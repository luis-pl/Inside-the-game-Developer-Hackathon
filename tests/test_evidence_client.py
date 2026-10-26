"""Motor de evidencia (tools/evidence_client.py): validación, caché y paginación."""

import asyncio
import copy

from inside_game.insights.demo import demo_manifest
from inside_game.tools.evidence_client import EvidenceClient

FIXTURE = {e["operation"]: e["response"] for e in demo_manifest()["evidence"]}


class FakeTransport:
    """Responde el fixture SINTÉTICO de la galería por operación."""

    def __init__(self, overrides=None, errors=None, pages=None):
        self.responses = {**FIXTURE, **(overrides or {})}
        self.errors = errors or {}
        self.pages = pages or {}
        self.calls = []

    async def call(self, operation, arguments):
        self.calls.append((operation, arguments))
        if operation in self.errors:
            return None, self.errors[operation]
        if operation in self.pages:
            return self.pages[operation][arguments.get("cursor")], None
        return copy.deepcopy(self.responses[operation]), None


def run(coroutine):
    return asyncio.run(coroutine)


def shots_args():
    return {"match_id": 900001, "limit": 200}


def test_client_caches_identical_queries_and_validates_arguments():
    transport = FakeTransport()
    client = EvidenceClient(transport)
    first = run(client.query("get_shots", shots_args()))
    again = run(client.query("get_shots", {"limit": 200, "match_id": 900001}))
    assert first == again and first[1] is None
    assert len(transport.calls) == 1
    assert run(client.query("get_shots", {"match_id": "x"})) == ([], "INVALID_ARGUMENT")
    assert run(client.query("drop_table", {})) == ([], "UNREGISTERED_OPERATION")


def test_client_follows_cursors_and_rejects_foreign_responses():
    page1 = copy.deepcopy(FIXTURE["get_shots"])
    page1["pagination"] = {"next_cursor": "c2"}
    page2 = copy.deepcopy(FIXTURE["get_shots"])
    transport = FakeTransport(pages={"get_shots": {None: page1, "c2": page2}})
    ids, error = run(EvidenceClient(transport).query("get_shots", shots_args()))
    assert error is None and len(ids) == 2
    assert transport.calls[1][1]["cursor"] == "c2"

    foreign = copy.deepcopy(FIXTURE["get_passes"])
    client = EvidenceClient(FakeTransport(overrides={"get_shots": foreign}))
    assert run(client.query("get_shots", shots_args())) == ([], "INVALID_DATA_RESPONSE")


def test_client_does_not_present_partial_pagination_as_complete():
    looping = copy.deepcopy(FIXTURE["get_shots"])
    looping["pagination"] = {"next_cursor": "again"}
    transport = FakeTransport(pages={"get_shots": {None: looping, "again": looping}})
    assert run(EvidenceClient(transport).query("get_shots", shots_args())) == (
        [],
        "INVALID_PAGINATION",
    )


class SlowTransport(FakeTransport):
    """Mide cuántas consultas van a la vez."""

    def __init__(self):
        super().__init__()
        self.active = self.peak = 0

    async def call(self, operation, arguments):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        try:
            return await super().call(operation, arguments)
        finally:
            self.active -= 1


class Query:
    def __init__(self, key, operation, arguments):
        self.key, self.operation, self.arguments = key, operation, arguments


def test_run_executes_independent_queries_in_parallel_with_stable_ids():
    transport = SlowTransport()
    client = EvidenceClient(transport)
    plan = [
        Query("a", "get_shots", shots_args()),
        Query("b", "get_passes", {"match_id": 900001, "limit": 200}),
        Query("c", "get_shots", {"limit": 200, "match_id": 900001}),  # igual que a
        Query("d", "get_ball_actions", {"match_id": 900001, "limit": 200}),
        Query("e", "get_events", {"match_id": 900001, "limit": 200}),
    ]
    results = run(client.run(plan))
    assert [results[k][0][0].split("-")[0] for k in "abde"] == ["q1", "q2", "q3", "q4"]
    assert results["a"] == results["c"], "la consulta repetida comparte resultado"
    assert len(transport.calls) == 4, "una consulta idéntica en vuelo no se repite"
    assert 1 < transport.peak <= 3, "hay paralelismo, acotado por la API"


def test_http_transport_bursts_within_the_window_and_waits_beyond_it(monkeypatch):
    from inside_game.tools import evidence_client as module

    now, slept = [1000.0], []

    async def fake_sleep(seconds):
        slept.append(round(seconds, 1))
        now[0] += seconds

    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    class Response:
        status_code = 200

        def json(self):
            return {}

    class Client:
        async def post(self, *_args, **_kwargs):
            return Response()

    transport = module.HttpTransport(Client(), rate_per_minute=3)

    async def burst():
        for _ in range(3):
            await transport.call("get_shots", {})
        assert slept == [], "tres consultas caben en la ventana: sin esperas"
        await transport.call("get_shots", {})

    run(burst())
    assert slept == [60.0], "la cuarta espera a que salga la primera de la ventana"


def test_http_transport_polls_a_paused_database_every_few_seconds(monkeypatch):
    from inside_game.tools import evidence_client as module

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    class Response:
        def __init__(self, status):
            self.status_code = status

        def json(self):
            return {}

    class Client:
        def __init__(self):
            self.statuses = [503, 503, 200]

        async def post(self, *_args, **_kwargs):
            return Response(self.statuses.pop(0))

    _, error = run(module.HttpTransport(Client()).call("get_shots", {}))
    assert error is None
    assert slept == [module.COLD_START_POLL_S] * 2
