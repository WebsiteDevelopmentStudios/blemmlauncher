"""BlemmLauncher local Minecraft server manager."""
import json, os, shutil, subprocess, threading, urllib.request, urllib.parse, urllib.error, ssl, re
from . import instances, core, database

SERVERS_DIR = os.path.join(instances.LAUNCHERS_ROOT, "servers")
SERVER_TYPES = ("Vanilla", "Paper", "Fabric", "Forge", "NeoForge")
MAX_SERVERS = 2
PROCESSES, CALLBACKS = {}, {}

def safe_name(name):
    return bool(name) and name not in (".", "..") and not any(c in name for c in '<>:|?*"') and "/" not in name and "\\" not in name


def is_reserved_name(name):
    return str(name).strip().casefold() == "survival"

def root(name):
    if not safe_name(name): raise RuntimeError("Invalid server name.")
    return os.path.join(SERVERS_DIR, name)

def path(name, rel=""):
    base, p = os.path.abspath(root(name)), os.path.abspath(os.path.join(root(name), str(rel).replace("\\", "/")))
    if os.path.commonpath((base, p)) != base: raise RuntimeError("Path escapes the server directory.")
    return p

def _request(url, load_json=True, dest=None):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BlemmLauncher/1.3.0",
            "Accept": "application/json" if not dest else "*/*"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=180 if dest else 40) as r:
            if dest:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                tmp = dest + ".part"
                total = r.headers.get("Content-Length")
                try:
                    total = int(total) if total else None
                except (TypeError, ValueError):
                    total = None
                downloaded = 0
                last_report = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded - last_report >= 512 * 1024 or (total and downloaded >= total):
                            last_report = downloaded
                            if total:
                                core.report(
                                    "Downloading " + os.path.basename(dest) + " — "
                                    + "{:.1f}".format(downloaded / (1024 * 1024))
                                    + " / " + "{:.1f}".format(total / (1024 * 1024)) + " MB",
                                    downloaded, total
                                )
                            else:
                                core.report(
                                    "Downloading " + os.path.basename(dest) + " — "
                                    + "{:.1f}".format(downloaded / (1024 * 1024)) + " MB"
                                )
                if total and downloaded < total:
                    raise RuntimeError("download ended early.")
                os.replace(tmp, dest)
                return None
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP " + str(e.code) + " from " + urllib.parse.urlsplit(url).netloc + ": " + str(e.reason))
    except urllib.error.URLError as e:
        if "certificate" in str(e).lower():
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=180 if dest else 40, context=ctx) as r:
                if dest:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    tmp = dest + ".part"
                    total = r.headers.get("Content-Length")
                    try:
                        total = int(total) if total else None
                    except (TypeError, ValueError):
                        total = None
                    downloaded = 0
                    with open(tmp, "wb") as f:
                        while True:
                            chunk = r.read(256 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                core.report(
                                    "Downloading " + os.path.basename(dest) + " — "
                                    + "{:.1f}".format(downloaded / (1024 * 1024))
                                    + " / " + "{:.1f}".format(total / (1024 * 1024)) + " MB",
                                    downloaded, total
                                )
                    os.replace(tmp, dest)
                    return None
                return json.load(r)
        raise

def list_servers():
    os.makedirs(SERVERS_DIR, exist_ok=True)
    disk = [n for n in sorted(os.listdir(SERVERS_DIR))
            if os.path.isfile(os.path.join(SERVERS_DIR, n, "blemm-server.json"))]
    # Reconcile the database with disk so servers created by older versions
    # of BlemmLauncher are never lost.
    return database.reconcile("servers", disk)

def server_limit_reached():
    return len(list_servers()) >= MAX_SERVERS

def load(name):
    with open(os.path.join(root(name), "blemm-server.json"), encoding="utf-8") as f: return json.load(f)

def save(name, cfg):
    os.makedirs(root(name), exist_ok=True)
    with open(os.path.join(root(name), "blemm-server.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    database.register("servers", name)

def running(name):
    p = PROCESSES.get(name)
    return bool(p and p.poll() is None)

def start(name, callback=None):
    if running(name): return
    cfg = load(name)
    jar, ram, configured_java, launch = (
        cfg.get("jar", "server.jar"),
        str(cfg.get("ram", "4G")),
        cfg.get("java"),
        cfg.get("launch")
    )
    if not os.path.isfile(path(name, jar)):
        raise RuntimeError("Server JAR not found: " + jar)

    # "java" in older server configs means "use whatever Java is on PATH".
    # Resolve that through the managed Java system so an old/32-bit JVM cannot
    # be selected for a multi-GB server heap.
    if configured_java in (None, "", "java", "java.exe"):
        java = core.java_bin_for(str(cfg.get("version", "")))
    else:
        java = configured_java

    cmd = ([java, "-Xms" + ram, "-Xmx" + ram, "-jar", jar, "nogui"] if not launch else (["cmd", "/c", launch] if os.name == "nt" else ["sh", launch]))
    env = os.environ.copy()
    # Forge/NeoForge run scripts normally call "java" themselves. Put the
    # managed runtime on PATH and expose JAVA_HOME so those scripts use the
    # same Java that BlemmLauncher installed for this Minecraft version.
    java_abs = os.path.abspath(java) if os.path.isabs(str(java)) else shutil.which(str(java))
    if java_abs:
        java_bin_dir = os.path.dirname(java_abs)
        java_home = os.path.dirname(java_bin_dir)
        env["PATH"] = java_bin_dir + os.pathsep + env.get("PATH", "")
        env["JAVA_HOME"] = java_home
    p = subprocess.Popen(cmd, cwd=root(name), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
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

def _server_port(name):
    port = 25565
    try:
        p = path(name, "server.properties")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("server-port="):
                        value = line.split("=", 1)[1].strip()
                        if value.isdigit():
                            port = int(value)
                        break
    except Exception:
        pass
    return port


def _domain_slug(name):
    value = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    return value or "server"


def domain_info(name, suffix="blemm.devs.surf"):
    """Build a safe free-domain candidate from the server name.

    The harys722/free-domains repository is a directory of free-domain
    providers, not itself a DNS registration API. The returned hostname is a
    candidate that the user can register with the selected provider.
    """
    suffix = str(suffix or "").strip().lower().strip(".")
    if not suffix or not re.fullmatch(r"[a-z0-9.-]+", suffix):
        raise RuntimeError("Invalid domain suffix.")
    slug = _domain_slug(name)
    return {
        "slug": slug,
        "suffix": suffix,
        "domain": slug + "." + suffix,
        "status": "Candidate only — register this hostname with the provider before using it. DNS must point to your public server IP.",
    }


def network_info(name):
    """Return addresses useful for connecting to a local server."""
    import socket

    port = _server_port(name)
    local_ip = "127.0.0.1"
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:
        try:
            candidate = socket.gethostbyname(socket.gethostname())
            if not candidate.startswith("127."):
                local_ip = candidate
        except Exception:
            pass

    return {
        "local_ip": local_ip,
        "local_address": "127.0.0.1:" + str(port),
        "lan_address": local_ip + ":" + str(port),
        "port": port,
    }

def delete(name):
    if running(name): kill(name)
    shutil.rmtree(root(name), ignore_errors=True)
    database.unregister("servers", name)

def tree(name, rel=""):
    folder = path(name, rel)
    if not os.path.isdir(folder): raise RuntimeError("Directory not found.")
    return [{"name": n, "path": os.path.relpath(os.path.join(folder, n), root(name)).replace(os.sep, "/"), "dir": os.path.isdir(os.path.join(folder, n)), "size": os.path.getsize(os.path.join(folder, n)) if os.path.isfile(os.path.join(folder, n)) else 0} for n in sorted(os.listdir(folder), key=lambda x: (not os.path.isdir(os.path.join(folder, x)), x.lower()))]

def read_file(name, rel):
    p = path(name, rel)
    if not os.path.isfile(p): raise RuntimeError("File not found.")
    if os.path.getsize(p) > 50 * 1024 * 1024: raise RuntimeError("File is larger than the 50 MB editor limit.")
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

def _minecraft_versions(limit=80):
    data = _request("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, list):
        raise RuntimeError("Mojang returned an invalid version list.")
    return [x["id"] for x in versions if isinstance(x, dict) and x.get("type") == "release" and x.get("id")][:limit]


def _paper_versions(limit=80):
    # Paper's v2 API was retired. Use the current official Paper downloads
    # service (Fill API v3).
    data = _request("https://fill.papermc.io/v3/projects/paper/versions")
    versions = data.get("versions") if isinstance(data, dict) else data
    if not isinstance(versions, list):
        raise RuntimeError("Paper returned an invalid version list.")

    out = []
    for item in versions:
        if isinstance(item, dict):
            # Current Fill API: {"version": {"id": "1.x.x", ...}, ...}
            nested = item.get("version")
            value = nested.get("id") if isinstance(nested, dict) else item.get("id")
        else:
            value = item
        if value:
            out.append(str(value))

    return list(dict.fromkeys(out))[:limit]



def _forge_versions(limit=80):
    data = _request("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json")
    promos = data.get("promos") if isinstance(data, dict) else None
    if not isinstance(promos, dict):
        raise RuntimeError("Forge returned no version promotions.")
    out = []
    for key in promos:
        if str(key).endswith("-recommended"):
            out.append(str(key)[:-12])
    if not out:
        for key in promos:
            if str(key).endswith("-latest"):
                out.append(str(key)[:-7])
    return sorted(set(out), key=lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r"[.-]", v)], reverse=True)[:limit]


def _neoforge_versions(limit=80):
    data = _request("https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge")
    builds = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(builds, list):
        raise RuntimeError("NeoForge returned no versions.")
    families = []
    for b in builds:
        parts = str(b).split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            mc = "1." + parts[0] + "." + parts[1]
            if mc not in families:
                families.append(mc)
    return sorted(families, key=lambda v: [int(x) for x in v.split(".")], reverse=True)[:limit]

def versions(kind, limit=80):
    kind = str(kind).lower().strip()
    if kind in ("vanilla", "fabric"):
        return _minecraft_versions(limit)
    if kind == "paper":
        return _paper_versions(limit)
    if kind == "forge":
        return _forge_versions(limit)
    if kind == "neoforge":
        return _neoforge_versions(limit)
    return _minecraft_versions(limit)


def create(name, kind, version, ram="4G", java="java"):
    if not safe_name(name): raise RuntimeError("Invalid server name.")
    if not version: raise RuntimeError("Select a version.")
    d = root(name)
    existing = list_servers()
    if name not in existing and len(existing) >= MAX_SERVERS:
        raise RuntimeError("You can only have " + str(MAX_SERVERS) + " servers. Delete an existing server before creating another.")
    if os.path.exists(d) and os.listdir(d): raise RuntimeError("That server already exists and contains files.")
    os.makedirs(d, exist_ok=True)
    kind, version = str(kind).lower(), str(version)
    
    if kind == "vanilla":
        entry = next((x for x in _request("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")["versions"] if x["id"] == version), None)
        if not entry: raise RuntimeError("Minecraft version not found.")
        url = _request(entry["url"]).get("downloads", {}).get("server", {}).get("url")
        if not url: raise RuntimeError("No official server JAR exists for this version.")
        _request(url, dest=os.path.join(d, "server.jar"))
    elif kind == "paper":
        # Remapped deployment rules using standard v3 structures smoothly
        v_url = "https://papermc.io/versions/" + urllib.parse.quote(version)
        data = _request(v_url)
        builds = data.get("builds", [])
        if not builds: raise RuntimeError("No Paper build found for " + version)
        build = builds[-1]
        url = v_url + "/builds/" + str(build) + "/downloads/paper-" + version + "-" + str(build) + ".jar"
        _request(url, dest=os.path.join(d, "server.jar"))
    elif kind in ("fabric", "forge", "neoforge"):
        installer = os.path.join(d, kind + "-installer.jar")
        if kind == "fabric":
            _request(_request("https://fabricmc.net")[0]["url"], dest=installer)
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
    cfg = {
        "name": name,
        "type": kind.title(),
        "version": version,
        "ram": ram,
        "java": java,
        "jar": jar,
        "launch": launch,
        "domain_suffix": "blemm.devs.surf",
    }
    save(name, cfg)
    return cfg
def _server_java(version):
    return core.java_bin_for(str(version))


def _run_installer(java, installer, args, cwd, timeout):
    r = subprocess.run(
        [java, "-jar", installer] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    output = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    if r.returncode != 0:
        raise RuntimeError(
            "Installer failed (exit code " + str(r.returncode) + "):\n"
            + output[-4000:]
        )
    return output


def _fabric_server(d, version, java):
    installers = _request("https://meta.fabricmc.net/v2/versions/installer")
    if not installers:
        raise RuntimeError("Fabric returned no installer versions.")
    installer_path = os.path.join(d, "fabric-installer.jar")
    _request(installers[0]["url"], dest=installer_path)
    try:
        _run_installer(java, installer_path, ["server", "-mcversion", str(version), "-downloadMinecraft"], d, 1800)
    finally:
        if os.path.exists(installer_path):
            os.remove(installer_path)


def _forge_server(d, version, java):
    promos = _request("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json").get("promos", {})
    build = promos.get(str(version) + "-recommended") or promos.get(str(version) + "-latest")
    if not build:
        raise RuntimeError("No Forge build found for Minecraft " + str(version))
    full = str(version) + "-" + str(build)
    installer_path = os.path.join(d, "forge-installer.jar")
    url = "https://maven.minecraftforge.net/net/minecraftforge/forge/" + full + "/forge-" + full + "-installer.jar"
    _request(url, dest=installer_path)
    try:
        _run_installer(java, installer_path, ["--installServer"], d, 1800)
    finally:
        if os.path.exists(installer_path):
            os.remove(installer_path)


def _neoforge_server(d, version, java):
    data = _request("https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge")
    builds = [str(x) for x in data.get("versions", [])]
    parts = str(version).split(".")
    if len(parts) < 2:
        raise RuntimeError("Invalid Minecraft version: " + str(version))
    prefix = parts[1] + "." + (parts[2] if len(parts) > 2 else "0")
    cands = [b for b in builds if b.startswith(prefix + ".") and "beta" not in b.lower()]
    if not cands:
        raise RuntimeError("No NeoForge build found for Minecraft " + str(version))
    def key(v):
        return [int(x) for x in v.split(".") if x.isdigit()]
    build = sorted(cands, key=key, reverse=True)[0]
    installer_path = os.path.join(d, "neoforge-installer.jar")
    url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/" + build + "/neoforge-" + build + "-installer.jar"
    _request(url, dest=installer_path)
    try:
        _run_installer(java, installer_path, ["--installServer"], d, 1800)
    finally:
        if os.path.exists(installer_path):
            os.remove(installer_path)


def create(name, kind, version, ram="4G", java=None):
    if is_reserved_name(name):
        raise RuntimeError("That server name is used by the devs.")
    if not safe_name(name):
        raise RuntimeError("Invalid server name.")
    if not version:
        raise RuntimeError("Select a version.")
    d = root(name)
    existing = list_servers()
    if name not in existing and len(existing) >= MAX_SERVERS:
        raise RuntimeError("You can only have " + str(MAX_SERVERS) + " servers. Delete an existing server before creating another.")
    if os.path.exists(d) and os.listdir(d):
        raise RuntimeError("That server already exists and contains files.")
    os.makedirs(d, exist_ok=True)
    kind, version = str(kind).lower(), str(version)
    java = java or _server_java(version)

    if kind == "vanilla":
        entry = next(
            (x for x in _request("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json").get("versions", [])
             if x["id"] == version), None
        )
        if not entry:
            raise RuntimeError("Minecraft version not found.")
        info = _request(entry["url"])
        url = info.get("downloads", {}).get("server", {}).get("url")
        if not url:
            raise RuntimeError("No official server JAR exists for this version.")
        _request(url, dest=os.path.join(d, "server.jar"))

    elif kind == "paper":
        # Ask Fill for the latest stable build and use the download URL it
        # provides. This avoids depending on Paper's retired v2 API and also
        # avoids guessing JAR filenames.
        url = (
            "https://fill.papermc.io/v3/projects/paper/versions/"
            + urllib.parse.quote(version, safe="")
            + "/builds/latest"
        )
        data = _request(url)
        download = data.get("downloads", {}).get("server:default", {}) if isinstance(data, dict) else {}
        download_url = download.get("url")
        if not download_url:
            raise RuntimeError("No stable Paper build is available for " + version)
        _request(download_url, dest=os.path.join(d, "server.jar"))

    elif kind == "fabric":
        _fabric_server(d, version, java)

    elif kind == "forge":
        _forge_server(d, version, java)

    elif kind == "neoforge":
        _neoforge_server(d, version, java)

    else:
        raise RuntimeError("Unsupported server type: " + kind)

    jar = "server.jar" if os.path.isfile(os.path.join(d, "server.jar")) else "fabric-server-launch.jar"
    launch = "run.bat" if os.path.isfile(os.path.join(d, "run.bat")) else ("run.sh" if os.path.isfile(os.path.join(d, "run.sh")) else None)
    if kind in ("forge", "neoforge") and not launch:
        raise RuntimeError(kind.title() + " installer did not create a run script.")

    cfg = {"name": name, "type": kind.title(), "version": version, "ram": ram, "java": java, "jar": jar, "launch": launch}
    save(name, cfg)
    return cfg
