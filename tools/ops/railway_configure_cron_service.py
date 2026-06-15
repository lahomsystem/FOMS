"""Set FOMS-cron service config via Railway GraphQL (config path + redeploy).

Production FOMS-PRODUCTION IDs verified via `railway variables --json` (2026-06-15).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
REPO = "lahomsystem/FOMS"
CONFIG_PATH = "railway-cron.toml"
CRON_START_COMMAND = "python tools/cron/cleanup_order_drafts.py --execute"
CRON_SCHEDULE = "0 17 * * *"

# FOMS-PRODUCTION / production environment (verified 2026-06-15)
PRODUCTION_CRON_SERVICE_ID = "3bcaabb9-3b45-4382-8681-cc961865ae80"
PRODUCTION_ENVIRONMENT_ID = "57587e48-dc52-42f7-9991-e70895a0ee50"
PRODUCTION_BRANCH = "production"

# Legacy staging/deploy IDs (do not use for FOMS-PRODUCTION cron)
STAGING_CRON_SERVICE_ID = "593a03e6-966b-4ea6-9b3a-f19d78d7a5f7"
STAGING_ENVIRONMENT_ID = "d7156ab5-8d7d-4a55-99ed-1054d0a02f7d"
STAGING_BRANCH = "deploy"


def _parse_args() -> argparse.Namespace:
    """Parse target environment for cron service configuration."""
    parser = argparse.ArgumentParser(description="Configure Railway FOMS-cron service.")
    parser.add_argument(
        "--target",
        choices=("production", "staging"),
        default="production",
        help="Railway environment to configure (default: production).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without applying mutations.",
    )
    return parser.parse_args()


def _target_config(target: str) -> tuple[str, str, str]:
    """Return (service_id, environment_id, git_branch) for the target."""
    if target == "production":
        return PRODUCTION_CRON_SERVICE_ID, PRODUCTION_ENVIRONMENT_ID, PRODUCTION_BRANCH
    return STAGING_CRON_SERVICE_ID, STAGING_ENVIRONMENT_ID, STAGING_BRANCH


def _load_token() -> str:
    """Load Railway API token from CLI config."""
    config_path = Path.home() / ".railway" / "config.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    token = data.get("user", {}).get("token")
    if not token:
        raise SystemExit("Railway token not found in ~/.railway/config.json")
    return token


def _graphql(token: str, query: str, variables: dict | None = None) -> dict:
    """Execute a Railway GraphQL request."""
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "railway-cli/4.0.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GraphQL HTTP {exc.code}: {detail}") from exc
    if body.get("errors"):
        raise SystemExit(f"GraphQL errors: {json.dumps(body['errors'], ensure_ascii=False)}")
    return body.get("data", {})


def _introspect_update_input(token: str) -> list[str]:
    """List mutable ServiceInstanceUpdateInput fields."""
    query = """
    query {
      __type(name: "ServiceInstanceUpdateInput") {
        inputFields { name type { name kind ofType { name kind } } }
      }
    }
    """
    data = _graphql(token, query)
    fields = data["__type"]["inputFields"]
    return [f["name"] for f in fields]


def _get_service_instance(token: str, service_id: str, environment_id: str) -> dict:
    """Fetch current cron service instance settings."""
    query = """
    query($serviceId: String!, $environmentId: String!) {
      serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
        id
        startCommand
        cronSchedule
        railwayConfigFile
        rootDirectory
        source {
          repo
          image
        }
        latestDeployment {
          id
          status
        }
      }
    }
    """
    variables = {
        "serviceId": service_id,
        "environmentId": environment_id,
    }
    return _graphql(token, query, variables)["serviceInstance"]


def _connect_repo(token: str, service_id: str, branch: str) -> None:
    """Point FOMS-cron at the target git branch."""
    query = """
    mutation($id: String!, $input: ServiceConnectInput!) {
      serviceConnect(id: $id, input: $input) { id name }
    }
    """
    variables = {
        "id": service_id,
        "input": {"repo": REPO, "branch": branch},
    }
    _graphql(token, query, variables)


def _update_service_instance(
    token: str,
    service_id: str,
    environment_id: str,
    update_input: dict,
) -> None:
    """Apply service instance configuration."""
    query = """
    mutation($serviceId: String!, $environmentId: String!, $input: ServiceInstanceUpdateInput!) {
      serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId, input: $input)
    }
    """
    variables = {
        "serviceId": service_id,
        "environmentId": environment_id,
        "input": update_input,
    }
    _graphql(token, query, variables)


def _redeploy(token: str, service_id: str, environment_id: str) -> None:
    """Trigger a fresh deployment for the cron service."""
    query = """
    mutation($serviceId: String!, $environmentId: String!) {
      serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    variables = {
        "serviceId": service_id,
        "environmentId": environment_id,
    }
    _graphql(token, query, variables)


def main() -> int:
    """Configure FOMS-cron and redeploy."""
    args = _parse_args()
    service_id, environment_id, branch = _target_config(args.target)
    token = _load_token()
    fields = _introspect_update_input(token)
    print("Target:", args.target)
    print("ServiceInstanceUpdateInput fields:", ", ".join(fields))

    before = _get_service_instance(token, service_id, environment_id)
    print("Before:", json.dumps(before, ensure_ascii=False, indent=2))

    update_input: dict[str, str] = {
        "startCommand": CRON_START_COMMAND,
        "cronSchedule": CRON_SCHEDULE,
    }
    if "railwayConfigFile" in fields:
        update_input["railwayConfigFile"] = CONFIG_PATH
    elif "configFilePath" in fields:
        update_input["configFilePath"] = CONFIG_PATH
    elif "railwayConfigPath" in fields:
        update_input["railwayConfigPath"] = CONFIG_PATH

    print("Planned branch:", branch)
    print("Planned update:", json.dumps(update_input, ensure_ascii=False, indent=2))

    if args.dry_run:
        print("Dry-run only; no mutations applied.")
        return 0

    print("Connecting repo branch...")
    _connect_repo(token, service_id, branch)

    print("Applying service instance update...")
    _update_service_instance(token, service_id, environment_id, update_input)

    after = _get_service_instance(token, service_id, environment_id)
    print("After:", json.dumps(after, ensure_ascii=False, indent=2))

    print("Triggering redeploy...")
    _redeploy(token, service_id, environment_id)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
