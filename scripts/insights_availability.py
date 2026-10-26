"""Matriz de disponibilidad: 30 recetas × partido, con evidencia real de la API.

No ejecuta modelos. Las consultas las decide el resolvedor del agente de
insights; cada receta se compila con el mismo `compile_report` que usa el MCP.
Después prueba las plantillas con el perfil de fuente aplicado. El resultado
indica qué puede mostrar el agente para cada fuente y por qué no.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

from inside_game.agents.insights_agent.profiles import PROFILE_FILE, build_profiles
from inside_game.agents.insights_agent.resolver import Resolver
from inside_game.agents.insights_agent.templates import PACKAGES
from inside_game.dashboard.config import DashboardConfig
from inside_game.insights.catalog import RECIPES
from inside_game.insights.pages import compile_report, render_report
from inside_game.tools.evidence_client import EvidenceClient, HttpTransport

# Uno por fuente: sintético, Metrica real anonimizado, SkillCorner seudonimizado.
DEFAULT_MATCHES = [900001, 900011, 900101]


async def execute(data, plan):
    """Ejecuta las consultas del plan; devuelve bloques del manifiesto y errores."""
    results = await data.run(plan.queries)
    operations = {q.key: q.operation for q in plan.queries}
    blocks = []
    for block in plan.blocks:
        evidence_ids = list(
            dict.fromkeys(i for k in block.query_keys for i in results[k][0])
        )
        errors = [
            f"{operations[k]}: {results[k][1]}"
            for k in block.query_keys
            if results[k][1]
        ]
        blocks.append(
            (
                {
                    "id": block.id,
                    "insight_id": block.insight_id,
                    "title": block.title,
                    "evidence_ids": evidence_ids,
                    "parameters": block.parameters,
                },
                errors,
            )
        )
    return blocks


def counts(block):
    fields = ("points", "vectors", "series", "rows", "polygons", "frames")
    return {f: len(getattr(block, f)) for f in fields if getattr(block, f)}


def compile_one(data, block, api_errors):
    row = {"api_errors": api_errors, "evidence_pages": len(block["evidence_ids"])}
    if not block["evidence_ids"]:
        row.update(state="no_evidence", reasons=api_errors or ["Sin evidencia."])
        return row
    evidence = [data.evidence[i] for i in block["evidence_ids"]]
    try:
        _, (compiled,) = compile_report({"blocks": [block], "evidence": evidence})
    except ValueError as exc:
        row.update(state="spec_rejected", reasons=[str(exc)[:300]])
        return row
    inherited = {w for e in evidence for w in e["response"]["warnings"]}
    reasons = [w for w in compiled.warnings if w not in inherited]
    row.update(
        state=compiled.state,
        reasons=reasons + api_errors,
        warnings=compiled.warnings,
        metrics={k: compiled.metrics[k] for k in list(compiled.metrics)[:12]},
        items=counts(compiled),
    )
    return row


def pick_player(data, plan):
    """Un medio (o defensor) del equipo protagonista, por posición de la fuente."""
    roles = plan.decisions["roles_by_team"][str(plan.focus_team_id)]
    for group in ("midfielder_ids", "defender_ids"):
        if roles.get(group):
            return roles[group][0]
    context = next(
        e for e in data.evidence.values() if e["operation"] == "get_match_context"
    )["response"]["data"]
    goalkeeper = roles.get("goalkeeper_id")
    return next(
        row["player_id"]
        for row in context["lineups"]
        if row["team_id"] == plan.focus_team_id and row["player_id"] != goalkeeper
    )


async def matrix(data, match_id):
    """Las 30 recetas sin filtrar por perfil: mide la fuente."""
    resolver = Resolver(data.fetch, apply_profile=False)
    plan = await resolver.resolve(
        {
            "template_id": "custom_report",
            "match_id": match_id,
            "period": 1,
            "insight_ids": list(RECIPES),
        }
    )
    rows = {
        d.insight_id: {
            "state": "unavailable",
            "reasons": [f"Resolvedor: {d.reason}"],
            "api_errors": [],
            "evidence_pages": 0,
        }
        for d in plan.discarded
    }
    blocks = []
    for block, api_errors in await execute(data, plan):
        rows[block["insight_id"]] = compile_one(data, block, api_errors)
        if rows[block["insight_id"]]["state"] not in {"no_evidence", "spec_rejected"}:
            blocks.append(block)
    return plan, {k: rows[k] for k in RECIPES}, blocks


async def templates(data, match_id, profiles, player_id, folder):
    """Cada plantilla con el perfil aplicado, como la usará el agente."""
    resolver = Resolver(data.fetch, profiles=profiles)
    results = {}
    for template_id in PACKAGES:
        intent = {"template_id": template_id, "match_id": match_id}
        if template_id == "player_dossier":
            intent["player_id"] = player_id
        plan = await resolver.resolve(intent)
        blocks = [b for b, _ in await execute(data, plan) if b["evidence_ids"]]
        used = {i for b in blocks for i in b["evidence_ids"]}
        result = {
            "discarded": [d.model_dump() for d in plan.discarded],
            "decisions": plan.decisions,
        }
        try:
            page = render_report(
                {
                    "title": f"{template_id} · {match_id}",
                    "template_id": template_id,
                    "blocks": blocks,
                    "evidence": [data.evidence[i] for i in used],
                }
            )
        except ValueError as exc:
            result["page_error"] = str(exc)[:300]
        else:
            name = f"{template_id}-{match_id}.html"
            (folder / name).write_text(page["html"], encoding="utf-8")
            result["page"] = name
            result["blocks"] = {
                b["id"]: {"state": b["state"], "warnings": b["warnings"]}
                for b in page["blocks"]
            }
        results[template_id] = result
    return results


async def run(match_ids, folder):
    config = DashboardConfig.load(Path(__file__).resolve().parents[1])
    report = {"llm_used": False, "matches": []}
    clients = {}
    async with httpx.AsyncClient(
        base_url=config.api_url,
        headers={"Authorization": f"Bearer {config.api_key}"},
        timeout=120,
        follow_redirects=False,
        trust_env=False,
    ) as http:
        # Un transporte compartido mantiene el ritmo global por debajo del límite.
        transport = HttpTransport(http)
        for match_id in match_ids:
            started = time.perf_counter()
            data = clients[match_id] = EvidenceClient(transport)
            plan, rows, blocks = await matrix(data, match_id)
            context = next(
                e
                for e in data.evidence.values()
                if e["operation"] == "get_match_context"
            )["response"]
            match = context["data"]["match"]
            report["matches"].append(
                {
                    "match_id": match_id,
                    "label": f"{match['home_team_name']} vs {match['away_team_name']}",
                    "competition": match["competition_name"],
                    "is_synthetic": match["is_synthetic"],
                    "provider": match.get("provider"),
                    "provenance": context["provenance"],
                    "decisions": plan.decisions,
                    "api_seconds": round(time.perf_counter() - started, 1),
                    "api_queries": len(data.queries),
                    "insights": rows,
                }
            )
            print(match_id, {k: v["state"] for k, v in rows.items()}, flush=True)
            page = render_report(
                {
                    "title": f"Disponibilidad de insights · {match_id}",
                    "blocks": blocks,
                    "evidence": [
                        data.evidence[i]
                        for i in dict.fromkeys(
                            i for b in blocks for i in b["evidence_ids"]
                        )
                    ],
                }
            )
            (folder / f"match-{match_id}.html").write_text(
                page["html"], encoding="utf-8"
            )
        profiles = build_profiles(report)
        for entry in report["matches"]:
            data = clients[entry["match_id"]]
            plan = await Resolver(data.fetch, apply_profile=False).resolve(
                {
                    "template_id": "custom_report",
                    "match_id": entry["match_id"],
                    "insight_ids": ["shot_map"],
                }
            )
            entry["templates"] = await templates(
                data, entry["match_id"], profiles, pick_player(data, plan), folder
            )
    report["profiles"] = profiles
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id", type=int, action="append")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".temp/insights/availability")
    )
    parser.add_argument(
        "--write-profiles",
        action="store_true",
        help="Actualiza los perfiles de fuente del agente con esta matriz.",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(run(args.match_id or DEFAULT_MATCHES, args.output_dir))
    (args.output_dir / "availability.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    if args.write_profiles:
        PROFILE_FILE.write_text(
            json.dumps(report["profiles"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
