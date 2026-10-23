"""Actualiza la imagen sin reemplazar credenciales ni recursos de la demo."""

import argparse
import json
import re

from azure_runtime import ROOT, azure, save_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-tag", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", args.image_tag):
        parser.error("Invalid image tag")
    state = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    app = azure(
        "containerapp",
        "update",
        "-g",
        state["resource_group"],
        "-n",
        state["app_name"],
        "--image",
        state["registry_server"] + "/inside-game:" + args.image_tag,
    )
    state["image_tag"] = args.image_tag
    state["revision"] = app["properties"].get("latestReadyRevisionName")
    state["status"] = "deployed-pending-verification"
    save_state(state)
    print(json.dumps({"revision": state["revision"], "image_tag": args.image_tag}))


if __name__ == "__main__":
    main()
