"""Prepara recursos limitados de la demo; no publica un endpoint sin autenticar."""

import json

from azure_runtime import azure, save_state


def main():
    group = "rg-inside-game-demo"
    workspace = azure(
        "monitor",
        "log-analytics",
        "workspace",
        "show",
        "-g",
        group,
        "-n",
        "law-inside-game-demo",
    )
    keys = azure(
        "monitor",
        "log-analytics",
        "workspace",
        "get-shared-keys",
        "-g",
        group,
        "-n",
        "law-inside-game-demo",
    )
    identity = azure("identity", "show", "-g", group, "-n", "id-inside-game-api")
    env = azure(
        "containerapp",
        "env",
        "create",
        "-g",
        group,
        "-n",
        "env-inside-game-demo",
        "-l",
        "canadacentral",
        "--environment-mode",
        "ConsumptionOnly",
        "--logs-destination",
        "log-analytics",
        "--logs-workspace-id",
        workspace["customerId"],
        "--logs-workspace-key",
        keys["primarySharedKey"],
    )
    registry = azure("acr", "show", "-g", group, "-n", "acrinsidegame01a160e1")
    assignments = azure(
        "role",
        "assignment",
        "list",
        "--assignee",
        identity["principalId"],
        "--scope",
        registry["id"],
    )
    if not any(r["roleDefinitionName"] == "AcrPull" for r in assignments):
        azure(
            "role",
            "assignment",
            "create",
            "--assignee-object-id",
            identity["principalId"],
            "--assignee-principal-type",
            "ServicePrincipal",
            "--role",
            "AcrPull",
            "--scope",
            registry["id"],
        )
    state = {
        "resource_group": group,
        "app_name": "api-inside-game",
        "location": "canadacentral",
        "environment_id": env["id"],
        "registry": registry["name"],
        "registry_server": registry["loginServer"],
        "identity_id": identity["id"],
        "identity_client_id": identity["clientId"],
        "identity_principal_id": identity["principalId"],
        "workspace_id": workspace["customerId"],
        "public_host": "api-inside-game." + env["properties"]["defaultDomain"],
        "min_replicas": 0,
        "max_replicas": 1,
        "cpu": 1,
        "memory": "2Gi",
        "status": "infrastructure-ready",
        "authentication": "individual-expiring-bearer-credentials",
    }
    save_state(state)
    print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
