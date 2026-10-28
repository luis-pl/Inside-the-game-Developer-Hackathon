"""Bounded live QA: selected free Go model, real agents/MCP/SQL, no billing changes.

Run with --live. Reports contain public codes, model usage and sports evidence,
never transport headers, authentication records or private model reasoning.
"""

import argparse
import asyncio
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from inside_game.agents.contracts import DataContext
from inside_game.agents.conversation_copy import concept_reply
from inside_game.agents.insights_http_client import PayloadParser
from inside_game.agents.interpreter import Interpreter
from inside_game.agents_cli import app_from_env, load_local_env
from inside_game.providers.models import (
    ModelFailure,
    create_model,
    model_settings_from_env,
)
from inside_game.tools.mcp_client import DataMcpSettings


def free_settings():
    load_local_env(Path(__file__).resolve().parents[1])
    settings = model_settings_from_env()
    if not (
        settings.provider == "opencode-go"
        and settings.deployment == "beam-free"
        and settings.free_only
        and settings.auth_mode == "cli_session"
    ):
        raise ValueError("QA_REQUIRES_EXPLICIT_FREE_ONLY_BEAM_GO")
    return settings


def save(folder, name, value):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def usage_numbers(value):
    if isinstance(value, dict):
        return {
            k: usage_numbers(v)
            for k, v in value.items()
            if isinstance(v, (dict, int, float)) and not isinstance(v, bool)
        }
    return value


class Meter:
    def __init__(self, folder=None):
        self.case = "preflight"
        self.spans = []
        self.folder = folder

    def factory(self):
        model = create_model(free_settings())
        post = model._post

        async def measured(path, body):
            started = time.perf_counter()
            raw_messages = body.get("messages", body.get("input", []))
            names = {
                t.get("name", t.get("function", {}).get("name"))
                for t in body.get("tools", [])
            }
            role = next(
                (
                    role
                    for name, role in (
                        ("delegate_request", "interpreter"),
                        ("finish_data_request", "data"),
                        ("finish_analysis", "analyst"),
                        ("render_report", "insights"),
                        ("submit_intent", "planner"),
                    )
                    if name in names
                ),
                "unknown",
            )
            span = {
                "case": self.case,
                "agent": role,
                "wire_bytes": len(
                    json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
                ),
                "message_bytes": len(
                    json.dumps(
                        raw_messages, ensure_ascii=False, separators=(",", ":")
                    ).encode()
                ),
                "schema_bytes": len(
                    json.dumps(
                        body.get("tools", []), ensure_ascii=False, separators=(",", ":")
                    ).encode()
                ),
                "message_count": len(raw_messages),
                "tool_count": len(names),
            }
            self.spans.append(span)
            try:
                result = await post(path, body)
                span["usage"] = usage_numbers(result.get("usage", {})) or None
                span["status"] = "ok"
                return result
            except ModelFailure as exc:
                span.update(status="error", issue=exc.code)
                raise
            finally:
                span["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
                if self.folder:
                    save(self.folder, "telemetry.json", self.spans)

        model._post = measured
        return model


@contextmanager
def local_agents(port, meter):
    import uvicorn

    origin = f"http://127.0.0.1:{port}"
    before = {
        key: os.environ.get(key)
        for key in ("INSIDE_GAME_DATA_AGENT_URL", "INSIDE_GAME_INSIGHTS_AGENT_URL")
    }
    for key in before:
        os.environ[key] = origin
    app = app_from_env(port, model_factory=meter.factory)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, access_log=False, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=origin, trust_env=False, timeout=1) as ready:
            for _ in range(100):
                if not thread.is_alive():
                    raise RuntimeError("QA_LOCAL_SERVER_FAILED")
                try:
                    if ready.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("QA_LOCAL_SERVER_START_TIMEOUT")
        yield origin
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


CHAT_CASES = [
    {
        "id": "structural-passes-es",
        "language": "es",
        "text": "Reconstruye la secuencia de pases de Spaces Athletic de los primeros veinte segundos del primer tiempo. Crea exactamente tres bloques: mapa de pases, structural_pass para relacionar los pases con posiciones de rivales y reproducción a 5 Hz. Recupera tracking de ambos equipos y usa la orientación del contexto para alinear coordenadas. Describe el orden pasador-receptor observado sin llamar control, presión o pase seguro a la cercanía geométrica.",
        "context": {
            "match_ids": [900011],
            "team_ids": [103],
            "scope": {"kind": "window", "period": 1, "start_ms": 0, "end_ms": 20000},
        },
        "recipes": ["pass_map", "structural_pass", "play_replay"],
    },
    {
        "id": "reconstruct-es",
        "language": "es",
        "text": "Reconstruye la jugada de Spaces Athletic en los primeros veinte segundos del primer tiempo: muestra exactamente un mapa de sus pases y una reproducción de las posiciones a 5 Hz en esa misma ventana. Explica en pocas palabras qué se puede observar, sin inventar presión, intención ni trayectorias del balón entre eventos.",
        "context": {
            "match_ids": [900011],
            "team_ids": [103],
            "scope": {"kind": "window", "period": 1, "start_ms": 0, "end_ms": 20000},
        },
        "recipes": ["pass_map", "play_replay"],
    },
    {
        "id": "reconstruct-en",
        "language": "en",
        "text": "Reconstruct Spaces Athletic's play in the first twenty seconds of the first half. Show exactly a pass map and a replay at 5 Hz for that same window. Explain the observed pass sequence briefly, preserving missing data and without inventing tactical intent.",
        "context": {
            "match_ids": [900011],
            "team_ids": [103],
            "scope": {"kind": "window", "period": 1, "start_ms": 0, "end_ms": 20000},
        },
        "recipes": ["pass_map", "play_replay"],
    },
    {
        "id": "synthetic-shots-xg",
        "language": "es",
        "text": "Muéstrame exactamente el mapa de tiros de ambos equipos y la evolución de su xG. Explica la diferencia entre volumen y calidad de ocasiones sin decir quién merecía ganar. Conserva la procedencia sintética.",
        "context": {"match_ids": [900001]},
        "recipes": ["shot_map", "xg_story"],
    },
    {
        "id": "missing-xg-pt",
        "language": "pt",
        "text": "Quero o xG deste jogo e o melhor jogador por xG. Se os dados não existirem, explique e ofereça uma alternativa, sem inventar valores nem criar um gráfico vazio.",
        "context": {"match_ids": [900011]},
        "no_report": True,
    },
    {
        "id": "two-instants-fr",
        "language": "fr",
        "text": "Compare la largeur de Tabs United à exactement dix minutes et à dix minutes une seconde de la première période. Crée exactement deux graphiques de forme de l'équipe, un par instant. Ne confonds pas deux observations avec une tendance de tout le match.",
        "context": {
            "match_ids": [900011],
            "team_ids": [102],
            "scope": {
                "kind": "window",
                "period": 1,
                "start_ms": 600000,
                "end_ms": 602000,
            },
        },
        "recipes": ["team_shape", "team_shape"],
    },
    {
        "id": "ambiguous-episode-it",
        "language": "it",
        "text": "Ricostruisci quella giocata e mostrami i passaggi.",
        "context": {},
        "no_report": True,
    },
    {
        "id": "second-half-network-de",
        "language": "de",
        "text": "Zeige genau ein schematisches Passnetz von Spaces Athletic zwischen Sekunde zehn und zwanzig der zweiten Halbzeit. Verwende nur abgeschlossene Pässe in diesem Zeitfenster und erkläre kurz die Grenzen der Beobachtung.",
        "context": {
            "match_ids": [900011],
            "team_ids": [103],
            "scope": {
                "kind": "window",
                "period": 2,
                "start_ms": 10000,
                "end_ms": 20000,
            },
        },
        "recipes": ["passing_network"],
    },
]


def check_report(case, state, payload, plan):
    checks = {
        "finished_without_error": state["stage"]
        in {"complete", "partial", "clarification"},
        "language": state.get("language") == case["language"],
    }
    if case.get("no_report"):
        checks["no_invented_report"] = not state.get("report")
        return checks
    checks["has_report"] = bool(state.get("report"))
    if payload is None:
        checks["recipes"] = False
        return checks
    blocks = payload.get("blocks", [])
    checks["recipes"] = sorted(b["insight_id"] for b in blocks) == sorted(
        case["recipes"]
    )
    checks["ready_blocks"] = bool(blocks) and all(
        b["state"] in {"ready", "empty_with_coverage"} for b in blocks
    )
    selected = {i for b in blocks for i in b.get("evidence_ids", [])}
    evidence = [e for e in payload.get("evidence", []) if e["evidence_id"] in selected]
    context = case["context"]
    checks["same_match"] = all(
        e["arguments"].get("match_id", context["match_ids"][0]) in context["match_ids"]
        for e in evidence
    )
    checks["provenance_preserved"] = bool(evidence) and all(
        "is_synthetic" in e["response"]["provenance"] for e in evidence
    )
    expected = context.get("scope")
    if expected:
        scoped = [e for e in evidence if "scope" in e["arguments"]]
        if case["id"] == "two-instants-fr":
            observed = {
                s["time_ms"]
                for e in evidence
                if e["operation"] == "get_team_shape"
                for s in e["response"]["data"].get("samples", [])
            }
            checks["same_window"] = observed == {600000, 601000}
        else:
            checks["same_window"] = bool(scoped) and all(
                e["arguments"]["scope"] == expected for e in scoped
            )
    if "play_replay" in case["recipes"]:
        frames = [
            f
            for b in blocks
            if b["insight_id"] == "play_replay"
            for f in b.get("frames", [])
        ]
        checks["observed_frames"] = len(frames) == 100
        checks["tracking_5hz"] = any(
            e["operation"] == "get_tracking_window"
            and e["arguments"].get("sample_step_ms") == 200
            for e in evidence
        )
    if plan is not None:
        checks["plan_language"] = plan.get("language") == case["language"]
    analysis = state.get("runs", [{}])[-1].get("analysis")
    if analysis:
        checks["cited_values_match_sources"] = bool(analysis.get("facts")) and all(
            verify_fact(f, payload) for f in analysis["facts"]
        )
        if context.get("match_ids") == [900011]:
            missing = {
                "cross",
                "cut_back",
                "switch",
                "completion_rate",
                "attempted_passes",
            }
            checks["no_unannotated_pass_claims"] = not any(
                f["label"].rsplit(".", 1)[-1] in missing
                for f in analysis.get("facts", [])
            )
        if case["id"] in {"reconstruct-es", "reconstruct-en", "structural-passes-es"}:
            checks["narrates_recorded_pass_links"] = any(
                f["label"] == "recorded_pass_link" for f in analysis.get("facts", [])
            )
    return checks


def pointer(root, path):
    for key in path.strip("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        root = root[int(key)] if isinstance(root, list) else root[key]
    return root


def verify_fact(fact, payload):
    try:
        path = fact["path"]
        if path.startswith("/blocks/"):
            _, _, block_id, suffix = path.split("/", 3)
            block = next(b for b in payload["blocks"] if b["id"] == block_id)
            return pointer(block, suffix) == fact["value"]
        evidence = next(
            e for e in payload["evidence"] if e["evidence_id"] in fact["evidence_ids"]
        )
        if path.endswith("#count"):
            return (
                len(pointer(evidence["response"], path.removesuffix("#count")))
                == fact["value"]
            )
        if path.endswith("#frequency_hz"):
            return (
                1000 / pointer(evidence["response"], path.removesuffix("#frequency_hz"))
                == fact["value"]
            )
        if path.endswith("#pass_link"):
            event = pointer(evidence["response"], path.removesuffix("#pass_link"))
            names = {
                r["player_id"]: r["player_name"]
                for e in payload["evidence"]
                if e["operation"] == "get_match_context"
                for r in e["response"]["data"].get("lineups", [])
            }
            return (
                f"{event['timestamp']} · {names[event['player_id']]} → {names[event['pass']['recipient_player_id']]}"
                == fact["value"]
            )
        return pointer(evidence["response"], path) == fact["value"]
    except (KeyError, ValueError, IndexError, StopIteration, TypeError):
        return False


async def run_language_probes(folder):
    free_settings()
    seed = json.loads(
        Path(".temp/agent-quality/seed-data.json").read_text(encoding="utf-8")
    )
    matches = seed["catalog"]["data"]["items"]
    meter = Meter(folder)
    results = []
    for language, text in [
        ("es", "¿Qué es el xG? Explícamelo de forma sencilla."),
        ("en", "What are expected goals? Please explain it simply."),
        ("pt", "O que são gols esperados? Explique de forma simples."),
        ("fr", "Que sont les buts attendus ? Explique-le simplement."),
        ("it", "Che cosa sono i gol attesi? Spiegamelo in modo semplice."),
        ("de", "Was sind erwartete Tore? Erkläre es bitte einfach."),
    ]:
        meter.case = "language-" + language
        async with meter.factory() as model:
            plan = await Interpreter(model).interpret(
                text=text,
                context=DataContext(match_ids=[900011]),
                history=[],
                matches=matches,
                report=None,
            )
        record = {
            "language": language,
            "prompt": text,
            "plan": plan.model_dump(mode="json"),
            "reply": concept_reply(
                plan.answer_topic,
                plan.reply,
                [seed["context"]["data"]["match"]],
                language=plan.language,
            ),
            "passed": plan.language == language
            and plan.action == "answer"
            and plan.answer_topic == "xg",
        }
        results.append(record)
        save(folder, "languages.json", results)
        print(
            json.dumps(
                {
                    "language": language,
                    "detected": plan.language,
                    "passed": record["passed"],
                }
            ),
            flush=True,
        )
    save(
        folder,
        "verification.json",
        {
            "live_model": True,
            "free_only": True,
            "passed": all(r["passed"] for r in results),
            "cases": results,
        },
    )
    return all(r["passed"] for r in results)


def run_chat_cases(folder, port, selected=None):
    if selected and set(selected) - {case["id"] for case in CHAT_CASES}:
        raise ValueError("QA_UNKNOWN_CASE")
    free_settings()
    meter = Meter(folder)
    key = DataMcpSettings.from_env().key
    results = []
    with (
        local_agents(port, meter) as origin,
        httpx.Client(
            base_url=origin,
            headers={"Authorization": "Bearer " + key},
            timeout=125,
            follow_redirects=False,
            trust_env=False,
        ) as client,
    ):
        for case in CHAT_CASES:
            if selected and case["id"] not in selected:
                continue
            meter.case = case["id"]
            started = time.perf_counter()
            cid = client.post("/a2a/v1/conversations").json()["id"]
            body = {
                "request_id": str(uuid4()),
                "text": case["text"],
                "context": case["context"],
                "language": case["language"],
            }
            accepted = client.post(f"/a2a/v1/conversations/{cid}/messages", json=body)
            accepted.raise_for_status()
            last_stage = None
            while time.perf_counter() - started < 125:
                response = client.get(f"/a2a/v1/conversations/{cid}")
                if response.status_code == 429:
                    time.sleep(3)
                    continue
                response.raise_for_status()
                state = response.json()
                if state["stage"] != last_stage:
                    print(
                        json.dumps({"case": case["id"], "stage": state["stage"]}),
                        flush=True,
                    )
                    last_stage = state["stage"]
                if not state["busy"]:
                    break
                time.sleep(2)
            else:
                raise RuntimeError("QA_CASE_POLL_TIMEOUT")
            payload = plan = None
            if state.get("report"):
                report = client.get(
                    f"/a2a/v1/reports/{state['report']['report_id']}"
                ).json()
                plan = report.get("plan")
                page = client.get(
                    state["report"].get("artifact_url")
                    or f"/a2a/v1/reports/{state['report']['report_id']}/revisions/{state['report']['revision']}/html"
                )
                page.raise_for_status()
                if key in page.text:
                    raise RuntimeError("QA_CREDENTIAL_IN_ARTIFACT")
                (folder / (case["id"] + ".html")).write_text(
                    page.text, encoding="utf-8"
                )
                parser = PayloadParser()
                parser.feed(page.text)
                payload = json.loads("".join(parser.parts))
            record = {
                "id": case["id"],
                "prompt": case["text"],
                "context": case["context"],
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "stage": state["stage"],
                "checks": check_report(case, state, payload, plan),
                "reply": state["messages"][-1]["content"],
                "runs": state["runs"],
                "plan": plan,
            }
            record["passed"] = all(record["checks"].values())
            results.append(record)
            if key in json.dumps(record):
                raise RuntimeError("QA_CREDENTIAL_IN_RECORD")
            save(folder, case["id"] + ".json", record)
            save(folder, "telemetry.json", meter.spans)
            print(
                json.dumps(
                    {
                        k: record[k]
                        for k in ("id", "stage", "elapsed_seconds", "passed", "checks")
                    }
                ),
                flush=True,
            )
            if any(
                s.get("issue")
                in {
                    "MODEL_BILLING_REQUIRED",
                    "MODEL_FREE_STATUS_UNVERIFIED",
                    "MODEL_CLI_SESSION_EXPIRED",
                    "MODEL_UNAUTHORIZED",
                }
                for s in meter.spans
            ):
                break
    summary = {
        "model": "beam-free",
        "free_only": True,
        "live_model": True,
        "full_catalog_qa": False,
        "passed": bool(results) and all(r["passed"] for r in results),
        "cases": [
            {k: r[k] for k in ("id", "passed", "stage", "checks", "elapsed_seconds")}
            for r in results
        ],
        "inference_calls": len(meter.spans),
    }
    save(folder, "verification.json", summary)
    print(json.dumps(summary), flush=True)
    return summary["passed"]


def verify_existing(folder):
    """Recheck saved evidence using today's validator, without network or model."""
    results = []
    for case in CHAT_CASES:
        file = folder / (case["id"] + ".json")
        if not file.exists():
            continue
        record = json.loads(file.read_text(encoding="utf-8"))
        payload = None
        page = folder / (case["id"] + ".html")
        if page.exists():
            parser = PayloadParser()
            parser.feed(page.read_text(encoding="utf-8"))
            payload = json.loads("".join(parser.parts))
        state = {**record, "language": case["language"], "report": bool(payload)}
        checks = check_report(case, state, payload, record.get("plan"))
        checks.pop("language")  # No independent conversation snapshot was saved.
        results.append(
            {"id": case["id"], "checks": checks, "passed": all(checks.values())}
        )
    summary = {
        "network_used": False,
        "saved_cases": len(results),
        "passed": bool(results) and all(r["passed"] for r in results),
        "cases": results,
    }
    save(folder, "reverification.json", summary)
    print(json.dumps(summary), flush=True)
    return summary["passed"]


async def preflight(folder):
    settings = free_settings()
    started = time.perf_counter()
    result = {
        "model": settings.deployment,
        "provider": settings.provider,
        "free_only": True,
        "live_model": True,
        "full_catalog_qa": False,
    }
    try:
        async with create_model(settings) as model:
            plan = await Interpreter(model).interpret(
                text="Hola, explícame brevemente qué es el xG.",
                context=DataContext(),
                history=[],
                matches=[],
                report=None,
            )
        result["model_status"] = "ok"
        result["plan"] = plan.model_dump(mode="json")
    except ModelFailure as exc:
        result.update(model_status="blocked", issue=exc.code)
        save(folder, "preflight.json", result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return False
    config = DataMcpSettings.from_env()
    async with httpx.AsyncClient(
        base_url=config.url.removesuffix("/mcp"),
        headers={"Authorization": "Bearer " + config.key},
        timeout=60,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        seeds = {}
        for name, operation, args in [
            ("catalog", "list_matches", {"limit": 100}),
            ("context", "get_match_context", {"match_id": 900011}),
            (
                "passes",
                "get_passes",
                {
                    "match_id": 900011,
                    "scope": {
                        "kind": "window",
                        "period": 1,
                        "start_ms": 0,
                        "end_ms": 60000,
                    },
                    "view": "events",
                    "limit": 100,
                },
            ),
        ]:
            response = await client.post("/api/operations/" + operation, json=args)
            if response.status_code != 200:
                result.update(
                    data_status="blocked",
                    data_http=response.status_code,
                    operation=operation,
                )
                break
            seeds[name] = response.json()
        else:
            result["data_status"] = "ok"
            save(folder, "seed-data.json", seeds)
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    save(folder, "preflight.json", result)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result.get("data_status") == "ok"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--language-probes", action="store_true")
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--case", action="append")
    parser.add_argument("--output-dir", type=Path, default=Path(".temp/agent-quality"))
    args = parser.parse_args()
    if not args.live and not args.verify_existing:
        parser.error(
            "Live inference requires --live and the existing free-only settings"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.verify_existing:
        passed = verify_existing(args.output_dir)
    elif args.preflight:
        passed = asyncio.run(preflight(args.output_dir))
    elif args.language_probes:
        passed = asyncio.run(run_language_probes(args.output_dir))
    else:
        passed = run_chat_cases(args.output_dir, args.port, args.case)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
