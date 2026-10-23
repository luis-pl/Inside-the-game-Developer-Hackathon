"""Guarda evidencia agregada de trazabilidad en Azure; nunca descarga claves."""

import json
from datetime import UTC, datetime

from azure_runtime import ROOT, azure


def main():
    state = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    query = """
    ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == 'api-inside-game'
    | extend p=parse_json(Log_s)
    | where tostring(p.event) in ('analytics_request','mcp_tool')
    | summarize requests=count() by credential=tostring(p.credential_id),role=tostring(p.role),event=tostring(p.event)
    """
    rows = azure(
        "monitor",
        "log-analytics",
        "query",
        "--workspace",
        state["workspace_id"],
        "--analytics-query",
        query,
        "--timespan",
        "PT1H",
    )
    identities = {r["credential"] for r in rows}
    check = {
        "name": "Team and agent identities persisted in Azure audit",
        "passed": {"team-owner", "team-collaborator-01", "agent-data"} <= identities,
    }
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "source": "Azure Log Analytics, ContainerAppConsoleLogs_CL",
        "status": "passed" if check["passed"] else "pending-ingestion",
        "rows": rows,
        "checks": [check],
    }
    (ROOT / "docs/cloud-audit-verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    if not check["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
