"""Preguntas cotidianas → intérprete real → respuesta visible, sin crear informes.

Usa el modelo configurado y sus comprobaciones de precio cero. La muestra de
informe es sólo contexto de interfaz, no una ejecución fingida de Data/Insights.
Conserva solicitudes, decisiones y tiempos; nunca credenciales ni cookies.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

from inside_game.agents.contracts import DataContext
from inside_game.agents.conversation_copy import catalog_reply, concept_reply
from inside_game.agents.interpreter import Interpreter
from inside_game.agents_cli import load_local_env
from inside_game.providers.models import ModelFailure, create_model

CASES = [
    ("welcome", "Hola, ¿qué puedo mirar aquí?", [], None),
    (
        "explain-xg",
        "¿Qué es el xG? Explícamelo fácil, que no sé mucho de fútbol.",
        [],
        None,
    ),
    (
        "casual-analysis",
        "¿Quién fue mejor en este partido? No entiendo mucho de estadísticas.",
        [900001],
        None,
    ),
    ("real-match-attack", "Muéstrame cómo atacaron los dos equipos.", [900011], None),
    ("missing-xg", "Añade el xG y dime quién fue el jugador estrella.", [900011], None),
    (
        "explain-voronoi",
        "Eso del Voronoi no lo entiendo. ¿Para qué sirve en fútbol?",
        [],
        None,
    ),
    (
        "simplify-report",
        "Ese gráfico no me ayuda, quiero algo más sencillo y que me expliques lo importante.",
        [900001],
        {
            "report_id": "00000000-0000-4000-8000-000000000001",
            "revision": 1,
            "blocks": [
                {
                    "id": "shots",
                    "insight_id": "shot_map",
                    "title": "Mapa de tiros",
                    "state": "ready",
                },
                {
                    "id": "xg",
                    "insight_id": "xg_story",
                    "title": "Evolución del xG",
                    "state": "ready",
                },
            ],
        },
    ),
]


def check(name, plan, reply):
    if name in {"welcome", "explain-xg", "explain-voronoi"}:
        return (
            plan.action == "answer"
            and plan.answer_topic
            == {"welcome": "welcome", "explain-xg": "xg", "explain-voronoi": "voronoi"}[
                name
            ]
        )
    if name == "casual-analysis":
        return (
            plan.action == "clarify"
            and "equipo" in reply
            and "jugador" in reply
            and reply.count("?") == 1
        )
    if name == "real-match-attack":
        return plan.action == "create" and plan.context.match_ids == [900011]
    if name == "missing-xg":
        return (
            plan.action == "clarify" and "xg" in reply.lower() and reply.count("?") <= 1
        )
    return plan.action in {"modify", "clarify"} and reply.count("?") <= 1


async def run(folder, base_url):
    load_local_env(Path(__file__).resolve().parents[1])
    folder.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        base_url=base_url,
        timeout=60,
        trust_env=False,
        headers={"X-Inside-Game": "workspace"},
    ) as client:
        client.post("/workspace-api/session").raise_for_status()
        response = client.get("/workspace-api/chat-catalog")
        response.raise_for_status()
        matches = response.json()["matches"]
    assert {900001, 900011} <= {m["match_id"] for m in matches}, (
        "QA_FIXTURES_NOT_IN_CATALOG"
    )
    results = []
    for name, text, ids, report in CASES:
        started = time.perf_counter()
        result = {
            "case": name,
            "request": text,
            "context_match_ids": ids,
            "report_context_is_fixture": bool(report),
        }
        try:
            async with asyncio.timeout(30):
                async with create_model() as model:
                    interpreter = Interpreter(model)
                    plan = await interpreter.interpret(
                        text=text,
                        context=DataContext(match_ids=ids),
                        history=[],
                        matches=matches,
                        report=report,
                    )
            reply = plan.reply
            if plan.action == "answer":
                reply = concept_reply(
                    plan.answer_topic,
                    reply,
                    [m for m in matches if m["match_id"] in ids],
                )
            elif plan.action == "catalog":
                reply = catalog_reply(reply, matches)
            result.update(
                action=plan.action,
                reply=reply,
                delegation=plan.model_dump(mode="json"),
                trace=interpreter.trace,
                prompt_sha256=interpreter.prompt_sha256,
                passed=check(name, plan, reply),
            )
        except (TimeoutError, ModelFailure, ValueError, httpx.HTTPError) as exc:
            result.update(error=getattr(exc, "code", type(exc).__name__), passed=False)
        result["seconds"] = round(time.perf_counter() - started, 2)
        results.append(result)
        (folder / "responses.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k in {"case", "action", "reply", "error", "passed", "seconds"}
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    assert all(r["passed"] for r in results), "CONVERSATION_QA_FAILED"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".temp/sports-conversation-current")
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    args = parser.parse_args()
    asyncio.run(run(args.output_dir, args.base_url))
