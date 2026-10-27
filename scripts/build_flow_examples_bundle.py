"""Verifica las cinco ejecuciones y publica un índice y ZIP sin nuevas inferencias."""

import argparse
import hashlib
import json
import math
import zipfile
from html import escape
from pathlib import Path

from build_sports_analyst_bundle import pointer
from generate_flow_examples import CASES

from inside_game.agents.insights_http_client import PayloadParser
from inside_game.insights.templates import CSS


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(folder):
    records = read(folder / "verification.json")
    pages = []
    for case in CASES:
        record = next(r for r in records if r["id"] == case["id"])
        assert record.get("page"), case["id"]
        result = read(folder / f"{case['id']}.json")
        parser = PayloadParser()
        page = folder / record["page"]
        parser.feed(page.read_text(encoding="utf-8"))
        payload = json.loads("".join(parser.parts))
        analysis = result["analysis"]
        assert analysis["status"] == "complete"
        assert payload["analyst"]["text"] == analysis["text"]
        assert sorted(b["insight_id"] for b in payload["blocks"]) == sorted(
            case["recipes"]
        )
        assert all(b["state"] == "ready" for b in payload["blocks"])
        checks = []
        for fact in analysis["facts"]:
            path = fact["path"]
            if path.startswith("/blocks/"):
                _, _, block_id, *parts = path.split("/")
                block = next(b for b in payload["blocks"] if b["id"] == block_id)
                original = pointer(block, "/" + "/".join(parts))
            else:
                ev = next(
                    e
                    for e in payload["evidence"]
                    if e["evidence_id"] in fact["evidence_ids"]
                )
                original = pointer(ev["response"], path.removesuffix("#count"))
                if path.endswith("#count"):
                    original = len(original)
            value = fact["value"]
            assert (
                math.isclose(original, value, rel_tol=0, abs_tol=1e-10)
                if type(value) in (int, float)
                else original == value
            ), (case["id"], path)
            checks.append({"fact_id": fact["id"], "path": path, "matches": True})
        pages.append(
            {
                **record,
                "data_request": case["data"],
                "analyst_request": case["question"],
                "request_id": result["request_id"],
                "context": case["context"],
                "source": "Metrica real seudonimizada"
                if case["id"] == "04-estructura-real"
                else "Sintética",
                "fact_checks": checks,
                "page_sha256": hashlib.sha256(page.read_bytes()).hexdigest(),
            }
        )
    turns = [
        json.loads(line)
        for line in (folder / "llm-calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    for turn in turns:
        assert turn["agent"] in {"data", "analyst", "insights"}
        assert (
            hashlib.sha256(
                (folder / f"prompt-{turn['agent']}.md").read_bytes()
            ).hexdigest()
            == turn["prompt_sha256"]
        )
    trace = {
        "pages": pages,
        "passed": True,
        "fact_count": sum(len(p["fact_checks"]) for p in pages),
        "flow": "Solicitud → Data → MCP de datos → SQL → analista ↔ Insights → MCP de visualizaciones → HTML con análisis",
        "model": "Beam Free · OpenCode Go · free-only",
        "notes": [
            "Cinco solicitudes independientes, no cinco revisiones de la misma página.",
            "Las páginas y el ZIP se pueden abrir sin el servicio de agentes.",
            "Los tiempos son mediciones de estas ejecuciones, no una garantía de latencia.",
            "La comprobación de cifras no certifica todas las interpretaciones del modelo.",
            "Se conservan intentos fallidos, reintentos y mensajes de herramientas; no razonamiento interno ni credenciales.",
        ],
        "turns": turns,
    }
    (folder / "trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    cards = []
    for n, page in enumerate(pages, 1):
        ident = page["id"]
        retry = len(page["attempts"]) - 1
        prior_note = (
            f"<p>El flujo medido incluye {page['prior_seconds']:.1f} s de un intento anterior fallido de Data, conservado en la traza.</p>"
            if page.get("prior_seconds")
            else ""
        )
        cards.append(
            f'<article><span class="eyebrow">EJEMPLO {n:02} · {escape(page["source"])}</span>'
            f'<h2><a href="{ident}.html">{escape(page["title"])}</a></h2>'
            f"<p>{escape(page['analyst_request'])}</p>"
            f'<p class="recipes">{escape(" · ".join(page["recipes"]))}</p>'
            f'<dl class="timing"><div><dt>Data</dt><dd>{page["data_seconds"]:.1f} s</dd></div>'
            f"<div><dt>Análisis + página</dt><dd>{page['analysis_seconds']:.1f} s</dd></div>"
            f"<div><dt>Flujo medido</dt><dd>{page['end_to_end_seconds']:.1f} s</dd></div></dl>"
            f"<p>{page['facts']} hechos citados y verificados. Reintentos de análisis: {retry}.</p>"
            + prior_note
            + f'<nav aria-label="Archivos del ejemplo {n}"><a class="page-link" href="{ident}.html">Abrir página ↗</a>'
            f'<a href="{ident}.md">Leer análisis</a><a href="{ident}.data-request.json">Solicitud a Data</a>'
            f'<a href="{ident}.json">Resultado completo</a></nav></article>'
        )
    styles = """
    main{display:block!important;max-width:1140px}header{max-width:1140px}
    header p{max-width:76ch}article{padding:2rem 0;border-top:1px solid var(--line)}
    article p{max-width:85ch}h2{max-width:40ch;margin:.3rem 0 1rem}
    nav{display:flex;flex-wrap:wrap;gap:.7rem 1.4rem;font-size:.86rem}
    .timing{display:flex;flex-wrap:wrap;gap:1rem 2.5rem;margin:1.2rem 0}
    .timing dd{margin:0;font-size:1.35rem}.recipes{font-size:.85rem;color:var(--muted)}
    .page-link{font-weight:700}.notice{padding:1rem;border-left:3px solid #a05c13;background:#f6eee4}
    a{overflow-wrap:anywhere} @media(max-width:600px){article{padding:1.5rem 0}}
    """
    (folder / "index.html").write_text(
        '<!doctype html><html lang="es"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Cinco páginas · Inside the game</title><style>{CSS}{styles}</style>"
        '<header><span class="eyebrow">INSIDE THE GAME · EJECUCIONES REALES DEL FLUJO</span>'
        "<h1>Cinco preguntas.<br>Cinco páginas de análisis.</h1>"
        "<p>Data recupera la evidencia, Insights compone los gráficos y el analista redacta un texto con referencias a esos datos. Beam Free en las tres funciones.</p>"
        '<nav><a href="examples.zip" download>Descargar las cinco páginas y sus trazas</a>'
        '<a href="trace.json">Trazabilidad completa</a>'
        '<a href="prompt-data.md">Prompt de Data</a><a href="prompt-analyst.md">Prompt del analista</a>'
        '<a href="prompt-insights.md">Prompt de Insights</a></nav></header><main>'
        '<p class="notice">Cuatro ejemplos usan datos sintéticos; el cuarto utiliza posiciones reales de Metrica con identidades sustituidas. El xG sintético es ilustrativo. Los tiempos incluyen la recuperación de Data y los intentos de análisis de cada ejecución; los fallos y reintentos se conservan en la traza. La geometría describe posiciones y distancias, sin demostrar intención táctica ni control del balón.</p>'
        + "".join(cards)
        + "</main></html>",
        encoding="utf-8",
    )
    (folder / "README.md").write_text(
        "# Cinco ejemplos del flujo\n\nAbre `index.html` o cada HTML directamente. "
        "Las páginas son autocontenidas. `trace.json` contiene solicitudes, tiempos, "
        "resultados, comprobaciones numéricas y turnos de herramientas. Los tres "
        "archivos `prompt-*.md` conservan los prompts usados.\n\n"
        "Cuatro casos son sintéticos; el caso 04 usa posiciones reales seudonimizadas. "
        "Los tiempos no garantizan el rendimiento futuro.\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(folder / "examples.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix in {".html", ".md", ".json", ".jsonl"}:
                archive.write(path, path.relative_to(folder))
    print(json.dumps({"pages": len(pages), "facts_verified": trace["fact_count"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".temp/insights/five-flow-examples")
    )
    build(parser.parse_args().output_dir)
