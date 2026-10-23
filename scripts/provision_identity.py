"""Configura identidades Entra de la demo; no imprime tokens ni envía correos.

Ejecutar con Azure CLI autenticada y AZURE_CLI_PATH/AZURE_CONFIG_DIR configurados.
Los IDs públicos se guardan en deployment/identity.json. La autorización se
concede mediante roles de aplicación, nunca mediante permisos de la suscripción.
"""

import json
import os
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
AZ_PYTHON = Path(os.environ["AZURE_CLI_PATH"]).resolve().parents[1] / "python.exe"
TENANT = "ae525757-89ba-4d30-a2f7-49796ef8c604"
TEAM_ROLE = "7ea3f6e0-e9e6-49b1-81e9-456c893663ee"
AGENT_ROLE = "8c6dfd21-0ca8-476b-8dba-f447f19e5bd9"
READ_SCOPE = "99f2221a-95dd-45bb-a098-d7dbeb361584"
CLI_APP = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"


def main():
    result = subprocess.run(
        [
            str(AZ_PYTHON),
            "-IBm",
            "azure.cli",
            "account",
            "get-access-token",
            "--resource",
            "https://graph.microsoft.com/",
            "-o",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    token = json.loads(result.stdout)["accessToken"]
    with httpx.Client(
        base_url="https://graph.microsoft.com/v1.0",
        headers={"Authorization": "Bearer " + token},
        timeout=45,
    ) as graph:

        def request(method, path, body=None):
            r = graph.request(method, path, json=body)
            if r.is_error:
                error = r.json().get("error", {})
                raise RuntimeError(
                    f"Graph {r.status_code}: {error.get('code')} {error.get('message')}"
                )
            return r.json() if r.content else {}

        def app(name, body):
            existing = request(
                "GET", "/applications?$filter=displayName eq '" + name + "'"
            )["value"]
            if len(existing) > 1:
                raise RuntimeError("Ambiguous app display name")
            return (
                existing[0]
                if existing
                else request("POST", "/applications", {"displayName": name, **body})
            )

        def service_principal(app_id):
            found = request(
                "GET", "/servicePrincipals?$filter=appId eq '" + app_id + "'"
            )["value"]
            return (
                found[0]
                if found
                else request("POST", "/servicePrincipals", {"appId": app_id})
            )

        api = app(
            "inside-game-access",
            {
                "signInAudience": "AzureADMyOrg",
                "api": {
                    "requestedAccessTokenVersion": 2,
                    "oauth2PermissionScopes": [
                        {
                            "id": READ_SCOPE,
                            "value": "Analytics.Read",
                            "type": "User",
                            "isEnabled": True,
                            "adminConsentDisplayName": "Consultar analítica deportiva",
                            "adminConsentDescription": "Consultar las operaciones predeterminadas de lectura de la demo.",
                            "userConsentDisplayName": "Consultar analítica deportiva",
                            "userConsentDescription": "Consultar los partidos sintéticos con los permisos asignados.",
                        }
                    ],
                    "preAuthorizedApplications": [
                        {"appId": CLI_APP, "delegatedPermissionIds": [READ_SCOPE]}
                    ],
                },
                "appRoles": [
                    {
                        "id": TEAM_ROLE,
                        "value": "Team.Read",
                        "displayName": "Equipo de desarrollo",
                        "description": "Consultas de lectura para personas autorizadas",
                        "isEnabled": True,
                        "allowedMemberTypes": ["User"],
                    },
                    {
                        "id": AGENT_ROLE,
                        "value": "Agent.Read",
                        "displayName": "Agentes",
                        "description": "Consultas de lectura para identidades de agentes",
                        "isEnabled": True,
                        "allowedMemberTypes": ["Application"],
                    },
                ],
            },
        )
        audience = api["appId"]
        request(
            "PATCH",
            "/applications/" + api["id"],
            {"identifierUris": ["api://" + audience]},
        )
        sp = service_principal(audience)
        request(
            "PATCH",
            "/servicePrincipals/" + sp["id"],
            {"appRoleAssignmentRequired": True},
        )

        def assign(principal, role):
            existing = request(
                "GET", "/servicePrincipals/" + sp["id"] + "/appRoleAssignedTo"
            )["value"]
            if not any(
                a["principalId"] == principal and a["appRoleId"] == role
                for a in existing
            ):
                request(
                    "POST",
                    "/servicePrincipals/" + sp["id"] + "/appRoleAssignedTo",
                    {
                        "principalId": principal,
                        "resourceId": sp["id"],
                        "appRoleId": role,
                    },
                )

        me = request("GET", "/me?$select=id,displayName")
        assign(me["id"], TEAM_ROLE)
        agent = app("inside-game-agent", {"signInAudience": "AzureADMyOrg"})
        agent_sp = service_principal(agent["appId"])
        assign(agent_sp["id"], AGENT_ROLE)
        state = {
            "tenant_id": TENANT,
            "api_client_id": audience,
            "api_object_id": api["id"],
            "api_service_principal_id": sp["id"],
            "team_role_id": TEAM_ROLE,
            "agent_role_id": AGENT_ROLE,
            "read_scope_id": READ_SCOPE,
            "delegated_scope": "api://" + audience + "/Analytics.Read",
            "agent_client_id": agent["appId"],
            "agent_object_id": agent["id"],
            "agent_service_principal_id": agent_sp["id"],
            "owner_object_id": me["id"],
            "credentials": "No client secrets created; agent credentials are provisioned separately",
        }
        (ROOT / "deployment").mkdir(exist_ok=True)
        (ROOT / "deployment" / "identity.json").write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
