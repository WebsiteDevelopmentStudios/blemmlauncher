"""Cloudflare-based developer authentication for BlemmLauncher.

The desktop launcher opens a browser for Cloudflare Access authentication.
After Access succeeds, the Worker redirects to a temporary localhost callback.
The launcher exchanges the short-lived code with the Worker.

Set BLEMM_DEV_AUTH_URL to your deployed Worker URL.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

DEFAULT_TIMEOUT = 180
DEV_AUTH_URL = os.environ.get("BLEMM_DEV_AUTH_URL", "").strip().rstrip("/")


class _CallbackHandler(BaseHTTPRequestHandler):
    result = None
    event = None
    expected_state = None

    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return

        query = urllib.parse.parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]

        if not _CallbackHandler.expected_state or state != _CallbackHandler.expected_state:
            _CallbackHandler.result = {"error": "Invalid authentication state."}
        elif not code:
            _CallbackHandler.result = {
                "error": query.get("error", ["Developer authentication was cancelled."])[0]
            }
        else:
            _CallbackHandler.result = {"code": code}

        body = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>BlemmLauncher</title></head>
<body style="font-family:system-ui;background:#07110b;color:#9CFFBC;padding:40px">
<h2>BlemmLauncher developer login</h2>
<p>You can return to BlemmLauncher now.</p>
<script>window.close()</script>
</body></html>"""
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

        if _CallbackHandler.event:
            _CallbackHandler.event.set()


def _start_callback_server(state: str):
    event = threading.Event()
    _CallbackHandler.result = None
    _CallbackHandler.event = event
    _CallbackHandler.expected_state = state

    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.timeout = 0.5
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, event


def _exchange_code(code: str) -> dict:
    endpoint = DEV_AUTH_URL + "/token"
    payload = json.dumps({"code": code}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
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
        raise RuntimeError(detail.get("error", "Developer authentication failed.")) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Could not reach the Cloudflare developer authentication Worker.") from exc

    if not data.get("authenticated") or not data.get("developer"):
        raise RuntimeError("Cloudflare did not authenticate this account as a developer.")
    return data


def login(timeout: int = DEFAULT_TIMEOUT) -> Optional[dict]:
    """Open Cloudflare Access and return developer identity information."""
    if not DEV_AUTH_URL:
        raise RuntimeError(
            "BLEMM_DEV_AUTH_URL is not configured. Set it to your deployed Cloudflare Worker URL."
        )

    state = secrets.token_urlsafe(32)
    server, event = _start_callback_server(state)
    port = server.server_address[1]

    redirect = f"http://127.0.0.1:{port}/callback"
    params = urllib.parse.urlencode({
        "redirect": redirect,
        "state": state,
    })
    authorize_url = DEV_AUTH_URL + "/authorize?" + params

    try:
        if not webbrowser.open(authorize_url):
            raise RuntimeError("Could not open the developer login browser.")
        if not event.wait(timeout):
            raise RuntimeError("Developer login timed out.")

        result = _CallbackHandler.result or {}
        if result.get("error"):
            raise RuntimeError(str(result["error"]))

        return _exchange_code(result["code"])
    finally:
        server.shutdown()
        server.server_close()
        _CallbackHandler.event = None
        _CallbackHandler.expected_state = None
        _CallbackHandler.result = None


if __name__ == "__main__":
    try:
        identity = login()
        print("Developer login successful.")
        print("Developer:", identity.get("email", "unknown"))
    except Exception as exc:
        print("Developer login failed:", exc)
