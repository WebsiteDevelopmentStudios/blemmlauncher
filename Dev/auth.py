"""Cloudflare Worker developer authentication for BlemmLauncher.

Developer credentials live on the Cloudflare Worker/D1 database. The launcher
only sends the username/password over HTTPS and receives a short-lived token.
No developer password is saved locally.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from typing import Optional

try:
    import certifi
except ImportError:
    certifi = None

DEV_AUTH_URL = os.environ.get(
    "BLEMM_DEV_AUTH_URL",
    "https://blemmlauncher-dev-auth.wowgrayhaha.workers.dev",
).strip().rstrip("/")

# Cloudflare can reject requests that look like an unrecognized automation
# client. Use a stable desktop-app user agent instead of urllib's default
# Python signature. This does not disable TLS verification or Cloudflare
# security; it simply identifies the client normally.
USER_AGENT = "BlemmLauncher/1.0 (Windows; Developer Authentication)"


def _ssl_context() -> ssl.SSLContext:
    """Build a verified TLS context using certifi when available."""
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _request(
    path: str,
    method: str = "GET",
    body: Optional[dict] = None,
    token: Optional[str] = None,
) -> dict:
    """Make a JSON request to the Worker with secure TLS and useful diagnostics."""
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = "Bearer " + token

    request = urllib.request.Request(
        DEV_AUTH_URL + path,
        data=payload,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=20,
            context=_ssl_context(),
        ) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            raw_error = exc.read().decode("utf-8")
            try:
                detail = json.loads(raw_error)
            except json.JSONDecodeError:
                detail = {}
        except Exception:
            raw_error = ""
            detail = {}

        # Cloudflare's block pages are HTML rather than Worker JSON. Surface
        # that fact directly instead of reducing it to an unhelpful 403.
        if exc.code in (403, 429) and (
            "cloudflare" in raw_error.lower()
            or "browser" in raw_error.lower()
            or "blocked" in raw_error.lower()
        ):
            raise RuntimeError(
                "Cloudflare blocked the launcher request before it reached the "
                "developer authentication Worker. The Worker itself is online, "
                "but Cloudflare security is rejecting this client."
            ) from exc

        raise RuntimeError(
            detail.get("error")
            or detail.get("detail")
            or f"Developer service returned HTTP {exc.code}."
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise RuntimeError(
                "Secure HTTPS verification failed for the Cloudflare developer "
                "authentication Worker. The launcher includes its own CA bundle."
            ) from exc
        if isinstance(reason, socket.gaierror):
            raise RuntimeError(
                "Could not resolve the Cloudflare developer authentication Worker "
                f"({DEV_AUTH_URL}). Check your internet/DNS connection."
            ) from exc
        if isinstance(reason, TimeoutError):
            raise RuntimeError(
                "The Cloudflare developer authentication Worker timed out. "
                "Check your internet connection and Cloudflare Worker deployment."
            ) from exc
        raise RuntimeError(
            "Could not connect to the Cloudflare developer authentication Worker: "
            f"{reason}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            "The Cloudflare developer authentication Worker timed out."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "The Cloudflare developer authentication Worker returned invalid JSON."
        ) from exc


def login(username: str, password: str) -> Optional[dict]:
    """Authenticate a developer against the Cloudflare Worker."""
    username = (username or "").strip()
    if not username or not password:
        raise RuntimeError("Enter your developer username and password.")

    return _request(
        "/login",
        "POST",
        {"username": username, "password": password},
    )


def list_developers(token: str) -> list[dict]:
    return _request("/developers", "GET", token=token).get("developers", [])


def create_developer(token: str, username: str, password: str) -> dict:
    return _request(
        "/developers",
        "POST",
        {"username": username, "password": password},
        token,
    )


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
    return _request(
        "/developers/" + quote(username, safe=""),
        "DELETE",
        token=token,
    )


def create_agent_pairing(token: str) -> dict:
    return _request("/agents/pair", "POST", token=token)


def claim_agent(pairing_code: str, name: str) -> dict:
    return _request(
        "/agents/claim",
        "POST",
        {"code": pairing_code, "name": name},
    )


def register_owner_agent(token: str, name: str = "") -> dict:
    return _request(
        "/agents/owner/register",
        "POST",
        {"name": name} if name else {},
        token,
    )


def list_agents(token: str) -> list[dict]:
    return _request("/agents", "GET", token=token).get("agents", [])


def send_agent_command(
    token: str,
    agent_id: str,
    action: str,
    payload: Optional[dict] = None,
) -> dict:
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


def create_agent_pairing(token: str) -> dict:
    return _request("/agents/pair", "POST", token=token)


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
