"""Lee política, presupuesto y tokens; estima inferencia, nunca saldo ni factura."""

import json
from datetime import UTC, datetime, timedelta

from azure_runtime import ROOT, azure


def main():
    model_path = ROOT / "deployment/agent-model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if model.get("provider", "azure") != "azure":
        raise RuntimeError("Azure model metrics do not measure OpenCode usage")
    account = azure("account", "show")
    policy = azure(
        "rest",
        "--method",
        "get",
        "--url",
        f"https://management.azure.com/subscriptions/{account['id']}?api-version=2022-12-01",
    )
    budget = json.loads(
        (ROOT / "deployment/demo-budget.json").read_text(encoding="utf-8")
    )
    remote_budget = azure(
        "rest",
        "--method",
        "get",
        "--url",
        "https://management.azure.com"
        + budget["budget_id"]
        + "?api-version=2024-08-01",
    )
    now = datetime.now(UTC)
    metrics = azure(
        "monitor",
        "metrics",
        "list",
        "--resource",
        model["resource_id"],
        "--metric",
        "InputTokens",
        "OutputTokens",
        "--aggregation",
        "Total",
        "--interval",
        "PT1H",
        "--start-time",
        (now - timedelta(days=1)).isoformat(),
        "--end-time",
        now.isoformat(),
    )
    totals = {
        value["name"]["value"]: sum(
            point.get("total") or 0
            for series in value["timeseries"]
            for point in series["data"]
        )
        for value in metrics["value"]
    }
    price = model["retail_price_usd_per_million_tokens"]
    estimate = (
        totals.get("InputTokens", 0) * price["input"]
        + totals.get("OutputTokens", 0) * price["output"]
    ) / 1000000
    data = {
        "checked_at_utc": now.isoformat(),
        "model": model["model"],
        "offer": policy["subscriptionPolicies"]["quotaId"],
        "spending_limit": policy["subscriptionPolicies"]["spendingLimit"],
        "budget_amount_usd": remote_budget["properties"]["amount"],
        "budget_is_consumption_cutoff": False,
        "window": "last 24 hours, metrics available at check time",
        "tokens": totals,
        "retail_price_usd_per_million_tokens": price,
        "estimated_inference_usd": round(estimate, 6) if sum(totals.values()) else None,
        "is_invoice_or_remaining_credit": False,
        "note": "Estimate for this model only; metrics can lag and exclude other Azure services. Billing meter records are authoritative.",
    }
    (ROOT / "docs/model-cost-verification.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(data))


if __name__ == "__main__":
    main()
