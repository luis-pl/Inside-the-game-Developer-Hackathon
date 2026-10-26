"""Empaqueta evidencia, páginas y trazabilidad de un QA ya ejecutado; no usa LLM."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from qa_insight_agent import PayloadParser

from inside_game.insights.pages import render_report


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(folder):
    # SHA del prompt = bytes exactos enviados como instrucciones (LF), también
    # en Windows. No cambia su texto ni vuelve a invocar al modelo.
    for agent in ("data", "insights"):
        prompt_file = folder / f"prompt-{agent}.md"
        prompt_file.write_bytes(prompt_file.read_text(encoding="utf-8").encode("utf-8"))
    verification = read(folder / "verification.json")
    audit = read(folder / "xg-audit.json")
    suite = ET.parse(folder / "pytest.xml").getroot().find("testsuite")
    tests = {
        k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")
    }
    tests["seconds"] = float(suite.attrib["time"])
    assert tests["failures"] == tests["errors"] == 0
    calls = [
        json.loads(line)
        for line in (folder / "llm-calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    for call in calls:
        initial = json.loads(call["messages"][0]["content"])
        call["request_id"] = initial["request_id"]
        call["prompt_file"] = f"prompt-{call['agent']}.md"
        assert (
            call["prompt_sha256"]
            == hashlib.sha256(
                (folder / call["prompt_file"]).read_text(encoding="utf-8").encode()
            ).hexdigest()
        )
    cases, evidence = [], {}
    for case in verification["cases"]:
        name = case["case"]
        request, result = (
            read(folder / f"{name}.request.json"),
            read(folder / f"{name}.json"),
        )
        parser = PayloadParser()
        parser.feed((folder / f"{name}.html").read_text(encoding="utf-8"))
        payload = json.loads(parser.payload)
        manifest = {
            **read(folder / f"{name}.plan.json"),
            "evidence": payload["evidence"],
        }
        rendered = render_report(manifest)
        assert all(b["state"] == "ready" for b in rendered["blocks"]), name
        current = PayloadParser()
        current.feed(rendered["html"])
        rendered_blocks = json.loads(current.payload)["blocks"]
        (folder / f"{name}.html").write_text(rendered["html"], encoding="utf-8")
        (folder / f"{name}.manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for item in payload["evidence"]:
            evidence[
                json.dumps([item["response"]["request_id"], item["evidence_id"]])
            ] = item
        request_ids = [request["request_id"], *result["data_request_ids"]]
        reused_ids = (
            [request["data_result"]["request_id"]] if request.get("data_result") else []
        )
        selected_calls = [
            i
            for i, call in enumerate(calls)
            if call["request_id"] in request_ids
            and call["request_id"] not in reused_ids
        ]
        checks = []
        for block in rendered_blocks:
            plan_block = next(b for b in manifest["blocks"] if b["id"] == block["id"])
            params = plan_block.get("parameters", {})
            original_shots = read(folder / "shots-900001.json")["data"]["items"]
            selected_shots = [
                e
                for e in original_shots
                if all(
                    params.get(k) is None or e.get(k) == params[k]
                    for k in ("team_id", "player_id", "period")
                )
            ]
            expected_xg = sum(e["shot"]["statsbomb_xg"] for e in selected_shots)
            if block["insight_id"] == "shot_map":
                values = [p.get("xg") for p in block["points"]]
                checks.append(
                    {
                        "block_id": block["id"],
                        "shots": len(values),
                        "sum_shot_xg": sum(values),
                        "displayed_xg": block["metrics"].get("xg"),
                        "independent_api_xg": expected_xg,
                        "passed": len(values) == len(selected_shots)
                        and abs(expected_xg - block["metrics"].get("xg", -1)) < 1e-10
                        and abs(sum(values) - block["metrics"].get("xg", -1)) < 1e-10,
                    }
                )
            if block["insight_id"] == "xg_story":
                ends = {}
                for point in block["series"]:
                    ends[point["group"]] = point["value"]
                checks.append(
                    {
                        "block_id": block["id"],
                        "period_team_totals": ends,
                        "displayed_total": block["metrics"]["observed_xg"],
                        "independent_api_xg": expected_xg,
                        "passed": abs(
                            sum(ends.values()) - block["metrics"]["observed_xg"]
                        )
                        < 1e-10
                        and abs(expected_xg - block["metrics"]["observed_xg"]) < 1e-10,
                    }
                )
        assert all(c["passed"] for c in checks)
        cases.append(
            {
                **case,
                "request_id": request["request_id"],
                "user_prompt": request["request_text"],
                "data_request_ids": result["data_request_ids"],
                "llm_call_indexes": selected_calls,
                "reused_data_request_ids": reused_ids,
                "request_file": f"{name}.request.json",
                "result_file": f"{name}.json",
                "manifest_file": f"{name}.manifest.json",
                "page_file": f"{name}.html",
                "xg_checks": checks,
                "page_sha256": sha(folder / f"{name}.html"),
            }
        )

    # Controles adicionales de renderer, claramente separados de las páginas LLM.
    controls = []
    for match_id, title in [
        (900001, "Control de xG por período · sintético"),
        (900011, "Control de xG ausente · Metrica real"),
    ]:
        data = read(folder / f"shots-{match_id}.json")
        manifest = {
            "title": title,
            "template_id": "custom_report",
            "evidence": [
                {
                    "evidence_id": "audit-shots",
                    "query_id": "audit-shots",
                    "operation": "get_shots",
                    "arguments": {
                        "match_id": match_id,
                        "view": "events",
                        "scope": {"kind": "match"},
                    },
                    "response": data,
                }
            ],
            "blocks": [],
        }
        if match_id == 900001:
            for period in (1, 2):
                manifest["blocks"].append(
                    {
                        "id": f"period-{period}",
                        "insight_id": "shot_map",
                        "title": f"Tiros y xG del período {period}",
                        "evidence_ids": ["audit-shots"],
                        "parameters": {"period": period},
                    }
                )
        else:
            manifest["blocks"] = [
                {
                    "id": "real-shots",
                    "insight_id": "shot_map",
                    "evidence_ids": ["audit-shots"],
                },
                {
                    "id": "missing-xg",
                    "insight_id": "xg_story",
                    "evidence_ids": ["audit-shots"],
                },
            ]
        rendered = render_report(manifest)
        current = PayloadParser()
        current.feed(rendered["html"])
        rendered_blocks = json.loads(current.payload)["blocks"]
        if match_id == 900011:
            assert rendered["blocks"][1]["state"] == "unavailable"
            assert "xg" not in rendered_blocks[0]["metrics"]
        filename = f"control-{match_id}.html"
        (folder / filename).write_text(rendered["html"], encoding="utf-8")
        controls.append(
            {
                "title": title,
                "page_file": filename,
                "model_used": False,
                "blocks": rendered["blocks"],
            }
        )

    trace = {
        "created_utc": datetime.now(UTC).isoformat(),
        "model": "beam-free",
        "free_only": True,
        "prompts": {
            "data": {
                "file": "prompt-data.md",
                "sha256": sha(folder / "prompt-data.md"),
            },
            "insights": {
                "file": "prompt-insights.md",
                "sha256": sha(folder / "prompt-insights.md"),
            },
        },
        "notice": "Trazabilidad de acciones observables; sin razonamiento interno ni credenciales. Notas del modelo no equivalen a hechos deportivos. El texto de analista de estos casos fue aportado por el script, no generado por un tercer agente.",
        "render_refresh": "Las páginas se recompilaron con los mismos planes/evidencias después de aclarar la etiqueta de xG sintético; no hubo inferencia adicional.",
        "verification": verification,
        "test_suite": tests,
        "xg_audit": audit,
        "cases": cases,
        "model_calls": calls,
        "original_evidence": list(evidence.values()),
        "renderer_controls": controls,
    }
    (folder / "trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Revisión de xG y pruebas de agentes",
        "",
        "Fecha: 26 de octubre de 2026. Datos de la API existente; no se modificó SQL.",
        "",
        "## Qué se comprobó",
        "",
        "- 209 tiros sintéticos en diez partidos: probabilidades entre 0 y 1, fórmula geométrica y sumas coincidentes. Es un modelo de demostración sin calibración deportiva.",
        "- Los diez partidos reales importados carecen de xG; se conserva null.",
        "- Límite del generador sintético: la fórmula ignora portero, defensores, parte del cuerpo y tipo de asistencia. Además fuerza el primer tiro a Blocked para asegurar cobertura de acciones. Coincidir con esa fórmula no prueba calibración ni realismo de las probabilidades.",
        "- La comparación del partido 900001 suma 1,0615838865 + 0,6287962407 = 1,6903801272. Tener un marcador 1–2 no contradice esas probabilidades.",
        "- Se corrigió que los mapas filtrados reutilizaran resúmenes de otro alcance. Ahora métricas y puntos salen de los mismos tiros únicos.",
        "- Series temporales: se ordenan/deduplican intervalos; se rechazan solapamientos; P2 se reinicia expresamente en cero.",
        f"- Suite completa: {tests['tests']} pruebas, cero fallos/errores, en {tests['seconds']:.2f} s.",
        "",
        "## Prompts y detalle",
        "",
        "- [Prompt completo del agente de Data](prompt-data.md).",
        "- [Prompt completo del agente de Insights](prompt-insights.md).",
        "- [Trazabilidad JSON](trace.json): solicitudes, llamadas, argumentos, respuestas de tools visibles al modelo, errores y evidencia original.",
        "- [Schemas de tools de Data](tools-data.json) y [de Insights](tools-insights.json).",
        "- [Auditoría de los 20 partidos](xg-audit.json).",
        "",
        "La traza es de esta nueva ejecución. Las ejecuciones anteriores no guardaban el intercambio completo. No se reconstruyó ni se inventó ese historial. No contiene razonamiento interno ni claves. El párrafo del analista fue una entrada fija de prueba, no la salida de un analista LLM.",
        "",
        "## Solicitudes, delegaciones y páginas",
        "",
    ]
    for case in cases:
        lines += [
            f"### {case['case']}",
            "",
            f"Resultado: **{case['status']}**, {case['wall_seconds']:.3f} s; revisión {case['revision']}.",
            "",
            "**Solicitud a Insights:**",
            "",
            "> " + case["user_prompt"],
            "",
            f"[Abrir página]({case['page_file']}) · [Solicitud JSON]({case['request_file']}) · [Plan y evidencia]({case['manifest_file']})",
            "",
            "**Llamadas de Insights y Data:**",
            "",
        ]
        indexes = case["llm_call_indexes"]
        if case["reused_data_request_ids"]:
            lines += [
                "Evidencia de Data reutilizada de una solicitud anterior; no se ejecutó otra inferencia de Data en este caso.",
                "",
            ]
        for i in indexes:
            call = calls[i]
            for tool in call.get("tool_calls", []):
                args = json.loads(tool["arguments"])
                lines += [
                    f"- `{call['agent']}` → `{tool['name']}`: `{json.dumps(args, ensure_ascii=False)}`"
                ]
        lines += ["", "**Intentos rechazados por contrato:**", ""]
        rejected = [t for t in case["tool_trace"] if t["status"] == "error"]
        lines += (
            [
                f"- `{r['tool']}`: `{json.dumps(r.get('fields', r), ensure_ascii=False)}`"
                for r in rejected
            ]
            if rejected
            else [
                "Ninguno en la composición. Los errores de Data, si existen, se conservan en `trace.json`."
            ]
        )
        lines += [""]
    lines += (
        ["## Controles sin LLM", ""]
        + [f"- [{c['title']}]({c['page_file']})." for c in controls]
        + [
            "",
            "## Cómo abrir y reproducir",
            "",
            "Extrae el ZIP y abre `index.html`; los informes contienen sus datos y no necesitan API ni internet. Para consultar datos o generar páginas nuevas sí se necesitan credenciales privadas vigentes.",
            "",
            "```powershell",
            "python scripts/audit_xg.py",
            "python scripts/qa_insight_trace_server.py",
            "python scripts/qa_insight_agent.py --base-url http://127.0.0.1:8087 --output-dir .temp/insights/xg-review",
            "python scripts/build_insight_qa_bundle.py .temp/insights/xg-review",
            "```",
            "",
            "Los casos finales pasaron en menos de un minuto; no es una garantía de latencia. La validación rechazó IDs numéricos enviados como texto y el modelo corrigió sus llamadas. La bitácora conserva esos intentos.",
            "",
            "Definición de referencia: [Hudl StatsBomb, Expected Goals](https://statsbomb.com/soccer-metrics/expected-goals-xg-explained/). El xG de nuestra demo no procede de ese modelo.",
            "",
        ]
    )
    (folder / "README.md").write_text("\n".join(lines), encoding="utf-8")
    rows = "".join(
        f'<tr><td><a href="{c["page_file"]}">{escape(c["case"])}</a></td><td>{c["wall_seconds"]:.3f} s</td><td>{escape(c["status"])}</td><td><a href="{c["request_file"]}">Solicitud</a> · <a href="{c["manifest_file"]}">Plan y evidencia</a></td></tr>'
        for c in cases
    )
    control_links = "".join(
        f'<li><a href="{c["page_file"]}">{escape(c["title"])}</a> · sin LLM</li>'
        for c in controls
    )
    from inside_game.insights.templates import CSS

    index = f"""<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión de xG y trazabilidad</title><style>{CSS} main{{display:block!important;max-width:1100px}} h2{{margin-top:2.5rem}}td,th{{padding:.8rem;text-align:left}} table{{width:100%}}p{{max-width:70ch}}code{{overflow-wrap:anywhere}}a{{text-underline-offset:.2em}} </style><header><h1>Revisión de xG y trazabilidad</h1><p>26 de octubre de 2026 · Beam Free · tres páginas y dos modificaciones con los agentes.</p><p><a href="insight-review.zip" download>Descargar paquete para abrir sin servidor</a> · <a href="README.md">Informe Markdown</a> · <a href="trace.json">Trazabilidad JSON</a></p></header><main><h2>Qué ocurre con el xG</h2><p>En el partido sintético 900001: equipo 1 <strong>1,06158 xG</strong>, equipo 2 <strong>0,62880 xG</strong>; total <strong>1,69038</strong>. Coincide con los tiros. Es una fórmula de demostración, no un modelo calibrado ni el xG de StatsBomb.</p><p>Se corrigieron los resúmenes de mapas filtrados. Las curvas muestran acumulados independientes por período: P2 comienza en cero. En los diez partidos reales importados el xG está ausente; no se sustituye por cero.</p><h2>Páginas creadas por los agentes</h2><div class="table-scroll"><table><thead><tr><th>Resultado</th><th>Tiempo</th><th>Estado</th><th>Comprobar</th></tr></thead><tbody>{rows}</tbody></table></div><h2>Prompts usados</h2><ul><li><a href="prompt-insights.md">Prompt completo de Insights</a></li><li><a href="prompt-data.md">Prompt completo de Data</a></li></ul><p>Las solicitudes exactas, delegaciones, schemas, argumentos, resultados y errores están en el Markdown y JSON. Las notas del modelo se distinguen de los datos originales. El texto del analista fue aportado como entrada de prueba.</p><h2>Controles de datos sin LLM</h2><ul>{control_links}</ul><p><a href="xg-audit.json">Auditoría de veinte partidos</a> · 391 pruebas automatizadas pasadas. Las cinco solicitudes terminaron en menos de un minuto; no constituye garantía de disponibilidad del proveedor.</p></main></html>"""
    (folder / "index.html").write_text(index, encoding="utf-8")
    # Sin rutas absolutas ni archivos de configuración privada dentro del ZIP.
    with zipfile.ZipFile(
        folder / "insight-review.zip", "w", zipfile.ZIP_DEFLATED
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
                "cases": len(cases),
                "model_calls": len(calls),
                "archive_bytes": (folder / "insight-review.zip").stat().st_size,
                "xg_checks_passed": True,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    build(parser.parse_args().folder)
