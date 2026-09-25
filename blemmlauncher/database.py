"""Persistent launcher metadata storage.

The actual Minecraft files remain in instances/ and servers/. This JSON
registry keeps the launcher aware of them across restarts and automatically
repairs the registry from existing folders.
"""
import json
import os
import threading

LAUNCHERS_ROOT = os.environ.get(
    "BLEMM_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "minecraft")
)
DATABASE_DIR = os.path.join(LAUNCHERS_ROOT, "database")
LOCK = threading.RLock()

def _path(kind):
    if kind not in ("instances", "servers"):
        raise ValueError("Unknown database kind: " + str(kind))
    return os.path.join(DATABASE_DIR, kind + ".json")

def load(kind):
    with LOCK:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        p = _path(kind)
        if not os.path.isfile(p):
            return []
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError, TypeError):
            return []

def save(kind, names):
    with LOCK:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        p = _path(kind)
        tmp = p + ".tmp"
        values = sorted(dict.fromkeys(str(x) for x in names if str(x)))
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(values, f, indent=2)
        os.replace(tmp, p)
        return values

def register(kind, name):
    names = load(kind)
    if name not in names:
        names.append(name)
    return save(kind, names)

def unregister(kind, name):
    return save(kind, [x for x in load(kind) if x != name])

def reconcile(kind, filesystem_names):
    names = set(load(kind))
    names.update(str(x) for x in filesystem_names if str(x))
    return save(kind, names)
