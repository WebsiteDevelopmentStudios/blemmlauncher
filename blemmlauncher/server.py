"""BlemmLauncher local Minecraft server manager."""
import json, os, shutil, subprocess, threading, urllib.request, urllib.parse

from . import instances

SERVERS_DIR = os.path.join(instances.LAUNCHERS_ROOT, "servers")
SERVER_TYPES = ("Vanilla", "Paper", "Fabric", "Forge", "NeoForge")
PROCESSES = {}
CALLBACKS = {}

def safe_name(name):
    return bool(name) and name not in (".", "..") and not any(c in name for c in '<>:|?*"') and "/" not in name and chr(92) not in name

def root(name):
    if not safe_name(name):
        raise RuntimeError("Invalid server name.")
    return os.path.join(SERVERS_DIR, name)

def path(name, rel=""):
    base = os.path.abspath(root(name))
    p = os.path.abspath(os.path.join(base, str(rel).replace(chr(92), "/")))
    if os.path.commonpath((base, p)) != base:
        raise RuntimeError("Path escapes the server directory.")
    return p

def _json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BlemmLauncher/1.3.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)

def _download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "BlemmLauncher/1.3.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)

def list_servers():
    os.makedirs(SERVERS_DIR, exist_ok=True)
    return [n for n in sorted(os.listdir(SERVERS_DIR)) if os.path.isfile(os.path.join(SERVERS_DIR, n, "blemm-server.json"))]

def load(name):
    with open(os.path.join(root(name), "blemm-server.json"), encoding="utf-8") as f:
        return json.load(f)

def save(name, cfg):
    with open(os.path.join(root(name), "blemm-server.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def running(name):
    p = PROCESSES.get(name)
    return bool(p and p.poll() is None)

def start(name, callback=None):
    if running(name):
        return
    cfg = load(name)
    jar = cfg.get("jar", "server.jar")
    if not os.path.isfile(path(name, jar)):
        raise RuntimeError("Server JAR not found: " + jar)
    ram = str(cfg.get("ram", "4G"))
    java = cfg.get("java") or "java"
    launch = cfg.get("launch")
    cmd = ([java, "-Xms" + ram, "-Xmx" + ram, "-jar", jar, "nogui"] if not launch
           else (["cmd", "/c", launch] if os.name == "nt" else ["sh", launch]))
    p = subprocess.Popen(cmd, cwd=root(name), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
    PROCESSES[name] = p
    CALLBACKS[name] = callback
    def reader():
        for line in p.stdout:
            cb = CALLBACKS.get(name)
            if cb:
                cb(name, line.rstrip())
        cb = CALLBACKS.get(name)
        if cb:
            cb(name, "Server exited with code " + str(p.poll()))
        PROCESSES.pop(name, None)
        CALLBACKS.pop(name, None)
    threading.Thread(target=reader, daemon=True).start()

def command(name, value):
    p = PROCESSES.get(name)
    if not p or p.poll() is not None:
        raise RuntimeError("Server is not running.")
    p.stdin.write(str(value) + chr(10))
    p.stdin.flush()

def stop(name):
    if running(name):
        command(name, "stop")

def kill(name):
    p = PROCESSES.get(name)
    if p and p.poll() is None:
        p.terminate()

def delete(name):
    if running(name):
        kill(name)
    shutil.rmtree(root(name), ignore_errors=True)

def tree(name, rel=""):
    folder = path(name, rel)
    base = root(name)
    if not os.path.isdir(folder):
        raise RuntimeError("Directory not found.")
    out = []
    for n in sorted(os.listdir(folder), key=lambda x: (not os.path.isdir(os.path.join(folder, x)), x.lower())):
        p = os.path.join(folder, n)
        out.append({"name": n, "path": os.path.relpath(p, base).replace(os.sep, "/"), "dir": os.path.isdir(p), "size": os.path.getsize(p) if os.path.isfile(p) else 0})
    return out

def read_file(name, rel):
    p = path(name, rel)
    if not os.path.isfile(p):
        raise RuntimeError("File not found.")
    if os.path.getsize(p) > 2000000:
        raise RuntimeError("File is larger than the 2 MB editor limit.")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        raise RuntimeError("Binary files cannot be edited as text.")

def write_file(name, rel, content):
    p = path(name, rel)
    if os.path.isdir(p):
        raise RuntimeError("Cannot write to a directory.")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

def create_folder(name, rel):
    os.makedirs(path(name, rel), exist_ok=True)

def create_file(name, rel, content=""):
    write_file(name, rel, content)

def remove(name, rel):
    p = path(name, rel)
    if os.path.isdir(p):
        shutil.rmtree(p)
    elif os.path.isfile(p):
        os.remove(p)

def rename(name, old, new):
    os.replace(path(name, old), path(name, new))

def versions(kind, limit=80):
    """Load selectable release versions, falling back to Mojang if a provider fails."""
    kind = str(kind).lower().strip()
    try:
        if kind in ("vanilla", "fabric"):
            data = _json("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
            return [x["id"] for x in data.get("versions", []) if x.get("type") == "release"][:limit]
        if kind == "paper":
            data = _json("https://api.papermc.io/v2/projects/paper")
            vals = list(reversed(data.get("versions", [])))
            return vals[:limit] or versions("vanilla", limit)
        if kind == "forge":
            data = _json("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json")
            vals = sorted({k[:-11] for k in data.get("promos", {}) if k.endswith("-recommended")}, reverse=True)
            return vals[:limit] or versions("vanilla", limit)
        if kind == "neoforge":
            data = _json("https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge")
            builds = data if isinstance(data, list) else data.get("versions", [])
            vals = []
            for build in builds:
                p = str(build).split(".")
                if len(p) >= 2 and p[0].isdigit() and p[1].isdigit():
                    mc = p[0] + "." + p[1]
                    if mc not in vals:
                        vals.append(mc)
            return vals[:limit] or versions("vanilla", limit)
        return versions("vanilla", limit)
    except Exception:
        data = _json("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
        return [x["id"] for x in data.get("versions", []) if x.get("type") == "release"][:limit]

def create(name, kind, version, ram="4G", java="java"):
    if not safe_name(name):
        raise RuntimeError("Invalid server name.")
    if not version:
        raise RuntimeError("Select a version.")
    d = root(name)
    if os.path.exists(d) and os.listdir(d):
        raise RuntimeError("That server already exists and contains files.")
    os.makedirs(d, exist_ok=True)
    kind = str(kind).lower()
    version = str(version)
    if kind == "vanilla":
        manifest = _json("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
        entry = next((x for x in manifest["versions"] if x["id"] == version), None)
        if not entry:
            raise RuntimeError("Minecraft version not found.")
        meta = _json(entry["url"])
        url = meta.get("downloads", {}).get("server", {}).get("url")
        if not url:
            raise RuntimeError("No official server JAR exists for this version.")
        _download(url, os.path.join(d, "server.jar"))
    elif kind == "paper":
        data = _json("https://api.papermc.io/v2/projects/paper/versions/" + urllib.parse.quote(version, safe=""))
        builds = data.get("builds", [])
        if not builds:
            raise RuntimeError("No Paper build found for " + version)
        build = builds[-1]
        url = "https://api.papermc.io/v2/projects/paper/versions/" + urllib.parse.quote(version, safe="") + "/builds/" + str(build) + "/downloads/paper-" + version + "-" + str(build) + ".jar"
        _download(url, os.path.join(d, "server.jar"))
    elif kind == "fabric":
        installers = _json("https://meta.fabricmc.net/v2/versions/installer")
        installer = os.path.join(d, "fabric-installer.jar")
        _download(installers[0]["url"], installer)
        r = subprocess.run([java, "-jar", "fabric-installer.jar", "server", "-mcversion", version, "-downloadMinecraft"], cwd=d, capture_output=True, text=True, timeout=900)
        if r.returncode:
            raise RuntimeError((r.stderr or r.stdout or "Fabric installer failed")[-2000:])
        os.remove(installer)
    elif kind == "forge":
        promos = _json("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json").get("promos", {})
        build = promos.get(version + "-recommended") or promos.get(version + "-latest")
        if not build:
            raise RuntimeError("No Forge build found for " + version)
        installer = os.path.join(d, "forge-installer.jar")
        _download("https://maven.minecraftforge.net/net/minecraftforge/forge/" + version + "-" + build + "/forge-" + version + "-" + build + "-installer.jar", installer)
        r = subprocess.run([java, "-jar", "forge-installer.jar", "--installServer"], cwd=d, capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise RuntimeError((r.stderr or r.stdout or "Forge installer failed")[-2500:])
        os.remove(installer)
    elif kind == "neoforge":
        data = _json("https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge")
        builds = data if isinstance(data, list) else data.get("versions", [])
        candidates = [str(x) for x in builds if str(x).startswith(version + ".")]
        if not candidates:
            raise RuntimeError("No NeoForge build found for " + version)
        build = sorted(candidates)[-1]
        installer = os.path.join(d, "neoforge-installer.jar")
        _download("https://maven.neoforged.net/releases/net/neoforged/neoforge/" + build + "/neoforge-" + build + "-installer.jar", installer)
        r = subprocess.run([java, "-jar", "neoforge-installer.jar", "--installServer"], cwd=d, capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise RuntimeError((r.stderr or r.stdout or "NeoForge installer failed")[-2500:])
        os.remove(installer)
    jar = "server.jar" if os.path.isfile(os.path.join(d, "server.jar")) else "fabric-server-launch.jar"
    launch = None
    if kind in ("forge", "neoforge"):
        launch = "run.bat" if os.path.isfile(os.path.join(d, "run.bat")) else ("run.sh" if os.path.isfile(os.path.join(d, "run.sh")) else None)
        if not launch:
            raise RuntimeError(kind.title() + " installer did not create a run script.")
    cfg = {"name": name, "type": kind.title(), "version": version, "ram": ram, "java": java, "jar": jar, "launch": launch}
    save(name, cfg)
    return cfg
