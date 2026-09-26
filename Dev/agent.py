"""BlemmLauncher remote developer server agent.

Run this on the computer that hosts the Minecraft server:
    python -m Dev.agent

The agent keeps the Minecraft server local and only makes outbound HTTPS
requests to the Cloudflare Worker. The one-time pairing code is used to
exchange for a long-lived agent token, which is stored locally in Dev/.agent.json.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque

WORKER_URL = os.environ.get(
    "BLEMM_DEV_AUTH_URL",
    "https://blemmlauncher-dev-auth.wowgrayhaha.workers.dev",
).strip().rstrip("/")

STATE_DIR = os.environ.get("BLEMM_AGENT_STATE_DIR", os.path.dirname(__file__))
STATE_PATH = os.path.join(STATE_DIR, ".agent.json")
LOG_LIMIT = 500


def http(method: str, path: str, payload=None, token: str | None = None, timeout=30):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token

    req = urllib.request.Request(WORKER_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {}
        raise RuntimeError(detail.get("error", "Remote server request failed.")) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach the BlemmLauncher server relay.") from exc


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("agent_token") and data.get("agent_id"):
            return data
    except Exception:
        pass
    return {}


def save_state(data):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def pair():
    print("\nBlemmLauncher Developer Server Agent")
    print("Open the Developer tab in BlemmLauncher and choose 'Generate Pairing Code'.")
    code = input("Pairing code: ").strip().upper()
    if not code:
        raise RuntimeError("A pairing code is required.")
    default_name = socket.gethostname() or "Developer Server"
    name = input("Agent/server PC name [" + default_name + "]: ").strip() or default_name
    result = http("POST", "/agents/claim", {"code": code, "name": name})
    state = {
        "agent_id": result["agent_id"],
        "agent_token": result["agent_token"],
        "name": result.get("name", name),
    }
    save_state(state)
    print("Paired successfully as:", state["name"])
    print("This agent token is stored locally. Do not share Dev/.agent.json.")
    return state


class Agent:
    def __init__(self, state):
        self.state = state
        self.logs = deque(maxlen=LOG_LIMIT)
        self.lock = threading.Lock()

    @property
    def token(self):
        return self.state["agent_token"]

    @property
    def agent_id(self):
        return self.state["agent_id"]

    def log(self, name, line):
        with self.lock:
            self.logs.append({"server": name, "line": str(line), "time": time.time()})

    def callback(self, name, line):
        self.log(name, line)

    def status(self):
        from blemmlauncher import server
        servers = []
        for name in server.list_servers():
            try:
                cfg = server.load(name)
                servers.append({
                    "name": name,
                    "running": bool(server.running(name)),
                    "type": cfg.get("type"),
                    "version": cfg.get("version"),
                    "ram": cfg.get("ram"),
                })
            except Exception:
                servers.append({"name": name, "running": bool(server.running(name))})
        return {"servers": servers}

    def execute(self, action, payload):
        from blemmlauncher import server

        name = str(payload.get("server", "")).strip()

        if action == "status":
            return self.status()

        if action == "start":
            if not name:
                raise RuntimeError("Choose a server.")
            server.start(name, self.callback)
            return {"server": name, "running": True}

        if action == "stop":
            if not name:
                raise RuntimeError("Choose a server.")
            server.stop(name)
            return {"server": name, "running": False}

        if action == "restart":
            if not name:
                raise RuntimeError("Choose a server.")
            server.stop(name)
            time.sleep(1.5)
            server.start(name, self.callback)
            return {"server": name, "running": True}

        if action == "console":
            if not name:
                raise RuntimeError("Choose a server.")
            command = str(payload.get("command", "")).strip()
            if not command:
                raise RuntimeError("Console command is empty.")
            server.command(name, command)
            self.log(name, "> " + command)
            return {"server": name, "sent": command}

        if action == "logs":
            with self.lock:
                lines = list(self.logs)
            if name:
                lines = [x for x in lines if x["server"] == name]
            return {"server": name, "lines": lines[-200:]}

        if action == "versions":
            kind = str(payload.get("type", "vanilla")).strip().lower()
            limit = int(payload.get("limit", 80))
            limit = max(1, min(limit, 200))
            return {"type": kind, "versions": server.versions(kind, limit)}

        if action == "create_server":
            if not name:
                raise RuntimeError("Choose a server name.")
            kind = str(payload.get("type", "vanilla")).strip().lower()
            version = str(payload.get("version", "")).strip()
            ram = str(payload.get("ram", "4G")).strip() or "4G"
            return server.create(name, kind, version, ram=ram, allow_reserved=True)

        if action == "files":
            if not name:
                raise RuntimeError("Choose a server.")
            rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
            return {"server": name, "path": rel, "files": server.tree(name, rel)}

        if action == "read_file":
            if not name:
                raise RuntimeError("Choose a server.")
            rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
            return {"server": name, "path": rel, "content": server.read_file(name, rel)}

        if action == "write_file":
            if not name:
                raise RuntimeError("Choose a server.")
            rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
            content = str(payload.get("content", ""))
            if len(content.encode("utf-8")) > 5 * 1024 * 1024:
                raise RuntimeError("Remote editor writes are limited to 5 MB.")
            server.write_file(name, rel, content)
            return {"server": name, "path": rel, "saved": True}

        if action == "import_file":
            if not name:
                raise RuntimeError("Choose a server.")
            rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
            encoded = str(payload.get("data", ""))
            import base64
            try:
                data = base64.b64decode(encoded, validate=True)
            except Exception:
                raise RuntimeError("Invalid imported file data.")
            if len(data) > 50 * 1024 * 1024:
                raise RuntimeError("Imported files are limited to 50 MB.")
            destination = server.path(name, rel)
            if os.path.isdir(destination):
                raise RuntimeError("Import destination is a directory.")
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "wb") as f:
                f.write(data)
            return {"server": name, "path": rel, "size": len(data), "imported": True}

        if action == "create_folder":
            if not name:
                raise RuntimeError("Choose a server.")
            rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
            server.create_folder(name, rel)
            return {"server": name, "path": rel, "created": True}

        if action == "create_file":
            if not name:
                raise RuntimeError("Choose a server.")
            rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
            content = str(payload.get("content", ""))
            server.create_file(name, rel, content)
            return {"server": name, "path": rel, "created": True}

        if action == "delete_file":
            if not name:
                raise RuntimeError("Choose a server.")
            rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
            if not rel:
                raise RuntimeError("Cannot delete the server root.")
            server.remove(name, rel)
            return {"server": name, "path": rel, "deleted": True}

        if action == "rename_file":
            if not name:
                raise RuntimeError("Choose a server.")
            old = str(payload.get("old", "")).replace("\\", "/").strip("/")
            new = str(payload.get("new", "")).replace("\\", "/").strip("/")
            if not old or not new:
                raise RuntimeError("Both old and new paths are required.")
            server.rename(name, old, new)
            return {"server": name, "old": old, "new": new}

        if action == "delete_server":
            if not name:
                raise RuntimeError("Choose a server.")
            server.delete(name)
            return {"server": name, "deleted": True}

        raise RuntimeError("Unsupported action: " + action)

    def heartbeat(self):
        try:
            http("POST", "/agent/heartbeat", {"status": "online"}, self.token, timeout=10)
        except Exception:
            pass

    def poll_once(self):
        response = http("GET", "/agent/poll", token=self.token, timeout=20)
        command = response.get("command")
        if not command:
            return
        try:
            result = self.execute(command["action"], command.get("payload") or {})
            status = "completed"
        except Exception as exc:
            result = {"error": str(exc)}
            status = "error"
        try:
            http("POST", "/agent/result", {
                "command_id": command["id"],
                "status": status,
                "result": result,
            }, self.token, timeout=20)
        except Exception as exc:
            print("Could not report command result:", exc)


def main():
    state = load_state()
    if not state:
        state = pair()

    agent = Agent(state)
    print("Remote developer server agent is running.")
    print("Press Ctrl+C to stop it. Your Minecraft server remains local.")
    last_heartbeat = 0.0

    while True:
        try:
            now = time.time()
            if now - last_heartbeat >= 8:
                agent.heartbeat()
                last_heartbeat = now
            agent.poll_once()
            time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nAgent stopped.")
            return
        except Exception as exc:
            print("Agent connection:", exc)
            time.sleep(3)


if __name__ == "__main__":
    main()
