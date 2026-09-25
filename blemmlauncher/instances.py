"""BlemmLauncher instances - isolated setups, loaders, Modrinth, export/import."""

import glob
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import zipfile
import urllib.error
import urllib.parse
import urllib.request


LAUNCHERS_ROOT = os.environ.get(
    "BLEMM_DIR",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "minecraft"
    )
)

INSTANCES_DIR = os.path.join(LAUNCHERS_ROOT, "instances")
SHARED_ASSETS = os.path.join(LAUNCHERS_ROOT, "assets")
SHARED_TOOLS = os.path.join(LAUNCHERS_ROOT, "tools")

MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "BlemmLauncher/1.3.0"


def _fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.URLError as e:
        txt = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in txt or "certificate" in txt.lower():
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                return json.load(r)
        raise


def _download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        return

    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    except urllib.error.URLError as e:
        txt = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in txt or "certificate" in txt.lower():
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
        else:
            raise
    os.replace(tmp, dest)


def isafe(name):
    bad = '<>:"/\\|?*'
    return bool(name) and not any(c in bad for c in name) and name not in (".", "..")


def instance_dir(name):
    return os.path.join(INSTANCES_DIR, name)


def list_instances():
    if not os.path.isdir(INSTANCES_DIR):
        return []
    return [
        n for n in sorted(os.listdir(INSTANCES_DIR))
        if os.path.exists(os.path.join(INSTANCES_DIR, n, "blemm.json"))
    ]


def load_cfg(name):
    with open(os.path.join(instance_dir(name), "blemm.json"), encoding="utf-8") as f:
        return json.load(f)


def save_cfg(name, cfg):
    os.makedirs(instance_dir(name), exist_ok=True)
    with open(os.path.join(instance_dir(name), "blemm.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def create(name, version, loader=None, ram="4G", username="Blemm", build=None):
    if not isafe(name):
        raise RuntimeError("bad instance name '" + str(name) + "'")
    if name in list_instances():
        raise RuntimeError("instance '" + name + "' already exists")

    os.makedirs(instance_dir(name), exist_ok=True)
    for sub in ("mods", "resourcepacks", "shaderpacks", "saves"):
        os.makedirs(os.path.join(instance_dir(name), sub), exist_ok=True)

    cfg = {
        "name": name,
        "version": version,
        "loader": loader,
        "loader_build": build,
        "ram": ram,
        "username": username,
        "optifine": False
    }
    save_cfg(name, cfg)
    return cfg


def delete(name):
    d = instance_dir(name)
    if os.path.isdir(d):
        shutil.rmtree(d)


def use(name, core):
    d = instance_dir(name)
    core.set_game_dir(d, assets_dir=SHARED_ASSETS, tools_dir=SHARED_TOOLS)
    return d


# Keep the existing client import implementation from the repository.
# This section is intentionally compatible with the current GUI/API.
def _sanitize_version_id(name):
    cleaned = re.sub(r'[<>:"/\\|?*\s]', "_", str(name)).strip("._ ")
    return cleaned or "CustomClient"


def _unique_instance_name(base):
    base = base or "Client"
    name = base
    i = 1
    while name in list_instances():
        i += 1
        name = base + " (" + str(i) + ")"
    return name


def inspect_client_file(path):
    from . import core
    p = str(path).lower()

    if p.endswith(".json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if isinstance(data, dict) and (
            "inheritsFrom" in data or "mainClass" in data or "id" in data
        ):
            return "version_json"
        return None

    if p.endswith(".jar"):
        if core.looks_like_optifine(path) or core.detect_kind(path) == "mod":
            return "mod"
        return "client_jar"

    return None


def _ensure_instance(name, version, loader, ram, username):
    if not isafe(name):
        raise RuntimeError("bad instance name '" + str(name) + "'")
    d = instance_dir(name)
    os.makedirs(d, exist_ok=True)
    for sub in ("mods", "resourcepacks", "shaderpacks", "saves"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)

    cfgp = os.path.join(d, "blemm.json")
    if os.path.exists(cfgp):
        with open(cfgp, encoding="utf-8") as f:
            return json.load(f)

    cfg = {
        "name": name,
        "version": version,
        "loader": loader,
        "loader_build": None,
        "ram": ram,
        "username": username,
        "optifine": False
    }
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def import_client(path, instance_name=None, mc_version=None,
                  loader=None, ram="4G", username="Blemm"):
    from . import core
    src = os.path.abspath(path)
    if not os.path.isfile(src):
        raise RuntimeError("file not found: " + src)

    base = os.path.splitext(os.path.basename(src))[0]
    kind = inspect_client_file(src)
    if kind is None:
        raise RuntimeError("unsupported file - use a .jar or Minecraft version .json")

    def _resolve(mc):
        if not mc:
            raise RuntimeError("a Minecraft version is required")
        return core.resolve_version(mc, core.manifest())

    if kind == "version_json":
        with open(src, encoding="utf-8") as f:
            vj = json.load(f)
        vid = _sanitize_version_id(vj.get("id") or base)
        name = instance_name or _unique_instance_name(base)
        cfg = _ensure_instance(name, vid, None, ram, username)
        d = instance_dir(name)
        vdest = os.path.join(d, "versions", vid)
        os.makedirs(vdest, exist_ok=True)
        shutil.copy2(src, os.path.join(vdest, vid + ".json"))

        srcdir = os.path.dirname(src)
        jar = None
        for cand in (vid + ".jar", base + ".jar"):
            jp = os.path.join(srcdir, cand)
            if os.path.isfile(jp):
                jar = jp
                break
        if jar:
            shutil.copy2(jar, os.path.join(vdest, vid + ".jar"))

        cfg["version"] = vid
        cfg["loader"] = None
        save_cfg(name, cfg)
        return name, "custom version '" + vid + "' imported" + (
            " (client jar included)" if jar else ""
        )

    if kind == "mod":
        if instance_name:
            name = instance_name
            cfg = _ensure_instance(name, None, None, ram, username)
        else:
            mv = _resolve(mc_version)
            name = _unique_instance_name(base)
            cfg = _ensure_instance(name, mv, loader, ram, username)

        d = instance_dir(name)
        core.set_game_dir(d, assets_dir=SHARED_ASSETS, tools_dir=SHARED_TOOLS)
        mods_dir = os.path.join(d, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        shutil.copy2(src, os.path.join(mods_dir, os.path.basename(src)))
        if core.looks_like_optifine(src):
            cfg["optifine"] = True
        save_cfg(name, cfg)
        return name, "installed into mods/: " + os.path.basename(src)

    mv = _resolve(mc_version)
    vid = _sanitize_version_id(base)
    name = instance_name or _unique_instance_name(base)
    cfg = _ensure_instance(name, vid, None, ram, username)
    d = instance_dir(name)
    vdest = os.path.join(d, "versions", vid)
    os.makedirs(vdest, exist_ok=True)
    shutil.copy2(src, os.path.join(vdest, vid + ".jar"))

    vjson = {
        "id": vid,
        "inheritsFrom": mv,
        "type": "release",
        "releaseTime": "2024-01-01T00:00:00+00:00",
        "time": "2024-01-01T00:00:00+00:00"
    }
    with open(os.path.join(vdest, vid + ".json"), "w", encoding="utf-8") as f:
        json.dump(vjson, f, indent=2)
    cfg["version"] = vid
    cfg["loader"] = None
    save_cfg(name, cfg)
    return name, "custom client '" + vid + "' imported (based on Minecraft " + mv + ")"


def _java(mc_version):
    from . import core
    return core.java_bin_for(mc_version)


def _version_installed(core, vid):
    p = os.path.join(core.GAME_DIR, "versions", vid, vid + ".json")
    return os.path.exists(p)


def install_fabric(mc_version):
    from . import core

    existing = glob.glob(
        os.path.join(core.GAME_DIR, "versions", "fabric-loader-*-" + mc_version)
    )
    for p in sorted(existing, reverse=True):
        vid = os.path.basename(p)
        if os.path.exists(os.path.join(p, vid + ".json")):
            return vid

    installers = _fetch_json("https://meta.fabricmc.net/v2/versions/installer")
    if not installers:
        raise RuntimeError("Fabric returned no installers")
    inst = installers[0]

    loaders = _fetch_json(
        "https://meta.fabricmc.net/v2/versions/loader/" + urllib.parse.quote(mc_version, safe="")
    )
    if not loaders:
        raise RuntimeError("no Fabric loader found for Minecraft " + mc_version)
    loader_ver = loaders[0]["loader"]["version"]

    core.ensure_launcher_profile(core.GAME_DIR)

    with tempfile.TemporaryDirectory() as td:
        ij = os.path.join(td, "fabric-installer.jar")
        _download(inst["url"], ij)

        r = subprocess.run(
            [
                _java(mc_version), "-jar", ij, "client",
                "-dir", core.GAME_DIR,
                "-mcversion", mc_version,
                "-loader", loader_ver,
                "-nogui"
            ],
            capture_output=True,
            timeout=900
        )
        outp = ((r.stderr or b"") + (r.stdout or b"")).decode(errors="replace")

        if r.returncode != 0:
            raise RuntimeError(
                "Fabric install failed (exit code "
                + str(r.returncode) + "):\n" + outp[-1200:]
            )

    vid = "fabric-loader-" + loader_ver + "-" + mc_version
    if not _version_installed(core, vid):
        raise RuntimeError(
            "Fabric installer finished, but the expected version '" + vid
            + "' was not created.\nInstaller output:\n" + outp[-1200:]
        )
    return vid


def _neoforge_series(mc_version):
    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?$", str(mc_version))
    if not m:
        return None
    return m.group(2) + "." + (m.group(3) or "0")


def install_neoforge(mc_version, build=None):
    from . import core

    if build and _version_installed(core, "neoforge-" + str(build)):
        return "neoforge-" + str(build)

    vers = _fetch_json(
        "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
    )

    if build is None:
        series = _neoforge_series(mc_version)
        if series is None:
            raise RuntimeError("can't map Minecraft '" + mc_version + "' to a NeoForge version")

        def key(v):
            return [int(x) for x in v.split(".") if x.isdigit()]

        cands = sorted(
            [
                v for v in vers
                if v.startswith(series + ".") and "beta" not in v.lower()
            ],
            key=key, reverse=True
        )
        if not cands:
            raise RuntimeError(
                "no NeoForge build found for Minecraft " + mc_version
                + " (series " + series + ")"
            )
        build = cands[0]

    if _version_installed(core, "neoforge-" + str(build)):
        return "neoforge-" + str(build)

    with tempfile.TemporaryDirectory() as td:
        ij = os.path.join(td, "neoforge-installer.jar")
        url = (
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/"
            + str(build) + "/neoforge-" + str(build) + "-installer.jar"
        )
        _download(url, ij)

        r = subprocess.run(
            [_java(mc_version), "-jar", ij, "--installClient"],
            cwd=core.GAME_DIR,
            capture_output=True,
            timeout=1800
        )
        outp = ((r.stderr or b"") + (r.stdout or b"")).decode(errors="replace")
        if r.returncode != 0:
            raise RuntimeError(
                "NeoForge install failed (exit code "
                + str(r.returncode) + "):\n" + outp[-1200:]
            )

    vid = "neoforge-" + str(build)
    if not _version_installed(core, vid):
        raise RuntimeError(
            "NeoForge installer finished but version '" + vid + "' was not created.\n"
            + outp[-1200:]
        )
    return vid


def install_loader(loader, mc_version, build=None):
    from . import core
    loader = str(loader).lower().strip()
    if loader == "forge":
        return core.install_forge(mc_version, build)
    if loader == "fabric":
        return install_fabric(mc_version)
    if loader == "neoforge":
        return install_neoforge(mc_version, build)
    raise RuntimeError("unknown loader " + str(loader))


def _modrinth_json(path, params=None):
    url = MODRINTH_API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise RuntimeError(
            "Modrinth API error (HTTP " + str(e.code) + "): " + body[:500]
        ) from e
    except urllib.error.URLError as e:
        txt = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in txt or "certificate" in txt.lower():
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                return json.load(r)
        raise RuntimeError("Modrinth API request failed: " + str(e)) from e


def _modrinth_project_type(ptype):
    return {"mod": "mod", "shader": "shader", "resourcepack": "resourcepack"}.get(
        ptype, "mod"
    )


def modrinth_search(query, mc_version, loader=None, project_type="mod"):
    pt = _modrinth_project_type(project_type)
    facets = [["project_type:" + pt], ["versions:" + str(mc_version)]]
    if pt == "mod" and loader:
        facets.append(["categories:" + str(loader).lower().strip()])

    data = _modrinth_json("/search", {
        "limit": "12",
        "query": query or "",
        "facets": json.dumps(facets, separators=(",", ":"))
    })

    return [
        {
            "title": h.get("title", "Unknown"),
            "id": h.get("project_id", ""),
            "desc": (h.get("description") or "")[:160],
            "downs": h.get("downloads", 0),
            "author": h.get("author", "Unknown"),
            "icon": h.get("icon_url"),
        }
        for h in data.get("hits", [])
    ]


def modrinth_install(project_id, mc_version, loader=None, project_type="mod"):
    from . import core
    pt = _modrinth_project_type(project_type)

    params = {
        "game_versions": json.dumps([str(mc_version)], separators=(",", ":"))
    }
    if pt == "mod" and loader:
        params["loaders"] = json.dumps(
            [str(loader).lower().strip()], separators=(",", ":")
        )

    versions = _modrinth_json(
        "/project/" + urllib.parse.quote(project_id, safe="") + "/version",
        params
    )
    if not versions:
        raise RuntimeError(
            "No Modrinth version found for this project on Minecraft "
            + str(mc_version) + ((" with " + str(loader)) if loader else "")
        )

    files = versions[0].get("files", [])
    if not files:
        raise RuntimeError("Modrinth version has no downloadable files")

    f = next((x for x in files if x.get("primary")), files[0])
    url = f.get("url")
    filename = f.get("filename")
    if not url or not filename:
        raise RuntimeError("Modrinth returned an invalid file entry")

    folder = (
        "shaderpacks" if pt == "shader"
        else "resourcepacks" if pt == "resourcepack"
        else "mods"
    )
    dest = os.path.join(core.GAME_DIR, folder, filename)
    _download(url, dest)

    if pt == "resourcepack":
        try:
            core.enable_resourcepack(filename)
        except Exception as e:
            raise RuntimeError(
                "Resource pack downloaded, but it could not be enabled automatically: "
                + str(e)
            ) from e
    return filename
