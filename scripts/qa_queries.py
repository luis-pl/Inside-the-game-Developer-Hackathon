"""QA de consultas reales: TCP HTTP y MCP, sin modificar datos de Azure SQL.

Ejecutar con la API (8000) y el MCP HTTP (8001) activos:
    python scripts/qa_queries.py

Contrasta respuestas con eventos detallados y reglas de negocio, además del
estado HTTP. Recorre los diez partidos sintéticos y guarda evidencia en docs/.
Las variables INSIDE_GAME_* configuran el destino y la clave de la API.
"""

import asyncio
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from inside_game.mcp_server import McpSettings

ROOT = Path(__file__).resolve().parents[1]


class QueryQA:
    def __init__(self):
        self.settings = McpSettings.from_env()
        self.last_call = 0
        self.report = {
            "tested_at_utc": datetime.now(UTC).isoformat(),
            "source": "Live TCP API and both MCP transports against synthetic Azure SQL data",
            "status": "running",
            "queries": [],
            "checks": [],
        }

    def check(self, label, passed, evidence=None):
        item = {"label": label, "passed": bool(passed)}
        if evidence is not None:
            item["evidence"] = evidence
        self.report["checks"].append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)

    async def query(self, name, args, expected=200):
        # Mantiene margen bajo el límite de 120 solicitudes/minuto de la API.
        await asyncio.sleep(max(0, 0.8 - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()
        response = await self.http.post("/api/operations/" + name, json=args)
        self.report["queries"].append(
            {
                "operation": name,
                "arguments": args,
                "status_code": response.status_code,
                "expected_status": expected,
            }
        )
        if response.status_code != expected:
            raise AssertionError(
                f"Unexpected HTTP status for {name}: {response.status_code}, expected {expected}"
            )
        payload = response.json()
        if expected == 200:
            assert payload["provenance"]["is_synthetic"] is True
            assert payload["operation_id"] == name
            assert payload["warnings"] and payload["coordinates"]
        return payload

    async def rows(self, name, args):
        """Sigue cursores y comprueba que la paginación no altere el total."""
        records, cursor, seen, total, last = [], None, set(), None, None
        for _ in range(100):
            last = await self.query(
                name, {**args, **({"cursor": cursor} if cursor else {})}
            )
            current = last["data"]
            total = current["total"] if total is None else total
            assert current["total"] == total
            records.extend(current["items"])
            cursor = last["pagination"].get("next_cursor")
            if not cursor:
                assert len(records) == total
                return records, last
            assert cursor not in seen
            seen.add(cursor)
        raise AssertionError("Pagination did not terminate")

    async def business_queries(self):
        catalog = (await self.query("list_matches", {}))["data"]["items"]
        self.check(
            "Están disponibles los diez partidos auditados",
            {m["match_id"] for m in catalog} == set(range(900001, 900011)),
        )
        shot_sets, shot_total, pass_total, substitution_total = {}, 0, 0, 0
        for match in catalog:
            mid = match["match_id"]
            shots, response = await self.rows(
                "get_shots", {"match_id": mid, "limit": 200}
            )
            shot_sets[mid] = shots
            ids = [s["event_id"] for s in shots]
            summary = response["data"]["summary"]
            self.check(
                f"{mid}: tiros únicos y total completo",
                len(ids) == len(set(ids)) == summary["shots"],
                len(ids),
            )
            xg = math.fsum(s["shot"]["statsbomb_xg"] for s in shots)
            self.check(
                f"{mid}: xG agregado coincide con tiros detallados",
                math.isclose(xg, summary["xg"], abs_tol=1e-10),
                xg,
            )
            self.check(
                f"{mid}: marcador coincide con goles por equipo",
                all(
                    sum(
                        s["shot"]["outcome"]["id"] == 97
                        and s["team_id"] == match[side + "_team_id"]
                        for s in shots
                    )
                    == match[side + "_score"]
                    for side in ("home", "away")
                ),
            )
            self.check(
                f"{mid}: ubicaciones, períodos y xG válidos",
                all(
                    0 <= s["location_x"] <= 120
                    and 0 <= s["location_y"] <= 80
                    and s["period"] in (1, 2)
                    and 0 <= s["period_time_ms"] < 2700000
                    and 0 <= s["shot"]["statsbomb_xg"] <= 1
                    for s in shots
                ),
            )
            passes = (
                await self.query("get_passes", {"match_id": mid, "view": "summary"})
            )["data"]
            subs = (await self.query("get_substitutions", {"match_id": mid}))["data"]
            self.check(
                f"{mid}: seis cambios sin autorreemplazos",
                subs["total"] == 6
                and all(
                    s["player_id"] != s["replacement"]["id"] for s in subs["items"]
                ),
            )
            shot_total += len(shots)
            pass_total += passes["total"]
            substitution_total += subs["total"]
            if mid == 900001:
                first_sub = subs["items"][0]
        self.check(
            "Totales auditados de los diez partidos",
            (shot_total, pass_total, substitution_total) == (209, 5752, 60),
            {
                "shots": shot_total,
                "passes": pass_total,
                "substitutions": substitution_total,
            },
        )

        shots = shot_sets[900001]

        def event_ids(rows):
            return {r["event_id"] for r in rows}

        for team in (1, 2):
            result = (
                await self.query("get_shots", {"match_id": 900001, "team_id": team})
            )["data"]
            self.check(
                f"Filtro de tiros del equipo {team}",
                event_ids(result["items"])
                == event_ids([s for s in shots if s["team_id"] == team]),
            )
        for period in (1, 2):
            result = (
                await self.query(
                    "get_shots",
                    {"match_id": 900001, "scope": {"kind": "period", "period": period}},
                )
            )["data"]
            self.check(
                f"Filtro de tiros del período {period}",
                event_ids(result["items"])
                == event_ids([s for s in shots if s["period"] == period]),
            )
        on_target = (
            await self.query(
                "get_shots", {"match_id": 900001, "team_id": 1, "outcome": "on_target"}
            )
        )["data"]
        expected = [
            s
            for s in shots
            if s["team_id"] == 1 and s["shot"]["outcome"]["id"] in (97, 100, 116)
        ]
        self.check(
            "Cuántos, cuándo y dónde: seis tiros a puerta del equipo 1",
            on_target["total"] == 6
            and event_ids(on_target["items"]) == event_ids(expected),
        )
        pages, _ = await self.rows("get_shots", {"match_id": 900001, "limit": 5})
        self.check(
            "Paginación de tiros conserva todos los eventos sin duplicarlos",
            len(pages) == len(event_ids(pages)) == 23
            and event_ids(pages) == event_ids(shots),
        )
        timeline = (
            await self.query("get_shots", {"match_id": 900001, "view": "timeline"})
        )["data"]
        self.check(
            "La cronología conserva tiros y xG",
            sum(b["metrics"]["shots"] for b in timeline["series"]) == len(shots)
            and math.isclose(
                sum(b["metrics"]["xg"] for b in timeline["series"]),
                math.fsum(s["shot"]["statsbomb_xg"] for s in shots),
                abs_tol=1e-10,
            ),
        )
        heat = (
            await self.query(
                "get_heatmap",
                {
                    "match_id": 900001,
                    "team_id": 1,
                    "mode": "event_count",
                    "event_type": "shot",
                },
            )
        )["data"]
        self.check(
            "Mapa de tiros del equipo conserva el número de eventos",
            sum(c["events"] for c in heat["cells"])
            == sum(s["team_id"] == 1 for s in shots),
        )
        passes, response = await self.rows(
            "get_passes", {"match_id": 900001, "limit": 200}
        )
        self.check(
            "Paginación de pases conserva los 576 IDs únicos",
            len(passes) == len(event_ids(passes)) == 576,
        )
        for outcome in ("complete", "incomplete"):
            selected = (
                await self.query(
                    "get_passes",
                    {"match_id": 900001, "outcome": outcome, "view": "summary"},
                )
            )["data"]
            expected_count = sum(
                (p["pass"]["outcome"] is None) == (outcome == "complete")
                for p in passes
            )
            self.check(
                f"Filtro de pases {outcome}",
                selected["total"] == expected_count,
                expected_count,
            )
        for height, code in (("ground", 1), ("low", 2), ("high", 3)):
            selected = (
                await self.query(
                    "get_passes",
                    {"match_id": 900001, "height": height, "view": "summary"},
                )
            )["data"]
            self.check(
                f"Filtro de altura {height}",
                selected["total"]
                == sum(p["pass"]["height"]["id"] == code for p in passes),
            )
        pressures = (
            await self.query(
                "get_defensive_actions",
                {"match_id": 900001, "kind": "pressure", "view": "summary"},
            )
        )["data"]
        self.check("249 presiones consultables", pressures["total"] == 249)
        aerial = (
            await self.query(
                "get_defensive_actions", {"match_id": 900001, "kind": "aerial_duel"}
            )
        )["data"]
        self.check(
            "Nueve duelos aéreos sin duplicar enfrentamientos",
            aerial["total"] == 9
            and len({r["contest_id"] for r in aerial["items"]}) == 9,
        )
        tackle_counts = []
        for outcome in ("all", "won", "lost"):
            data = (
                await self.query(
                    "get_defensive_actions",
                    {
                        "match_id": 900001,
                        "kind": "tackle",
                        "outcome": outcome,
                        "view": "summary",
                    },
                )
            )["data"]
            tackle_counts.append(data["total"])
        self.check(
            "Entradas ganadas y perdidas particionan los intentos",
            tackle_counts[0] == sum(tackle_counts[1:]),
            tackle_counts,
        )
        for kind in ("dribble", "carry"):
            data = (
                await self.query(
                    "get_ball_actions",
                    {"match_id": 900001, "kind": kind, "view": "summary"},
                )
            )["data"]
            self.check(
                f"Hay datos consultables de {kind}",
                data["total"] == 77 if kind == "dribble" else data["total"] > 0,
                data["total"],
            )

        scope = {"kind": "window", "period": 1, "start_ms": 600000, "end_ms": 603000}
        tracking = (
            await self.query(
                "get_tracking_window", {"match_id": 900001, "scope": scope}
            )
        )["data"]["frames"]
        self.check(
            "Ventana temporal semiabierta: tres segundos, sin incluir el extremo final",
            [f["period_time_ms"] for f in tracking] == [600000, 601000, 602000],
        )
        self.check(
            "Tracking: 22 jugadores únicos dentro del campo por frame",
            all(
                len(f["players"]) == len({p["player_id"] for p in f["players"]}) == 22
                and all(
                    0 <= p["x_m"] <= 105 and 0 <= p["y_m"] <= 68 for p in f["players"]
                )
                for f in tracking
            ),
        )
        occupancy = (
            await self.query(
                "get_heatmap",
                {"match_id": 900001, "team_id": 1, "mode": "occupancy_seconds"},
            )
        )["data"]
        self.check(
            "Mapa de ocupación: once jugadores por 90 minutos",
            math.isclose(occupancy["total_player_seconds"], 11 * 5400),
            occupancy["total_player_seconds"],
        )
        # La carga 3.0.0 anota el evento con el saliente todavía activo y
        # transfiere la posición al reemplazo en la muestra del segundo siguiente.
        # Contrato documentado en database/azure-sql/DATA-QUALITY.md.
        context = (await self.query("get_match_context", {"match_id": 900001}))["data"]
        old, new = first_sub["player_id"], first_sub["replacement"]["id"]
        outgoing = next(
            p for p in context["position_intervals"] if p["player_id"] == old
        )
        incoming = next(
            p for p in context["position_intervals"] if p["player_id"] == new
        )
        minutes, seconds = map(int, incoming["from_time"].split(":"))
        prior_period_ms = sum(
            p["duration_ms"]
            for p in context["periods"]
            if p["period"] < first_sub["period"]
        )
        effective_ms = (minutes * 60 + seconds) * 1000 - prior_period_ms
        self.check(
            "Intervalos del cambio: continuidad y entrada efectiva al segundo siguiente",
            outgoing["to_time"] == incoming["from_time"]
            and effective_ms == first_sub["period_time_ms"] + 1000,
            {
                "event_time_ms": first_sub["period_time_ms"],
                "effective_time_ms": effective_ms,
            },
        )
        before_after = []
        for delta in (-1000, 0):
            frame = (
                await self.query(
                    "get_tracking_frame",
                    {
                        "match_id": 900001,
                        "period": first_sub["period"],
                        "time_ms": effective_ms + delta,
                    },
                )
            )["data"]["frames"][0]
            before_after.append({p["player_id"] for p in frame["players"]})
        self.check(
            "Sustitución: tracking respeta los intervalos efectivos de participación",
            old in before_after[0]
            and new not in before_after[0]
            and old not in before_after[1]
            and new in before_after[1]
            and len(before_after[1]) == 22,
        )
        spatial = (
            await self.query(
                "get_space_coverage",
                {"match_id": 900001, "team_id": 1, "period": 1, "time_ms": 600000},
            )
        )["data"]
        self.check(
            "Voronoi cubre los 7140 m² del campo",
            math.isclose(
                spatial["samples"][0]["result"]["area_sum_m2"], 7140, abs_tol=1e-6
            ),
        )

        invalid_cases = [
            ("get_shots", {"match_id": 900001, "sql": "SELECT 1"}, 422),
            ("get_shots", {"match_id": 900001, "limit": 201}, 422),
            ("get_shots", {"match_id": 900001, "team_id": 99999}, 422),
            ("get_shots", {"match_id": 900099}, 404),
            (
                "get_shots",
                {
                    "match_id": 900001,
                    "scope": {
                        "kind": "window",
                        "period": 1,
                        "start_ms": 2000,
                        "end_ms": 1000,
                    },
                },
                422,
            ),
            (
                "get_tracking_frame",
                {"match_id": 900001, "period": 1, "time_ms": 500},
                422,
            ),
            ("execute_query", {"sql": "SELECT 1"}, 404),
        ]
        for name, args, status in invalid_cases:
            await self.query(name, args, expected=status)
        self.check(
            "Se rechazan SQL, filtros inválidos, tiempos imposibles y operaciones no registradas",
            True,
            len(invalid_cases),
        )
        page = await self.query("get_shots", {"match_id": 900001, "limit": 5})
        cursor = page["pagination"]["next_cursor"]
        await self.query(
            "get_shots",
            {"match_id": 900001, "limit": 5, "team_id": 1, "cursor": cursor},
            expected=422,
        )
        self.check("Un cursor no permite cambiar los filtros de la consulta", True)

    async def protocol_parity(self):
        """La comparación ignora request_id y cursores, que dependen de la llamada."""
        cases = [
            (
                "get_shots",
                {
                    "match_id": 900001,
                    "team_id": 1,
                    "outcome": "on_target",
                    "view": "summary",
                },
            ),
            ("get_passes", {"match_id": 900001, "view": "summary"}),
            (
                "get_defensive_actions",
                {"match_id": 900001, "kind": "aerial_duel", "view": "summary"},
            ),
            (
                "get_tracking_frame",
                {"match_id": 900001, "period": 1, "time_ms": 600000},
            ),
        ]
        stdio = StdioServerParameters(
            command=sys.executable,
            args=["-m", "inside_game.mcp_server"],
            cwd=ROOT,
            env={k: v for k, v in os.environ.items() if k.startswith("INSIDE_GAME_")},
        )
        for transport, target in (
            ("stdio", stdio),
            ("streamable-http", "http://127.0.0.1:8001/mcp"),
        ):
            async with Client(target, read_timeout_seconds=45) as client:
                for name, args in cases:
                    api = await self.query(name, args)
                    result = await client.call_tool(name, args)
                    payload = result.structured_content
                    fields = (
                        "operation_id",
                        "method_id",
                        "scope",
                        "data",
                        "provenance",
                        "coverage",
                        "coordinates",
                        "warnings",
                    )
                    self.check(
                        f"Paridad API/MCP {transport}: {name}",
                        not result.is_error
                        and payload is not None
                        and all(api[f] == payload[f] for f in fields),
                    )

    async def run(self):
        headers = (
            {"Authorization": "Bearer " + self.settings.api_key}
            if self.settings.api_key
            else {}
        )
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.api_url,
                headers=headers,
                timeout=40,
                trust_env=False,
            ) as self.http:
                await self.business_queries()
                await self.protocol_parity()
        except (
            AssertionError,
            httpx.HTTPError,
            RuntimeError,
            KeyError,
            IndexError,
        ) as exc:
            self.check(
                "La ejecución completa finaliza sin errores",
                False,
                {
                    "type": type(exc).__name__,
                    "message": str(exc)
                    if isinstance(exc, AssertionError)
                    else "See failed query or check",
                },
            )
        self.report["status"] = (
            "passed"
            if self.report["checks"] and all(c["passed"] for c in self.report["checks"])
            else "failed"
        )
        (ROOT / "docs" / "query-qa-report.json").write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": self.report["status"],
                    "queries": len(self.report["queries"]),
                    "checks": len(self.report["checks"]),
                }
            ),
            flush=True,
        )
        if self.report["status"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(QueryQA().run())
