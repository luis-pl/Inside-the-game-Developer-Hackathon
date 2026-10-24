"""Read-only HTTPS/MCP QA for the real anonymized dataset (no model calls)."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from verify_api import verification_cases

from inside_game.dashboard.config import DashboardConfig
from inside_game.dashboard.gateway import DataError, EpisodeService, HttpOperations
from inside_game.service import OPERATIONS
from inside_game.tools.mcp_client import DataMcpSettings, connect_data_mcp

ROOT = Path(__file__).resolve().parents[1]


async def verify():
    config = DashboardConfig.load(ROOT)

    class VerificationOperations(HttpOperations):
        ALLOWED = frozenset(OPERATIONS)

    operations = VerificationOperations(config)
    service = EpisodeService(operations)
    report = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "source": "Live public HTTPS API and MCP -> managed identity -> Azure SQL",
        "status": "running",
        "operations": [],
        "checks": [],
    }

    def check(name, passed, evidence=None):
        item = {"name": name, "passed": bool(passed)}
        if evidence is not None:
            item["evidence"] = evidence
        report["checks"].append(item)
        print(json.dumps(item), flush=True)
        assert passed, name

    try:
        matches = service.matches()
        check(
            "Default dashboard catalogue contains ten distinct real games",
            {900011, 900012, *range(900101, 900109)}.issubset(
                {m["id"] for m in matches}
            )
            and len(matches) >= 10,
            {"match_ids": [m["id"] for m in matches]},
        )
        context = operations.execute("get_match_context", {"match_id": 900011})["data"]
        first_pass = operations.execute("get_passes", {"match_id": 900011, "limit": 1})[
            "data"
        ]["items"][0]
        first_shot = operations.execute("get_shots", {"match_id": 900011, "limit": 1})[
            "data"
        ]["items"][0]
        # The legacy case builder only reads height to choose a reference pass;
        # its placeholder here never enters a request or a stored source row.
        cases = verification_cases(
            {
                "event_passes": [
                    {"event_id": first_pass["event_id"], "height": {"id": 1}}
                ],
                "event_shots": [{"event_id": first_shot["event_id"]}],
                "event_index": {
                    first_pass["event_id"]: {"team_id": first_pass["team_id"]}
                },
            }
        )
        home, away = context["match"]["home_team_id"], context["match"]["away_team_id"]
        for operation, original in cases.items():
            args = dict(original)
            if "match_id" in args:
                args["match_id"] = 900011
            if "match_ids" in args:
                args["match_ids"] = [900011]
            if args.get("team_id") in (1, 2):
                args["team_id"] = home if args["team_id"] == 1 else away
            if "player_id" in args:
                args["player_id"] = first_pass["player_id"]
            if "entity_ids" in args:
                args["entity_ids"] = [home, away]
            if operation == "get_rankings":
                args.update(metric="completed_passes", profile_id="passing")
            if operation == "find_entities":
                args["name"] = "M1 Jugador"
            if operation == "get_passes":
                args.pop("height", None)
            try:
                result = operations.execute(operation, args)
            except DataError as error:
                if error.status == 422 and operation in (
                    "get_pass_corridor",
                    "get_line_breaks",
                    "get_defensive_profile",
                ):
                    report["operations"].append(
                        {
                            "operation": operation,
                            "passed": True,
                            "status": 422,
                            "expected_limitation": "Unavailable source fields or incomplete real tracking; no invented result",
                            "arguments": args,
                        }
                    )
                    print(json.dumps(report["operations"][-1]), flush=True)
                    continue
                raise
            report["operations"].append(
                {"operation": operation, "passed": True, "arguments": args}
            )
            if operation not in ("describe_dataset", "find_entities", "list_matches"):
                assert result["provenance"]["is_synthetic"] is False
            if operation == "get_team_summary":
                check(
                    "Real xG is null, never a fabricated zero",
                    result["data"]["aggregate"]["xg"] is None,
                )
            print(json.dumps({"operation": operation, "passed": True}), flush=True)
            await asyncio.sleep(0.7)
        source_report = json.loads(
            (ROOT / "database/azure-sql/skillcorner-quality-report.json").read_text()
        )
        counts = [(900011, 799), (900012, 964)] + [
            (m["match_id"], m["counts"]["event_passes"])
            for m in source_report["reports"]
        ]
        for mid, passes in counts:
            result = operations.execute("get_passes", {"match_id": mid, "limit": 1})
            check(
                f"Game {mid} preserves source pass row count",
                result["data"]["total"] == passes,
            )
            result = operations.execute(
                "get_tracking_window",
                {
                    "match_id": mid,
                    "sample_step_ms": 200,
                    "scope": {
                        "kind": "window",
                        "period": 1,
                        "start_ms": 0,
                        "end_ms": 10000,
                    },
                },
            )
            frames = result["data"]["frames"]
            check(
                f"Game {mid}: 10 seconds contains 50 original observations",
                [f["period_time_ms"] for f in frames] == list(range(0, 10000, 200)),
            )
            check(
                f"Game {mid} has explicit real provenance",
                result["provenance"]["is_synthetic"] is False,
            )
        episode = service.episode(900011, 1, 0, duration_seconds=300)
        check(
            "Five-minute viewer window keeps all 1500 real samples",
            len(episode["frames"]) == 1500
            and episode["window"]["endMs"] - episode["window"]["startMs"] == 300000,
        )
        check(
            "Viewer identifies the real provider",
            episode["dataKind"] == "real_anonymized"
            and episode["provider"] == "Metrica Sports",
        )
        check(
            "Ball gaps remain missing",
            any(f["ball"] is None for f in episode["frames"]),
        )
        episode_sc = service.episode(900101, 1, 0, duration_seconds=300)
        check(
            "SkillCorner viewer keeps 1500 samples and pseudonymized provenance",
            len(episode_sc["frames"]) == 1500
            and episode_sc["window"]["endMs"] == 300000
            and episode_sc["provider"] == "SkillCorner"
            and episode_sc["dataKind"] == "real_pseudonymized",
        )
        async with connect_data_mcp(
            DataMcpSettings(config.api_url + "/mcp", config.api_key)
        ) as client:
            result = await client.call_tool(
                "get_tracking_frame",
                {"match_id": 900011, "period": 1, "time_ms": 200},
            )
            payload = result.structured_content or json.loads(
                next(c.text for c in result.content if c.type == "text")
            )
            check(
                "MCP accepts real provenance and subsecond tracking",
                not result.is_error
                and payload["provenance"]["is_synthetic"] is False
                and payload["data"]["frames"][0]["period_time_ms"] == 200,
            )
            result = await client.call_tool(
                "get_tracking_frame",
                {"match_id": 900108, "period": 1, "time_ms": 200},
            )
            payload = result.structured_content or json.loads(
                next(c.text for c in result.content if c.type == "text")
            )
            check(
                "MCP serves the tenth real game without synthetic provenance",
                not result.is_error
                and payload["provenance"]["is_synthetic"] is False
                and payload["data"]["frames"][0]["period_time_ms"] == 200,
            )
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        (ROOT / "docs/metrica-service-verification.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    asyncio.run(verify())
