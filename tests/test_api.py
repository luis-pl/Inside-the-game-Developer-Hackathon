import pytest
from fastapi.testclient import TestClient

from inside_game.api import create_app
from inside_game.contracts import ShotsRequest
from inside_game.errors import DomainError
from inside_game.service import AnalyticsService
from inside_game.settings import Settings
from inside_game.tools import topology
from inside_game.tools.synthetic_db import SqlRepository

TOKEN = "test-only-credential-32-characters-long"


@pytest.fixture
def client(repository):
    with TestClient(
        create_app(Settings(api_key=TOKEN, local_access=False), repository)
    ) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        yield client


def post(client, op, **body):
    return client.post("/api/operations/" + op, json=body)


def test_exact_shot_totals_and_single_counted_saves(client):
    r = post(client, "get_shots", match_id=900001, view="summary", outcome="on_target")
    assert r.status_code == 200
    assert r.json()["data"]["summary"]["shots_on_target"] == 2
    assert r.json()["data"]["summary"]["xg"] == pytest.approx(0.5)
    r = post(
        client,
        "get_player_summary",
        match_ids=[900001],
        player_id=201,
        profile_id="goalkeeping",
    )
    assert r.json()["data"]["reports"][0]["metrics"]["saves"] == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"sql": "DROP TABLE events"},
        {"scope": {"kind": "match", "sql": "SELECT 1"}},
        {"where": "1=1"},
        {"match_id": "900001 OR 1=1"},
        {"match_id": True},
    ],
)
def test_unapproved_input_rejected(client, extra):
    r = post(client, "get_shots", **{"match_id": 900001, **extra})
    assert r.status_code == 422
    assert "DROP TABLE" not in r.text


def test_no_generic_executor(client):
    assert post(client, "execute_query", sql="SELECT 1").status_code == 404
    assert client.get("/api/matches/900001/shots?sql=SELECT").status_code == 422
    assert (
        client.post(
            "/api/operations/get_shots?team_id=1", json={"match_id": 900001}
        ).status_code
        == 422
    )


def test_authentication_and_rate_limit(repository):
    app = create_app(
        Settings(api_key=TOKEN, local_access=False, rate_per_minute=1), repository
    )
    with TestClient(app) as client:
        assert client.get("/api/operations").status_code == 401
        client.headers["Authorization"] = "Bearer " + TOKEN
        assert client.get("/api/operations").status_code == 200
        assert client.get("/api/operations").status_code == 429


def test_remote_cannot_use_local_bypass(repository):
    with TestClient(create_app(Settings(), repository)) as client:
        assert (
            client.post(
                "/api/operations/get_shots", json={"match_id": 900001}
            ).status_code
            == 401
        )


def test_entity_and_temporal_bounds(client):
    assert post(client, "get_shots", match_id=900001, team_id=3).status_code == 422
    assert (
        post(client, "get_shots", match_id=900001, team_id=1, player_id=201).status_code
        == 422
    )
    assert (
        post(
            client,
            "get_shots",
            match_id=900001,
            scope={"kind": "window", "period": 1, "start_ms": 0, "end_ms": 61000},
        ).status_code
        == 422
    )
    assert (
        post(
            client, "get_tracking_frame", match_id=900001, period=1, time_ms=1500
        ).status_code
        == 422
    )


def test_pagination_bound_to_query_and_totals_not_page(client):
    first = post(client, "get_shots", match_id=900001, limit=1).json()
    cursor = first["pagination"]["next_cursor"]
    assert first["data"]["total"] == 2 and len(first["data"]["items"]) == 1
    second = post(client, "get_shots", match_id=900001, limit=1, cursor=cursor).json()
    assert (
        second["data"]["items"][0]["event_id"] != first["data"]["items"][0]["event_id"]
    )
    assert (
        post(
            client, "get_shots", match_id=900001, team_id=1, limit=1, cursor=cursor
        ).status_code
        == 422
    )


def test_aerial_contest_one_record_and_correct_winner(client):
    r = post(client, "get_defensive_actions", match_id=900001, kind="aerial_duel")
    assert r.status_code == 200 and r.json()["data"]["total"] == 1
    assert r.json()["data"]["items"][0]["winner"]["player_id"] == 210
    r = post(
        client,
        "get_defensive_actions",
        match_id=900001,
        team_id=2,
        kind="aerial_duel",
        outcome="won",
    )
    assert r.json()["data"]["total"] == 1


def test_aerial_summary_preserves_both_global_perspectives(client):
    response = post(
        client,
        "get_defensive_actions",
        match_id=900001,
        kind="aerial_duel",
        view="summary",
    )
    summary = response.json()["data"]["summary"]
    assert summary["aerial_contests"] == 1
    assert summary["aerial_won"] == 1 and summary["aerial_lost"] == 1


def test_sql_query_timeout_is_set_on_connection(monkeypatch):
    import mssql_python

    observed = []

    class Cursor:
        def execute(self, statement):
            observed.append(connection.timeout)

        def fetchone(self):
            return [1, 0, 0, 0, 0]

        def close(self):
            pass

    class Connection:
        timeout = 0

        def cursor(self):
            return Cursor()

        def close(self):
            pass

    connection = Connection()
    monkeypatch.setattr(mssql_python, "connect", lambda *args, **kwargs: connection)
    SqlRepository(Settings())._connect()
    assert observed and all(value == 15 for value in observed)


def test_tackle_lost_belongs_to_challenger(client):
    r = post(
        client, "get_defensive_actions", match_id=900001, kind="tackle", outcome="lost"
    )
    assert r.json()["data"]["items"][0]["player_id"] == 206


def test_defensive_profile_uses_opponent_actions(client):
    response = post(client, "get_defensive_profile", match_id=900001, team_id=2)
    assert response.status_code == 200
    assert response.json()["data"]["anchor_count"] == 3
    assert response.json()["data"]["shots_conceded"] == 2


def test_fifty_fifty_outcome_filters_without_team(client):
    for outcome in ("all", "won", "lost"):
        response = post(
            client,
            "get_defensive_actions",
            match_id=900001,
            kind="fifty_fifty",
            outcome=outcome,
        )
        assert response.json()["data"]["total"] == 1


def test_sql_decimal_is_serialized_as_number():
    from decimal import Decimal

    from inside_game.tools.synthetic_db import normalize

    assert normalize(Decimal("5400.000000")) == 5400.0


def test_goalkeeping_rate_uses_shot_outcomes_without_double_count(client):
    response = post(
        client,
        "get_player_summary",
        match_ids=[900001],
        player_id=201,
        profile_id="goalkeeping",
    )
    metrics = response.json()["data"]["aggregate"]
    assert metrics["shots_on_target_faced"] == 2
    assert metrics["saves"] == 1
    assert metrics["goals_conceded"] == 1
    assert metrics["save_rate"] == pytest.approx(0.5)
    assert (
        post(
            client,
            "get_player_summary",
            match_ids=[900001],
            player_id=110,
            profile_id="goalkeeping",
        ).status_code
        == 422
    )


def test_pressure_union_is_not_summed_overlap(repository):
    from copy import deepcopy

    from inside_game.analytics import events_for, summary

    req = ShotsRequest(match_id=900001)
    first = next(e for e in events_for(repository.data, req) if e["type_id"] == 17)
    second = deepcopy(first)
    second["period_time_ms"] += 1000
    metrics = summary(
        repository.data, [first, second], "pressure_effectiveness", scope=req.scope
    )
    assert metrics["summed_action_seconds"] == 4
    assert metrics["union_pressure_seconds"] == 3


def test_half_open_window(client):
    r = post(
        client,
        "get_shots",
        match_id=900001,
        scope={"kind": "window", "period": 1, "start_ms": 0, "end_ms": 3000},
    )
    assert r.json()["data"]["total"] == 0


def test_substitution_minutes_and_presence(repository, client):
    service = AnalyticsService(repository)
    assert service.covered_minutes(
        repository.data, ShotsRequest(match_id=900001).scope, 106
    ) == pytest.approx(70 / 60)
    assert service.covered_minutes(
        repository.data, ShotsRequest(match_id=900001).scope, 112
    ) == pytest.approx(50 / 60)
    r = post(client, "get_tracking_frame", match_id=900001, period=2, time_ms=10000)
    ids = {p["player_id"] for p in r.json()["data"]["frames"][0]["players"]}
    assert 112 in ids and 106 not in ids


def points(coords):
    return [
        {
            "player_id": i + 1,
            "team_id": 1 if i < 2 else 2,
            "x_m": float(x),
            "y_m": float(y),
        }
        for i, (x, y) in enumerate(coords)
    ]


def test_mst_connection_threshold_and_invariance():
    p = points([(0, 0), (10, 0), (30, 0)])
    assert topology.proximity(p, 10)["component_count"] == 2
    assert topology.proximity(p, 20)["component_count"] == 1
    assert topology.proximity(p, 10)["critical_connection_distance_m"] == 20
    transformed = points([(7 - y, 4 + x) for x, y in [(0, 0), (10, 0), (30, 0)]])
    assert topology.proximity(transformed, 10)["critical_connection_distance_m"] == 20


def test_rips_fills_triangle_but_square_has_scale_dependent_hole():
    triangle = topology.persistence(points([(0, 0), (10, 0), (5, 8)]))
    assert all(b["h1"] == 0 for b in triangle["betti"])
    square = topology.persistence(points([(0, 0), (10, 0), (10, 10), (0, 10)]))
    assert next(b["h1"] for b in square["betti"] if b["epsilon_m"] == 10) == 1
    assert next(b["h1"] for b in square["betti"] if b["epsilon_m"] == 15) == 0


def test_voronoi_partition_and_duplicate_policy():
    from shapely.geometry import Polygon

    result = topology.coverage(points([(10, 10), (90, 10), (10, 60), (90, 60)]))
    assert result["area_sum_m2"] == pytest.approx(105 * 68)
    polygons = [Polygon(c["polygon_m"]) for c in result["cells"]]
    assert all(
        a.intersection(b).area < 1e-8
        for i, a in enumerate(polygons)
        for b in polygons[i + 1 :]
    )
    with pytest.raises(DomainError):
        topology.coverage(points([(10, 10), (10, 10)]))


def test_unknown_sql_template_never_opens_connection():
    with pytest.raises(DomainError, match="not registered"):
        SqlRepository(Settings()).execute("../../other")


def test_registry_and_openapi_have_34_operations(client):
    response = client.get("/api/operations").json()
    assert len(response["operations"]) == 34
    schema = client.get("/openapi.json").json()
    assert all(op["path"] in schema["paths"] for op in response["operations"])


def test_large_request_rejected(client):
    r = client.post(
        "/api/operations/get_shots",
        content=b"x" * 70000,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413


def test_query_parameter_repetition_rejected(client):
    assert (
        client.get("/api/matches/900001/shots?team_id=1&team_id=2").status_code == 422
    )


def test_bin_metadata_clipped_to_requested_window(client):
    r = post(
        client,
        "get_metric_series",
        match_id=900001,
        profile_id="finishing",
        scope={"kind": "window", "period": 1, "start_ms": 2000, "end_ms": 4000},
    )
    assert r.status_code == 200
    assert r.json()["data"]["series"][0]["start_ms"] == 2000
    assert r.json()["data"]["series"][0]["end_ms"] == 4000


def test_pressure_followup_is_censored_at_window_end(client):
    r = post(
        client,
        "get_team_summary",
        match_ids=[900001],
        team_id=2,
        profile_id="pressure_effectiveness",
        scope={"kind": "window", "period": 1, "start_ms": 4000, "end_ms": 6000},
    )
    metrics = r.json()["data"]["aggregate"]
    assert metrics["eligible_pressures"] == 0
    assert metrics["censored_pressures"] == 1
    assert metrics["association_rate"] is None


def test_event_heatmap_grid_has_partial_edge_cells(client, repository):
    repository.data["events"][0]["location_y"] = 79.0
    r = post(
        client,
        "get_heatmap",
        match_id=900001,
        team_id=1,
        mode="event_count",
        event_type="pass",
    )
    cell = r.json()["data"]["cells"][0]
    assert cell["y_m"] == 65


def test_multi_match_ratios_use_total_denominators(repository):
    service = AnalyticsService(repository)
    parts = [
        {
            "metrics": {
                "completed_passes": 1,
                "attempted_passes": 1,
                "completion_rate": 1.0,
            }
        },
        {
            "metrics": {
                "completed_passes": 0,
                "attempted_passes": 9,
                "completion_rate": 0.0,
            }
        },
    ]
    assert service.aggregate_reports(parts)["completion_rate"] == pytest.approx(0.1)


def test_sequence_context_does_not_invent_pass_combination_across_interruption(
    repository,
):
    from copy import deepcopy

    from inside_game.analytics import events_for, sequence_rows
    from inside_game.contracts import SequenceRequest

    req = SequenceRequest(match_id=900001, pattern_id="pass_aba")
    data = repository.data
    # A completed return after an incomplete intervening pass is not consecutive A-B-A.
    failed = deepcopy(data["events"][0])
    failed["event_id"] = "failed"
    failed["event_index"] = 2
    back = deepcopy(failed)
    back["event_id"] = "back"
    back["event_index"] = 3
    back["player_id"] = 106
    data["events"] = [data["events"][0], failed, back]
    data["passes"]["failed"] = {
        **data["passes"][data["events"][0]["event_id"]],
        "outcome": {"id": 9},
    }
    data["passes"]["back"] = {
        **data["passes"][data["events"][0]["event_id"]],
        "recipient_player_id": 110,
    }
    assert sequence_rows(data, events_for(data, req), "pass_aba", req.scope) == []
