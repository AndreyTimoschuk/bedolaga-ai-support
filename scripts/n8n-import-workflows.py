#!/usr/bin/env python3
"""Bootstrap n8n for e2e: owner setup, credentials, import workflows, activate."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "PROJECT · Support Output": ROOT / "n8n/workflows/support-output.json",
    "PROJECT · Support AI": ROOT / "n8n/workflows/support-ai.json",
    "PROJECT · Support Main": ROOT / "n8n/workflows/support-main.json",
}


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def wait_n8n(client: httpx.Client, timeout: float = 120.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = client.get("/healthz")
            if r.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        try:
            r = client.get("/")
            if r.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("n8n did not become ready")


def ensure_owner(client: httpx.Client, env: dict[str, str]) -> None:
    email = env.get("N8N_OWNER_EMAIL", "e2e@example.com")
    password = env.get("N8N_OWNER_PASSWORD", "E2eOwnerPass123!")
    first = env.get("N8N_OWNER_FIRST_NAME", "E2E")
    last = env.get("N8N_OWNER_LAST_NAME", "Owner")

    r = client.get("/rest/settings")
    r.raise_for_status()
    settings = r.json()
    # showSetupOnFirstLoad / userManagement
    um = (settings.get("data") or settings).get("userManagement") or {}
    if um.get("showSetupOnFirstLoad") is False or um.get("quota") == 0:
        # already set up — try login
        login(client, email, password)
        return

    payload = {
        "email": email,
        "firstName": first,
        "lastName": last,
        "password": password,
    }
    r = client.post("/rest/owner/setup", json=payload)
    if r.status_code in (200, 201, 204):
        login(client, email, password)
        return
    # maybe already created
    if r.status_code in (400, 409):
        login(client, email, password)
        return
    r.raise_for_status()


def login(client: httpx.Client, email: str, password: str) -> None:
    r = client.post("/rest/login", json={"emailOrLdapLoginId": email, "password": password})
    if r.status_code >= 400:
        # older n8n field name
        r = client.post("/rest/login", json={"email": email, "password": password})
    r.raise_for_status()


def upsert_credential(client: httpx.Client, name: str, cred_type: str, data: dict) -> str:
    r = client.get("/rest/credentials")
    r.raise_for_status()
    body = r.json()
    items = body.get("data") if isinstance(body, dict) else body
    for item in items or []:
        if item.get("name") == name and item.get("type") == cred_type:
            cid = item["id"]
            # patch data
            client.patch(f"/rest/credentials/{cid}", json={"name": name, "type": cred_type, "data": data})
            return str(cid)

    r = client.post(
        "/rest/credentials",
        json={"name": name, "type": cred_type, "data": data},
    )
    r.raise_for_status()
    created = r.json()
    data_obj = created.get("data") or created
    return str(data_obj["id"])


def patch_workflow_tokens(raw: str, user_token: str) -> dict:
    text = raw.replace("USER_BOT_TOKEN", user_token)
    return json.loads(text)


def list_workflows(client: httpx.Client) -> list[dict]:
    r = client.get("/rest/workflows")
    r.raise_for_status()
    body = r.json()
    data = body.get("data") if isinstance(body, dict) else body
    if isinstance(data, dict):
        data = data.get("data") or data.get("workflows") or []
    return data or []


def import_or_update_workflow(client: httpx.Client, name: str, wf: dict) -> str:
    existing = {w.get("name"): w for w in list_workflows(client)}
    wf = dict(wf)
    wf["name"] = name
    for key in ("id", "versionId", "meta", "pinData", "tags", "shared", "activeVersionId", "versionCounter"):
        wf.pop(key, None)
    wf["active"] = False

    payload = {
        k: wf[k]
        for k in ("name", "nodes", "connections", "settings", "staticData", "pinData")
        if k in wf
    }
    payload["name"] = name
    payload["active"] = False

    if name in existing:
        wid = str(existing[name]["id"])
        full = client.get(f"/rest/workflows/{wid}").json()
        full = full.get("data") or full
        if full.get("active"):
            client.post(
                f"/rest/workflows/{wid}/deactivate",
                json={"versionId": full.get("versionId")},
            )
        r = client.patch(f"/rest/workflows/{wid}", json=payload)
        r.raise_for_status()
        return wid

    r = client.post("/rest/workflows", json=payload)
    r.raise_for_status()
    created = r.json()
    data_obj = created.get("data") or created
    return str(data_obj["id"])


def rematch_workflow_refs(client: httpx.Client, imported: dict[str, str]) -> None:
    """Point Execute Workflow nodes at real workflow ids (list mode)."""
    by_name = {w["name"]: w for w in list_workflows(client)}
    for name, wid in imported.items():
        full = client.get(f"/rest/workflows/{wid}").json()
        full = full.get("data") or full
        changed = False
        for node in full.get("nodes", []):
            if node.get("type") != "n8n-nodes-base.executeWorkflow":
                continue
            ref = (node.get("parameters") or {}).get("workflowId") or {}
            target_name = ref.get("cachedResultName")
            if not target_name and ref.get("mode") == "name":
                target_name = ref.get("value")
            if target_name in by_name:
                target = by_name[target_name]
                node["parameters"]["workflowId"] = {
                    "__rl": True,
                    "mode": "list",
                    "value": target["id"],
                    "cachedResultName": target["name"],
                }
                changed = True
        if changed:
            payload = {
                k: full[k]
                for k in ("name", "nodes", "connections", "settings", "staticData", "pinData")
                if k in full
            }
            payload["active"] = False
            r = client.patch(f"/rest/workflows/{wid}", json=payload)
            r.raise_for_status()
            print(f"rematched sub-workflow refs in {name}")


def activate(client: httpx.Client, wid: str) -> None:
    full = client.get(f"/rest/workflows/{wid}").json()
    full = full.get("data") or full
    version_id = full.get("versionId")
    r = client.post(
        f"/rest/workflows/{wid}/activate",
        json={"versionId": version_id} if version_id else {},
    )
    r.raise_for_status()


def rematch_credentials(wf: dict, cred_ids: dict[str, str]) -> None:
    """Replace credential name-as-id with real n8n ids by credential name."""

    def walk(obj):
        if isinstance(obj, dict):
            if "credentials" in obj and isinstance(obj["credentials"], dict):
                for _ctype, cdata in obj["credentials"].items():
                    if isinstance(cdata, dict) and "name" in cdata:
                        n = cdata["name"]
                        if n in cred_ids:
                            cdata["id"] = cred_ids[n]
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(wf)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env.test"))
    parser.add_argument("--base-url", default="http://127.0.0.1:5679")
    args = parser.parse_args()

    env = load_env(Path(args.env_file))
    user_token = env["TELEGRAM_USER_BOT_TOKEN"]
    pg_pass = env.get("POSTGRES_PASSWORD", "supportbot")
    pg_user = env.get("POSTGRES_USER", "supportbot")
    pg_db = env.get("POSTGRES_DB", "supportbot")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60.0, follow_redirects=True) as client:
        wait_n8n(client)
        ensure_owner(client, env)

        cred_ids: dict[str, str] = {}
        cred_ids["PROJECT · Support Bot"] = upsert_credential(
            client,
            "PROJECT · Support Bot",
            "telegramApi",
            {"accessToken": user_token},
        )
        cred_ids["Shared · OpenAI"] = upsert_credential(
            client,
            "Shared · OpenAI",
            "openAiApi",
            {"apiKey": env.get("OPENAI_API_KEY") or "sk-dummy"},
        )
        cred_ids["PROJECT · Support DB"] = upsert_credential(
            client,
            "PROJECT · Support DB",
            "postgres",
            {
                "host": "postgres",
                "port": 5432,
                "database": pg_db,
                "user": pg_user,
                "password": pg_pass,
                "ssl": "disable",
            },
        )
        cred_ids["PROJECT · Bedolaga DB"] = upsert_credential(
            client,
            "PROJECT · Bedolaga DB",
            "postgres",
            {
                "host": "postgres",
                "port": 5432,
                "database": pg_db,
                "user": pg_user,
                "password": pg_pass,
                "ssl": "disable",
            },
        )
        cred_ids["PROJECT · Support Redis"] = upsert_credential(
            client,
            "PROJECT · Support Redis",
            "redis",
            {"host": "redis", "port": 6379, "password": ""},
        )
        cred_ids["PROJECT · Qdrant"] = upsert_credential(
            client,
            "PROJECT · Qdrant",
            "qdrantApi",
            {"qdrantApiUrl": "http://qdrant:6333"},
        )

        imported: dict[str, str] = {}
        for name, path in WORKFLOWS.items():
            raw = path.read_text(encoding="utf-8")
            wf = patch_workflow_tokens(raw, user_token)
            rematch_credentials(wf, cred_ids)
            wid = import_or_update_workflow(client, name, wf)
            imported[name] = wid
            print(f"imported {name} -> {wid}")

        rematch_workflow_refs(client, imported)

        for name in (
            "PROJECT · Support Output",
            "PROJECT · Support AI",
            "PROJECT · Support Main",
        ):
            activate(client, imported[name])
            print(f"activated {name}")

    print("n8n import complete")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"n8n-import failed: {exc}", file=sys.stderr)
        raise
