"""BlemmLauncher instances - isolated setups, loaders, Modrinth, export/import."""
import json, os, shutil, subprocess, sys, tempfile, zipfile, urllib.parse, urllib.request

LAUNCHERS_ROOT = os.environ.get("BLEMM_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "minecraft"))
INSTANCES_DIR = os.path.join(LAUNCHERS_ROOT, "instances")
SHARED_ASSETS = os.path.join(LAUNCHERS_ROOT, "assets")     # prism-style: assets shared
SHARED_TOOLS = os.path.join(LAUNCHERS_ROOT, "tools")      # java shared

def _fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BlemmLauncher/1.2"})
    with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)

def _download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest): return
    req = urllib.request.Request(url, headers={"User-Agent": "BlemmLauncher/1.2"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(dest + ".part", dest)

# ---------- instance basics ----------
def isafe(name):
    bad = '<>:"/\\|?*'
    return name and not any(c in bad for c in name) and name not in (".", "..")

def instance_dir(name): return os.path.join(INSTANCES_DIR, name)

def list_instances():
    if not os.path.isdir(INSTANCES_DIR): return []
    out = []
    for n in sorted(os.listdir(INSTANCES_DIR)):
        if os.path.exists(os.path.join(INSTANCES_DIR, n, "blemm.json")):
            out.append(n)
    return out

def load_cfg(name):
    with open(os.path.join(instance_dir(name), "blemm.json"), encoding="utf-8") as f:
        return json.load(f)

def save_cfg(name, cfg):
    os.makedirs(instance_dir(name), exist_ok=True)
    with open(os.path.join(instance_dir(name), "blemm.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def create(name, version, loader=None, ram="4G", username="Blemm", build=None):
    """loader: None | 'forge' | 'fabric' | 'neoforge'."""
    if not isafe(name): raise RuntimeError(f"bad instance name '{name}'")
    if name in list_instances(): raise RuntimeError(f"instance '{name}' already exists")
    os.makedirs(instance_dir(name), exist_ok=True)
    for sub in ("mods", "resourcepacks", "shaderpacks", "saves"):
        os.makedirs(os.path.join(instance_dir(name), sub), exist_ok=True)
    cfg = {"name": name, "version": version, "loader": loader, "loader_build": build,
           "ram": ram, "username": username}
    save_cfg(name, cfg)
    return cfg

def delete(name):
    d = instance_dir(name)
    if os.path.isdir(d): shutil.rmtree(d)

def use(name, core):
    """Point core's globals at this instance; share assets/java globally."""
    d = instance_dir(name)
    core.GAME_DIR = d
    core.ASSETS = SHARED_ASSETS
    core.TOOLS = SHARED_TOOLS
    core.LIBS = os.path.join(d, "libraries")
    return d

# ---------- export / import ----------
def export(name, dest_zip):
    d = instance_dir(name)
    if not os.path.isdir(d): raise RuntimeError(f"no instance '{name}'")
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(d):
            if os.sep + "libraries" in root or os.sep + "natives" in root: continue
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.join(name, os.path.relpath(p, d)))

def import_from_zip(src_zip):
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(src_zip) as z: z.extractall(td)
        for n in os.listdir(td):
            if os.path.exists(os.path.join(td, n, "blemm.json")):
                if not isafe(n): raise RuntimeError(f"bad instance name in zip: '{n}'")
                if os.path.exists(instance_dir(n)):
                    i = 1
                    while os.path.exists(instance_dir(f"{n} ({i})")): i += 1
                    n = f"{n} ({i})"
                shutil.move(os.path.join(td, n), instance_dir(n))
                return n
    raise RuntimeError("zip had no instance (missing blemm.json)")

# ---------- desktop shortcut ----------
def shortcut(name):
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    bat = os.path.join(desktop, f"Blemm - {name}.bat")
    exe = sys.executable if sys.executable.lower().endswith("blemmlauncher.exe") \
          else f'"{os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")}"'
    py = f'python' if not sys.executable.lower().endswith("blemmlauncher.exe") else ""
    with open(bat, "w") as f:
        f.write(f'@echo off\n{py} {exe} --instance "{name}"\n')
    return bat

# ---------- loaders ----------
def _java():
    from . import core
    return core.java_bin_for("1.20")

def install_fabric(mc_version):
    inst = _fetch_json("https://meta.fabricmc.net/v2/versions/installer")[0]
    with tempfile.TemporaryDirectory() as td:
        ij = os.path.join(td, "fi.jar"); _download(inst["url"], ij)
        from . import core
        d = core.GAME_DIR
        r = subprocess.run([_java(), "-jar", ij, "client", "-dir", d,
                            "-mcversion", mc_version, "-nogui"], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("fabric install failed: " + r.stderr.decode(errors="replace")[:400])
    return _fetch_json(f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}")[0]["loader"]["version"]

def install_neoforge(mc_version, build=None):
    vers = _fetch_json("https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge")
    if build is None:
        import re
        ok = [v.replace(".", "", 2)[:2] for v in vers]  # crude filter below instead
        build = None
        want = {"1.21.1": "21.1", "1.21": "21.0", "1.20.6": "20.6", "1.20.5": "20.5",
                "1.20.4": "20.4", "1.20.3": "20.3", "1.20.2": "20.2", "1.20.1": "20.1",
                "1.20": "20", "1.19.5": "19.5", "1.19.4": "19.4"}
        pref = want.get(mc_version)
        cands = [v for v in vers if not v.endswith("-beta")]
        if pref:
            cands = sorted([v for v in cands if v.startswith(pref)],
                           key=lambda v: [int(x) for x in v.split(".") if x.isdigit()], reverse=True)
            if cands: build = cands[0]
        if build is None:
            raise RuntimeError(f"no NeoForge build found for {mc_version} (try Forge/Fabric)")
    with tempfile.TemporaryDirectory() as td:
        ij = os.path.join(td, "nf.jar")
        _download(f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{build}/"
                  f"neoforge-{build}-installer.jar", ij)
        from . import core
        r = subprocess.run([_java(), "-jar", ij, "--installClient"],
                            cwd=core.GAME_DIR, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("neoforge install failed: " + r.stderr.decode(errors="replace")[:400])
    return build

def install_loader(loader, mc_version, build=None):
    from . import core
    if loader == "forge":
        return core.install_forge(mc_version, build)            # returns full version id
    if loader == "fabric":  return install_fabric(mc_version)   # returns loader version
    if loader == "neoforge": return install_neoforge(mc_version, build)
    raise RuntimeError(f"unknown loader {loader}")

# ---------- Modrinth ----------
MODRINTH_API = "https://api.modrinth.com/v2"

def _modrinth_json(path, params=None):
    """Fetch JSON from Modrinth with proper URL encoding and useful errors."""
    url = MODRINTH_API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "User-Agent": "BlemmLauncher/1.3.0",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise RuntimeError(
            f"Modrinth API error (HTTP {e.code}): {body[:500]}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Modrinth API request failed: {e}") from e


def modrinth_search(query, mc_version, loader=None):
    """Search Modrinth for projects compatible with a Minecraft version."""
    # Modrinth facets are JSON arrays. Build the JSON first, then let
    # urlencode() correctly escape brackets, quotes, spaces, etc.
    facets = [[f"versions:{mc_version}"]]

    if loader:
        loader = loader.lower().strip()
        facets.append([f"categories:{loader}"])

    data = _modrinth_json("/search", {
        "limit": "12",
        "query": query or "",
        "facets": json.dumps(facets, separators=(",", ":")),
    })

    results = []
    for h in data.get("hits", []):
        results.append({
            "title": h.get("title", "Unknown"),
            "id": h.get("project_id", ""),
            "desc": (h.get("description") or "")[:80],
            "downs": h.get("downloads", 0),
            "author": h.get("author", "Unknown"),
            "icon": h.get("icon_url"),
        })

    return results


def modrinth_install(project_id, mc_version, loader=None):
    """Install the first compatible Modrinth file."""
    params = {
        "game_versions": json.dumps([mc_version], separators=(",", ":")),
    }

    if loader:
        params["loaders"] = json.dumps(
            [loader.lower().strip()],
            separators=(",", ":")
        )

    versions = _modrinth_json(
        f"/project/{urllib.parse.quote(project_id, safe='')}/version",
        params
    )

    if not versions:
        raise RuntimeError(
            f"No Modrinth version found for {project_id} on Minecraft "
            f"{mc_version}" + (f" with {loader}" if loader else "")
        )

    ver = versions[0]
    files = ver.get("files", [])

    if not files:
        raise RuntimeError(
            f"Modrinth version {ver.get('id', '?')} has no downloadable files"
        )

    # Prefer the file Modrinth marks as primary.
    f = next((x for x in files if x.get("primary")), files[0])

    url = f.get("url")
    filename = f.get("filename")

    if not url or not filename:
        raise RuntimeError("Modrinth returned an invalid file entry")

    from . import core
    dest = os.path.join(core.GAME_DIR, "mods", filename)
    _download(url, dest)
    return filename
