"""Exporta un manifiesto o una respuesta del agente como informe HTML sin red."""

import argparse
import json
from pathlib import Path

from .catalog import CATALOG
from .pages import render_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--data-result", type=Path)
    source.add_argument("--catalog", action="store_true")
    parser.add_argument("--insight", default="shot_map")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.catalog:
        print(json.dumps(CATALOG, ensure_ascii=False, indent=2))
        return
    if not args.output:
        parser.error("--output es obligatorio para exportar HTML")
    try:
        payload = json.loads(
            (args.manifest or args.data_result).read_text(encoding="utf-8-sig")
        )
        if args.data_result:
            payload = {
                "title": "Informe del agente de datos",
                "blocks": [
                    {
                        "id": "insight",
                        "insight_id": args.insight,
                        "evidence_ids": [e["evidence_id"] for e in payload["evidence"]],
                    }
                ],
                "evidence": payload["evidence"],
            }
        result = render_report(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.pop("html"), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError):
        parser.exit(
            1,
            "No se pudo exportar: revisa el manifiesto, la evidencia y la ruta de salida.\n",
        )


if __name__ == "__main__":
    main()
