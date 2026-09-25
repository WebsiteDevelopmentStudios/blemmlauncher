"""Cloudflare Worker developer authentication for BlemmLauncher.

Developer credentials live on the Cloudflare Worker/D1 database. The launcher
only sends the username/password over HTTPS and receives a short-lived token.
No developer password is saved locally.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

DEV_AUTH_URL = os.environ.get(
    "BLEMM_DEV_AUTH_URL",
    "https://blemmlauncher-dev-auth.wowgrayhaha.workers.dev",
).strip().rstrip("/")


def login(username: str, password: str) -> Optional[dict]:
    """Authenticate a developer against the Cloudflare Worker."""
    username = (username or "").strip()
    if not username or not password:
        raise RuntimeError("Enter your developer username and password.")

    payload = json.dumps({
        "username": username,
        "password": password,
    }).encode("utf-8")

    request = urllib.request.Request(
        DEV_AUTH_URL + "/login",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {}
        raise RuntimeError(
            detail.get("error", "Developer authentication failed.")
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            "Could not reach the Cloudflare developer authentication Worker."
        ) from exc

    if not data.get("authenticated") or not data.get("developer"):
        raise RuntimeError("Invalid developer username or password.")

    return data

def list_developers(token: str) -> list[dict]:
    return _request("/developers", "GET", token=token).get("developers", [])


def create_developer(token: str, username: str, password: str) -> dict:
    return _request("/developers", "POST", {"username": username, "password": password}, token)


def reset_developer_password(token: str, username: str, password: str) -> dict:
    from urllib.parse import quote
    return _request(
        "/developers/" + quote(username, safe="") + "/reset",
        "POST",
        {"password": password},
        token,
    )


def delete_developer(token: str, username: str) -> dict:
    from urllib.parse import quote
    return _request("/developers/" + quote(username, safe=""), "DELETE", token=token)


def create_agent_pairing(token: str) -> dict:
    return _request("/agents/pair", "POST", token=token)


def claim_agent(pairing_code: str, name: str) -> dict:
    return _request("/agents/claim", "POST", {
        "code": pairing_code,
        "name": name,
    })


def list_agents(token: str) -> list[dict]:
    return _request("/agents", "GET", token=token).get("agents", [])


def send_agent_command(token: str, agent_id: str, action: str, payload: Optional[dict] = None) -> dict:
    from urllib.parse import quote
    return _request(
        "/agents/" + quote(str(agent_id), safe="") + "/command",
        "POST",
        {"action": action, "payload": payload or {}},
        token,
    )


def list_agent_commands(token: str, agent_id: str) -> list[dict]:
    from urllib.parse import quote
    return _request(
        "/agents/" + quote(str(agent_id), safe="") + "/commands",
        "GET",
        token=token,
    ).get("commands", [])


if __name__ == "__main__":
    import getpass

    try:
        username = input("Developer username: ").strip()
        password = getpass.getpass("Developer password: ")
        identity = login(username, password)
        print("Developer login successful.")
        print("Developer:", identity.get("username", "unknown"))
    except Exception as exc:
        print("Developer login failed:", exc)
