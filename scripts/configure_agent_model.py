"""Configura el modelo ya desplegado sin cambiar oferta ni límite de gasto.

Sólo escribe ajustes públicos y la ruta del archivo individual privado. No lee
ni copia claves. Conserva el diagnóstico de Luna para distinguir los modelos.
"""

import json
from pathlib import Path

from azure_runtime import ROOT, azure


def main():
    path = ROOT / "deployment/agent-model.json"
    previous = json.loads(path.read_text(encoding="utf-8"))
    if previous.get("provider", "azure") != "azure":
        raise RuntimeError("This script only configures the historical Azure deployment")
    # La existencia del despliegue no autoriza a reactivar un modelo descartado.
    if previous.get("selection_status") == "rejected_by_user":
        raise RuntimeError(
            "GPT-OSS was rejected by the owner; choose an approved model first"
        )
    subscription = azure("account", "show")["id"]
    policy = azure(
        "rest",
        "--method",
        "get",
        "--url",
        f"https://management.azure.com/subscriptions/{subscription}?api-version=2022-12-01",
    )
    if policy["subscriptionPolicies"].get("spendingLimit") != "On":
        raise RuntimeError("Stop: spending limit must remain enabled")
    group = "rg-inside-game-demo"
    account = "ai-inside-game-01a160e1-ca"
    resource = azure("cognitiveservices", "account", "show", "-g", group, "-n", account)
    deployed = azure(
        "cognitiveservices",
        "account",
        "deployment",
        "show",
        "-g",
        group,
        "-n",
        account,
        "--deployment-name",
        "gpt-oss-120b",
    )
    if deployed["properties"]["provisioningState"] != "Succeeded":
        raise RuntimeError("Model deployment is not ready")
    luna = previous.get("luna") or previous
    if "luna" in luna:
        raise RuntimeError("Invalid model metadata")
    state = {
        "status": "deployed_pending_inference_verification",
        "resource_group": group,
        "resource": account,
        "resource_id": resource["id"],
        "project": "inside-game",
        "endpoint": f"https://{account}.services.ai.azure.com/",
        "deployment": "gpt-oss-120b",
        "deployment_created": True,
        "model": "gpt-oss-120b",
        "model_version": "1",
        "api": "chat_completions",
        "sku": "GlobalStandard",
        "capacity": deployed["sku"]["capacity"],
        "location": "canadacentral",
        "budget_target_usd": 100,
        "subscription_offer": policy["subscriptionPolicies"]["quotaId"],
        "spending_limit": "On",
        "billing_changed": False,
        "billing_path": "Azure-native model meters; no Marketplace purchase",
        "natural_language_evaluation": "pending",
        "luna": luna,
        "retail_price_usd_per_million_tokens": {"input": 0.15, "output": 0.60},
    }
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    cloud = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    private = (
        Path.home()
        / ".codex/visualizations/2026/10/21/01a160e1-4edd-7690-aa3b-45f82ff5aba9/private-access/agent-data.json"
    )
    values = {
        "AZURE_OPENAI_ENDPOINT": state["endpoint"],
        "AZURE_OPENAI_DEPLOYMENT": state["deployment"],
        "INSIDE_GAME_MODEL_API": state["api"],
        "INSIDE_GAME_MODEL_AUTH": "azure_cli",
        "INSIDE_GAME_DATA_MCP_URL": cloud["url"] + "/mcp",
    }
    if private.is_file():
        values["INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE"] = str(private)
    env = ROOT / ".env.local"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    lines = [line for line in lines if line.partition("=")[0].strip() not in values]
    lines.extend(f"{name}={value}" for name, value in values.items())
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "model": state["model"],
                "deployment_ready": True,
                "spending_limit": "On",
                "billing_changed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
