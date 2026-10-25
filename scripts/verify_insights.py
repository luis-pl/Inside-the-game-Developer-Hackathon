"""QA de las 30 recetas y exportación real opcional, sin LLM ni acceso de red.

Separa el fixture ilustrativo de los resultados reales del agente. Guarda HTML,
manifiestos y mediciones reproducibles; no lee credenciales ni modifica SQL.
"""

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from inside_game.insights.demo import demo_manifest
from inside_game.insights.mcp_server import create_server
from inside_game.insights.pages import render_report


async def mcp_check(manifest, evidence_file=None):
    plan = {k: v for k, v in manifest.items() if k != "evidence"}
    target = (
        StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "inside_game.insights.mcp_server",
                "--evidence-file",
                str(evidence_file.resolve()),
            ],
        )
        if evidence_file
        else create_server(manifest["evidence"])
    )
    async with Client(target) as client:
        discovered = await client.list_tools()
        validated = await client.call_tool("validate_report", plan)
        pieces = {}
        for block in plan["blocks"]:
            piece = await client.call_tool("render_insight", block)
            if piece.is_error:
                pieces[block["insight_id"]] = False
                continue
            resource = await client.read_resource(
                piece.structured_content["resource_uri"]
            )
            pieces[block["insight_id"]] = (
                resource.contents[0].text.startswith("<!doctype html>")
                and piece.structured_content["blocks"][0]["state"] == "ready"
            )
        rendered = await client.call_tool("render_report", plan)
        if rendered.is_error:
            return {"passed": False}
        data = rendered.structured_content
        resource = await client.read_resource(data["resource_uri"])
        return {
            "passed": not validated.is_error
            and validated.structured_content["ready"]
            and all(pieces.values())
            and len(discovered.tools) == 5
            and resource.contents[0].text.startswith("<!doctype html>"),
            "tools": len(discovered.tools),
            "transport": "stdio subprocess" if evidence_file else "in-process",
            "individual_pieces": pieces,
            "bytes": data["bytes"],
            "states": {b["id"]: b["state"] for b in data["blocks"]},
        }


def verify(args):
    folder = args.output_dir
    folder.mkdir(parents=True, exist_ok=True)
    fixture = demo_manifest()
    measurements = []
    for _ in range(10):
        result = render_report(fixture)
        measurements.append(result["render_ms"])
    (folder / "gallery.html").write_text(result["html"], encoding="utf-8")
    (folder / "gallery.manifest.json").write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = {
        "llm_used": False,
        "network_used": False,
        "gallery_source": "Explicit synthetic UI fixture, not a World Cup match or Azure synthetic dataset",
        "family_count": len(result["blocks"]),
        "fixture_states": {b["id"]: b["state"] for b in result["blocks"]},
        "benchmark": {
            "iterations": 10,
            "scope": "warm renderer only, not model/network/SQL",
            "p50_ms": statistics.median(measurements),
            "p95_ms": sorted(measurements)[9],
            "bytes": result["bytes"],
        },
        "mcp": asyncio.run(
            mcp_check(fixture, folder / "gallery.manifest.json" if args.stdio else None)
        ),
    }
    if args.data_result:
        evidence = []
        for i, path in enumerate(args.data_result):
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            for original in payload["evidence"]:
                item = {
                    **original,
                    "evidence_id": f"r{i}-{original['evidence_id']}",
                    "query_id": f"r{i}-{original['query_id']}",
                }
                evidence.append(item)
        by_op = {
            op: [e["evidence_id"] for e in evidence if e["operation"] == op]
            for op in {e["operation"] for e in evidence}
        }
        blocks = []
        if by_op.get("get_shots"):
            blocks.append(
                {
                    "id": "shots",
                    "insight_id": "shot_map",
                    "evidence_ids": by_op["get_shots"],
                }
            )
        tracking = by_op.get("get_tracking_window") or by_op.get("get_tracking_frame")
        if tracking:
            blocks.append(
                {"id": "replay", "insight_id": "play_replay", "evidence_ids": tracking}
            )
            if args.team_id:
                for key in [
                    "topological_change",
                    "clearance_connectivity",
                    "defensive_line_height",
                ]:
                    blocks.append(
                        {
                            "id": key,
                            "insight_id": key,
                            "evidence_ids": tracking,
                            "parameters": {"team_id": args.team_id},
                        }
                    )
        manifest = {
            "title": "Datos del agente · procedencia conservada",
            "template_id": "tactical_episode",
            "blocks": blocks,
            "evidence": evidence,
        }
        result = render_report(manifest)
        (folder / "agent-report.html").write_text(result["html"], encoding="utf-8")
        (folder / "agent-report.manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report["agent_data"] = {
            "render_ms": result["render_ms"],
            "bytes": result["bytes"],
            "states": {b["id"]: b["state"] for b in result["blocks"]},
            "evidence_count": len(evidence),
        }
    report["passed"] = report["mcp"]["passed"] and all(
        state == "ready" for state in report["fixture_states"].values()
    )
    (folder / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(".temp/insights"))
    parser.add_argument("--data-result", type=Path, action="append")
    parser.add_argument("--team-id", type=int)
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Verifica el MCP como subproceso real, igual que un cliente de agente.",
    )
    options = parser.parse_args()
    raise SystemExit(0 if verify(options) else 1)
