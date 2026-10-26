"""Pruebas portables del analista: páginas, texto, prompts y trazas, sin LLM."""

import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from html import escape
from pathlib import Path

from inside_game.agents.insights_http_client import PayloadParser
from inside_game.insights.templates import CSS


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pointer(value, path):
    for part in path.strip("/").split("/"):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def build(folder):
    suite = ET.parse(folder / "pytest.xml").getroot().find("testsuite")
    tests = {
        k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")
    }
    tests["seconds"] = float(suite.attrib["time"])
    assert tests["failures"] == tests["errors"] == 0
    basic = read(folder / "verification.json")
    advanced = read(folder / "advanced-verification.json")
    cases = []
    for name in ["topology-analysis", "reused-topology-analysis", "advanced-topology"]:
        result = read(folder / f"{name}.json")
        analysis = result["analysis"]
        parser = PayloadParser()
        parser.feed((folder / f"{name}.html").read_text(encoding="utf-8"))
        payload = json.loads("".join(parser.parts))
        assert (
            analysis["status"] == "complete"
            and payload["analyst"]["text"] == analysis["text"]
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
            )
            checks.append(
                {"fact_id": fact["id"], "path": path, "original_matches": True}
            )
        record = (
            advanced
            if name == "advanced-topology"
            else next(c for c in basic["cases"] if c["case"] == name)
        )
        cases.append(
            {
                **record,
                "request_id": result["request_id"],
                "prompt": read(folder / f"{name}.request.json")["request_text"],
                "fact_checks": checks,
                "page": name + ".html",
                "text": name + ".md",
                "result": name + ".json",
                "sha256": hashlib.sha256(
                    (folder / f"{name}.html").read_bytes()
                ).hexdigest(),
            }
        )
    turns = [
        json.loads(line)
        for line in (folder / "llm-calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    for turn in turns:
        assert turn["agent"] in {"analyst", "data", "insights"}
        assert (
            hashlib.sha256(
                (folder / f"prompt-{turn['agent']}.md").read_bytes()
            ).hexdigest()
            == turn["prompt_sha256"]
        )
    failures = []
    context_failure = folder / "advanced-context-error.json"
    if context_failure.exists():
        old = read(context_failure)
        failures.append(
            {
                "file": str(context_failure),
                "analysis": old["analysis"]["status"],
                "issues": old["analysis"]["issues"],
            }
        )
    for directory in ["analyst-qa", "analyst-review"]:
        for filename in ["first-attempt.json", "topology-analysis.json"]:
            path = folder.parent / directory / filename
            if path.exists():
                previous = read(path)
                failures.append(
                    {
                        "file": str(path),
                        "analysis": previous.get("analysis", {}).get("status"),
                        "issues": previous.get("analysis", {}).get("issues", []),
                    }
                )
    report = {
        "test_suite": tests,
        "cases": cases,
        "prior_failures": failures,
        "data_first_seconds": basic["data_first_seconds"],
        "first_page_end_to_end_seconds": basic["first_page_end_to_end_seconds"],
        "advanced_original_data_seconds": advanced.get("original_data_seconds"),
        "turns": turns,
        "limits": [
            "Las pruebas reales cubren un episodio sintético, no todos los partidos o interpretaciones.",
            "El modelo puede formular interpretaciones débiles; origen de cifras y referencias no prueba toda la semántica.",
            "El intérprete conversacional y el nuevo shell con chat/documento no están implementados en esta tarea.",
            "La prueba avanzada reutiliza la recuperación original de Data; su tiempo de petición no incluye otra consulta SQL.",
        ],
        "passed": True,
    }
    (folder / "trace.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    links = "".join(
        f'<tr><td><a href="{c["page"]}">{escape(c["case"])}</a></td><td>{c["wall_seconds"]:.3f} s</td><td><a href="{c["text"]}">Texto</a> · <a href="{c["result"]}">JSON</a></td></tr>'
        for c in cases
    )
    (folder / "index.html").write_text(
        f"""<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Analista deportivo · pruebas</title><style>{CSS}main{{display:block!important;max-width:1100px}}table{{width:100%}}td,th{{padding:.8rem;text-align:left}}p{{max-width:70ch}}h2{{margin-top:2rem}}</style><header><h1>Analista deportivo: texto y evidencia</h1><p>Beam Free · Datos sintéticos · Data, Insights y funciones topológicas.</p><p><a href="analyst-demo.zip" download>Descargar el paquete sin servidor</a> · <a href="trace.json">Trazabilidad completa</a></p></header><main><p>Data recuperó la evidencia en {basic["data_first_seconds"]:.3f} s. La primera página completa tardó {basic["first_page_end_to_end_seconds"]:.3f} s desde esa recuperación. Las peticiones de las otras páginas reutilizan evidencia; sus tiempos se muestran abajo.</p><div class="table-scroll"><table><thead><tr><th>Página con análisis</th><th>Petición de análisis</th><th>Revisar</th></tr></thead><tbody>{links}</tbody></table></div><h2>Prompts reales</h2><ul><li><a href="prompt-analyst.md">Analista deportivo</a></li><li><a href="prompt-data.md">Data</a></li><li><a href="prompt-insights.md">Insights</a></li></ul><h2>Qué se verificó</h2><p>Cada cifra citada coincide con el campo original de su fuente o bloque. El texto se incorporó literalmente a la página; los gráficos están disponibles. También se conservan las validaciones rechazadas y fallos anteriores. Las interpretaciones siguen requiriendo criterio deportivo.</p><p>Topología: forma, conectividad, homología persistente, retirada virtual de nodos y Voronoi. La geometría no demuestra impenetrabilidad, presión ni control del balón.</p><p>Esta entrega implementa el analista y su comunicación HTTP. El intérprete conversacional y la interfaz con conversaciones, documento y chat son consumidores futuros de estos contratos.</p></main></html>""",
        encoding="utf-8",
    )
    with zipfile.ZipFile(
        folder / "analyst-demo.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for path in folder.iterdir():
            if path.is_file() and path.suffix in {
                ".html",
                ".json",
                ".jsonl",
                ".md",
                ".xml",
            }:
                archive.write(path, path.name)
        for path in (folder / "screenshots").glob("*.png"):
            archive.write(path, "screenshots/" + path.name)
    print(
        json.dumps(
            {
                "pages": len(cases),
                "facts_verified": sum(len(c["fact_checks"]) for c in cases),
                "turns": len(turns),
                "zip_bytes": (folder / "analyst-demo.zip").stat().st_size,
            }
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "folder", type=Path, default=Path(".temp/insights/analyst-demo"), nargs="?"
    )
    build(parser.parse_args().folder)
