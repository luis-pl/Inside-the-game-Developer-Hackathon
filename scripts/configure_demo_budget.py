"""Presupuesto de seguimiento de USD100 para la demo, sin envíos ni corte automático.

La protección crediticia sigue siendo spendingLimit=On. Este presupuesto registra
el objetivo en Azure; no retira ese límite, no cambia oferta y no compra servicios.
"""

import json
from datetime import UTC, datetime

from azure_runtime import ROOT, azure


def main():
    subscription = azure("account", "show")["id"]
    base = f"https://management.azure.com/subscriptions/{subscription}"
    policy = azure("rest", "--method", "get", "--url", base + "?api-version=2022-12-01")
    if policy["subscriptionPolicies"].get("spendingLimit") != "On":
        raise RuntimeError("Stop: keep spending limit enabled")
    cost = azure(
        "rest",
        "--method",
        "post",
        "--url",
        base + "/providers/Microsoft.CostManagement/query?api-version=2025-03-01",
        "--body",
        json.dumps(
            {
                "type": "ActualCost",
                "timeframe": "MonthToDate",
                "dataset": {
                    "granularity": "None",
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                },
            }
        ),
    )
    columns = [c["name"] for c in cost["properties"]["columns"]]
    currencies = {row[columns.index("Currency")] for row in cost["properties"]["rows"]}
    if currencies != {"USD"}:
        raise RuntimeError("Verify billing currency before setting a USD amount")
    now = datetime.now(UTC)
    start = f"{now.year}-{now.month:02d}-01T00:00:00Z"
    end = f"{now.year + 1}-{now.month:02d}-01T00:00:00Z"
    scope = base + "/resourceGroups/rg-inside-game-demo"
    body = {
        "properties": {
            "category": "Cost",
            "amount": 100,
            "timeGrain": "Annually",
            "timePeriod": {"startDate": start, "endDate": end},
            "notifications": {},
        }
    }
    result = azure(
        "rest",
        "--method",
        "put",
        "--url",
        scope
        + "/providers/Microsoft.Consumption/budgets/inside-game-demo-100-usd?api-version=2024-08-01",
        "--body",
        json.dumps(body),
    )
    report = {
        "budget_id": result["id"],
        "amount": 100,
        "currency": "USD",
        "scope": "rg-inside-game-demo (all demo resources)",
        "time_grain": "Annually",
        "start": start,
        "end": end,
        "automatic_consumption_cutoff": False,
        "notification_recipients": [],
        "spending_limit": "On",
        "billing_changed": False,
    }
    (ROOT / "deployment/demo-budget.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
