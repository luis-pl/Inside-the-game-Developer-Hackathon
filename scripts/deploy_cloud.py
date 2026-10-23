"""Publica la imagen privada con credenciales caducables y SQL por identidad.

La única información de claves enviada a Azure es el registro de hashes. El
archivo privado queda fuera del repositorio; nunca se imprime su contenido.
"""

import argparse
import json
from pathlib import Path

from azure_runtime import ROOT, azure, save_state
from manage_credentials import registry_from_private


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", required=True, type=Path)
    parser.add_argument("--image-tag", default="demo-20261023")
    args = parser.parse_args()
    state = json.loads((ROOT / "deployment" / "cloud.json").read_text(encoding="utf-8"))
    records = json.dumps(
        registry_from_private(args.private_file), separators=(",", ":")
    )
    app = azure(
        "containerapp",
        "create",
        "-g",
        state["resource_group"],
        "-n",
        state["app_name"],
        "--environment",
        state["environment_id"],
        "--image",
        state["registry_server"] + "/inside-game:" + args.image_tag,
        "--user-assigned",
        state["identity_id"],
        "--registry-server",
        state["registry_server"],
        "--registry-identity",
        state["identity_id"],
        "--ingress",
        "external",
        "--target-port",
        "8000",
        "--transport",
        "http",
        "--cpu",
        "1",
        "--memory",
        "2Gi",
        "--min-replicas",
        "0",
        "--max-replicas",
        "1",
        "--scale-rule-name",
        "http",
        "--scale-rule-http-concurrency",
        "4",
        "--secrets",
        "individual-credentials=" + records,
        "--env-vars",
        "INSIDE_GAME_CLOUD=true",
        "INSIDE_GAME_LOCAL_ACCESS=false",
        "INSIDE_GAME_CREDENTIALS_JSON=secretref:individual-credentials",
        "INSIDE_GAME_PUBLIC_HOST=" + state["public_host"],
        "INSIDE_GAME_SQL_AUTH=managed_identity",
        "AZURE_CLIENT_ID=" + state["identity_client_id"],
        "INSIDE_GAME_SQL_READER=",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
    )
    ingress = app["properties"]["configuration"]["ingress"]
    if ingress.get("allowInsecure"):
        raise RuntimeError("HTTPS-only ingress is required")
    state.update(
        {
            "public_host": ingress["fqdn"],
            "url": "https://" + ingress["fqdn"],
            "app_id": app["id"],
            "image_tag": args.image_tag,
            "revision": app["properties"].get("latestReadyRevisionName"),
            "outbound_ips": app["properties"].get("outboundIpAddresses", []),
            "status": "deployed-pending-verification",
        }
    )
    save_state(state)
    # Sólo las IP de salida declaradas por Azure para el contenedor; no se abre
    # SQL a todos los servicios de Azure ni a las IP de cada compañero.
    for index, address in enumerate(state["outbound_ips"]):
        azure(
            "sql",
            "server",
            "firewall-rule",
            "create",
            "-g",
            state["resource_group"],
            "-s",
            "sql-inside-game-01a160e1-ca",
            "-n",
            f"inside-game-container-{index}",
            "--start-ip-address",
            address,
            "--end-ip-address",
            address,
        )
    print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
