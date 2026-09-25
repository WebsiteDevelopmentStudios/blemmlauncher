"""BlemmLauncher local Minecraft server manager."""
import json, os, shutil, subprocess, threading, urllib.request, urllib.parse
from . import instances

SERVERS_DIR = os.path.join(instances.LAUNCHERS_ROOT, "servers")
SERVER_TYPES = ("Vanilla", "Paper", "Fabric", "Forge", "NeoForge")
PROCESSES, CALLBACKS = {}, {}

def safe_name(name):
    return bool(name) and name not in (".", "..") and not any(c in name for c in '<>:|?*"') and "/" not in name and "\\" not in name

def root(name):
    if not safe_name(name): raise RuntimeError("Invalid server name.")
    return os.path.join(SERVERS_DIR, name)

def path(name, rel=""):
    base, p = os.path.abspath(root(name)), os.path.abspath(os.path.join(root(name), str(rel).replace("\\", "/")))
    if os.path.commonpath((base, p)) != base: raise RuntimeError("Path escapes the server directory.")
    return p

def _request(url, load_json=True, dest=None):
    req = urllib.request.Request(url, headers={"User-Agent": "BlemmLauncher/1.3.0"})
    with urllib.request.urlopen(req, timeout=180 if dest else 40) as r:
        if dest:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".part"
            with open(tmp, "wb") as f: shutil.copyfileobj(r, f)
            os.replace(tmp, dest)
        else: return json.load(r)

def list_servers():
    os.makedirs(SERVERS_DIR, exist_ok=True)
    return [n for n in sorted(os.listdir(SERVERS_DIR)) if os.path.isfile(os.path.join(SERVERS_DIR, n, "blemm-server.json"))]

def load(name):
    with open(os.path.join(root(name), "blemm-server.json"), encoding="utf-8") as f: return json.load(f)

def save(name, cfg):
    with open(os.path.join(root(name), "blemm-server.json"), "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2)

def running(name):
    p = PROCESSES.get(name)
    return bool(p and p.poll() is None)

def start(name, callback=None):
    if running(name): return
    cfg = load(name)
    jar, ram, java, launch = cfg.get("jar", "server.jar"), str(cfg.get("ram", "4G")), cfg.get("java", "java"), cfg.get("launch")
    if not os.path.isfile(path(name, jar)): raise RuntimeError("Server JAR not found: " + jar)
    cmd = ([java, "-Xms" + ram, "-Xmx" + ram, "-jar", jar, "nogui"] if not launch else (["cmd", "/c", launch] if os.name == "nt" else ["sh", launch]))
    p = subprocess.Popen(cmd, cwd=root(name), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
    PROCESSES[name], CALLBACKS[name] = p, callback
    def reader():
        for line in p.stdout:
            if CALLBACKS.get(name): CALLBACKS[name](name, line.rstrip())
        if CALLBACKS.get(name): CALLBACKS[name](name, "Server exited with code " + str(p.poll()))
        PROCESSES.pop(name, None); CALLBACKS.pop(name, None)
    threading.Thread(target=reader, daemon=True).start()

def command(name, value):
    p = PROCESSES.get(name)
    if not p or p.poll() is not None: raise RuntimeError("Server is not running.")
    p.stdin.write(str(value) + "\n"); p.stdin.flush()

def stop(name):
    if running(name): command(name, "stop")

def kill(name):
    p = PROCESSES.get(name)
    if p and p.poll() is None: p.terminate()

def delete(name):
    if running(name): kill(name)
    shutil.rmtree(root(name), ignore_errors=True)

def tree(name, rel=""):
    folder = path(name, rel)
    if not os.path.isdir(folder): raise RuntimeError("Directory not found.")
    return [{"name": n, "path": os.path.relpath(os.path.join(folder, n), root(name)).replace(os.sep, "/"), "dir": os.path.isdir(os.path.join(folder, n)), "size": os.path.getsize(os.path.join(folder, n)) if os.path.isfile(os.path.join(folder, n)) else 0} for n in sorted(os.listdir(folder), key=lambda x: (not os.path.isdir(os.path.join(folder, x)), x.lower()))]

def read_file(name, rel):
    p = path(name, rel)
    if not os.path.isfile(p): raise RuntimeError("File not found.")
    if os.path.getsize(p) > 2000000: raise RuntimeError("File is larger than the 2 MB editor limit.")
    try:
        with open(p, encoding="utf-8") as f: return f.read()
    except UnicodeDecodeError: raise RuntimeError("Binary files cannot be edited as text.")

def write_file(name, rel, content):
    p = path(name, rel)
    if os.path.isdir(p): raise RuntimeError("Cannot write to a directory.")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: f.write(content)

def create_folder(name, rel): os.makedirs(path(name, rel), exist_ok=True)
def create_file(name, rel, content=""): write_file(name, rel, content)
def remove(name, rel):
    p = path(name, rel)
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p) if os.path.isfile(p) else None
def rename(name, old, new): os.replace(path(name, old), path(name, new))

def versions(kind, limit=80):
    kind = str(kind).lower().strip()
    try:
        if kind in ("vanilla", "fabric"):
            return [x["id"] for x in _request("https://mojang.com")["versions"] if x.get("type") == "release"][:limit]
        if kind == "paper":
            # Migrated from v2 to modern v3 tracking index endpoint
            return list(reversed(_request("https://papermc.io")["versions"]))[:limit]
        if kind == "forge":
            return sorted({k[:-11] for k in _request("https://minecraftforge.net")["promos"] if k.endswith("-recommended")}, reverse=True)[:limit]
        if kind == "neoforge":
            return list(dict.fromkeys([".".join(str(b).split(".")[:2]) for b in _request("https://neoforged.net")["versions"] if len(str(b).split(".")) >= 2]))[:limit]
    except Exception: pass
    return [x["id"] for x in _request("https://mojang.com")["versions"] if x.get("type") == "release"][:limit]

def create(name, kind, version, ram="4G", java="java"):
    if not safe_name(name): raise RuntimeError("Invalid server name.")
    if not version: raise RuntimeError("Select a version.")
    d = root(name)
    if os.path.exists(d) and os.listdir(d): raise RuntimeError("That server already exists and contains files.")
    os.makedirs(d, exist_ok=True)
    kind, version = str(kind).lower(), str(version)
    
    if kind == "vanilla":
        entry = next((x for x in _request("https://mojang.com")["versions"] if x["id"] == version), None)
        if not entry: raise RuntimeError("Minecraft version not found.")
        url = _request(entry["url"]).get("downloads", {}).get("server", {}).get("url")
        if not url: raise RuntimeError("No official server JAR exists for this version.")
        _request(url, dest=os.path.join(d, "server.jar"))
    elif kind == "paper":
        # Completely rewritten using modern v3 structure mappings
        v_url = "https://papermc.io/versions/" + urllib.parse.quote(version)
        data = _request(v_url)
        builds = data.get("builds", [])
        if not builds: raise RuntimeError("No Paper build found for " + version)
        build = builds[-1]
        
        # Build the functional v3 download URI template
        url = v_url + "/builds/" + str(build) + "/downloads/paper-" + version + "-" + str(build) + ".jar"
        _request(url, dest=os.path.join(d, "server.jar"))
    elif kind in ("fabric", "forge", "neoforge"):
        installer = os.path.join(d, kind + "-installer.jar")
        if kind == "fabric":
            _request(_request("https://fabricmc.net")["url"], dest=installer)
            args = [java, "-jar", kind + "-installer.jar", "server", "-mcversion", version, "-downloadMinecraft"]
        elif kind == "forge":
            build = _request("https://minecraftforge.net")["promos"].get(version + "-recommended") or _request("https://minecraftforge.net")["promos"].get(version + "-latest")
            if not build: raise RuntimeError("No Forge build found for " + version)
            _request("https://minecraftforge.net" + version + "-" + build + "/forge-" + version + "-" + build + "-installer.jar", dest=installer)
            args = [java, "-jar", kind + "-installer.jar", "--installServer"]
        elif kind == "neoforge":
            build = sorted([str(x) for x in _request("https://neoforged.net")["versions"] if str(x).startswith(version + ".")])[-1]
            _request("https://neoforged.net" + build + "/neoforge-" + build + "-installer.jar", dest=installer)
            args = [java, "-jar", kind + "-installer.jar", "--installServer"]
        r = subprocess.run(args, cwd=d, capture_output=True, text=True, timeout=900 if kind == "fabric" else 1800)
        if r.returncode: raise RuntimeError((r.stderr or r.stdout or (kind.title() + " installer failed"))[-2000:])
        os.remove(installer)

    jar = "server.jar" if os.path.isfile(os.path.join(d, "server.jar")) else "fabric-server-launch.jar"
    launch = "run.bat" if os.path.isfile(os.path.join(d, "run.bat")) else ("run.sh" if os.path.isfile(os.path.join(d, "run.sh")) else None)
    if kind in ("forge", "neoforge") and not launch: raise RuntimeError(kind.title() + " installer did not create a run script.")
    cfg = {"name": name, "type": kind.title(), "version": version, "ram": ram, "java": java, "jar": jar, "launch": launch}
    save(name, cfg)
    return cfg
