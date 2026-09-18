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


# ============================================================
# SMALL HELPERS
# ============================================================

def _fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.URLError as e:
        txt = str(e)

        if "CERTIFICATE_VERIFY_FAILED" in txt or "certificate" in txt.lower():
            ctx = ssl._create_unverified_context()

            with urllib.request.urlopen(
                req, timeout=25, context=ctx
            ) as r:
                return json.load(r)

        raise


def _download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    if os.path.exists(dest):
        return

    tmp = dest + ".part"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    except urllib.error.URLError as e:
        txt = str(e)

        if "CERTIFICATE_VERIFY_FAILED" in txt or "certificate" in txt.lower():
            ctx = ssl._create_unverified_context()

            with urllib.request.urlopen(
                req, timeout=60, context=ctx
            ) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
        else:
            raise

    os.replace(tmp, dest)


# ============================================================
# INSTANCE BASICS
# ============================================================

def isafe(name):
    bad = '<>:"/\\|?*'
    return bool(name) and not any(c in bad for c in name) and name not in (".", "..")


def instance_dir(name):
    return os.path.join(INSTANCES_DIR, name)


def list_instances():
    if not os.path.isdir(INSTANCES_DIR):
        return []

    out = []

    for n in sorted(os.listdir(INSTANCES_DIR)):
        if os.path.exists(
            os.path.join(INSTANCES_DIR, n, "blemm.json")
        ):
            out.append(n)

    return out


def load_cfg(name):
    with open(
        os.path.join(instance_dir(name), "blemm.json"),
        encoding="utf-8"
    ) as f:
        return json.load(f)


def save_cfg(name, cfg):
    os.makedirs(instance_dir(name), exist_ok=True)

    with open(
        os.path.join(instance_dir(name), "blemm.json"),
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(cfg, f, indent=2)


def create(name, version, loader=None, ram="4G", username="Blemm", build=None):
    """loader: None | 'forge' | 'fabric' | 'neoforge'."""

    if not isafe(name):
        raise RuntimeError("bad instance name '" + str(name) + "'")

    if name in list_instances():
        raise RuntimeError("instance '" + name + "' already exists")

    os.makedirs(instance_dir(name), exist_ok=True)

    for sub in ("mods", "resourcepacks", "shaderpacks", "saves"):
        os.makedirs(
            os.path.join(instance_dir(name), sub),
            exist_ok=True
        )

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
    """Point core at this instance. Mods, libraries, version JSONs
    and natives are per-instance; assets and Java runtimes are shared
    globally so they aren't re-downloaded per instance.
    """

    d = instance_dir(name)

    core.set_game_dir(
        d,
        assets_dir=SHARED_ASSETS,
        tools_dir=SHARED_TOOLS
    )

    return d


# ============================================================
# IMPORT CLIENT / MOD / CUSTOM VERSION
# ============================================================

def _sanitize_version_id(name):
    """Turn an arbitrary file name into a valid version id."""

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


def _ensure_instance(name, version, loader, ram, username):
    """Load an existing instance's cfg, or create it on the fly."""

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


def inspect_client_file(path):
    """Classify a file the user wants to import.

    Returns:
      'version_json' - a Minecraft version JSON (custom client folder,
                       TLauncher-style clients, OptiFine standalone)
      'mod'          - a loader mod JAR (most hack clients: Meteor,
                       Wurst, LiquidBounce...) or an OptiFine JAR
      'client_jar'   - a bare custom client JAR that replaces the
                       vanilla client.jar entirely
      None           - unrecognizable
    """

    from . import core

    p = str(path).lower()

    if p.endswith(".json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

        if isinstance(data, dict) and (
            "inheritsFrom" in data
            or "mainClass" in data
            or "id" in data
        ):
            return "version_json"

        return None

    if p.endswith(".jar"):
        if core.looks_like_optifine(path):
            return "mod"

        if core.detect_kind(path) == "mod":
            return "mod"

        return "client_jar"

    return None


def import_client(path, instance_name=None, mc_version=None,
                 loader=None, ram="4G", username="Blemm"):
    """Import a hack client / custom client / mod into an instance.

    instance_name: an EXISTING instance to import into; when None a
    new instance is created (named after the file, with a unique
    suffix if the name is taken).

    mc_version: the Minecraft version to base things on ('release'
    works too - resolved through the Mojang manifest).

    loader: for mod JARs going into a NEW instance (forge/fabric/
    neoforge, or None for vanilla).

    Returns (instance_name, description_of_what_happened).
    """

    from . import core

    src = os.path.abspath(path)

    if not os.path.isfile(src):
        raise RuntimeError("file not found: " + src)

    base = os.path.splitext(os.path.basename(src))[0]

    kind = inspect_client_file(src)

    if kind is None:
        raise RuntimeError(
            "unsupported file - use a .jar or a Minecraft version .json"
        )

    def _resolve(mc):
        if not mc:
            raise RuntimeError(
                "a Minecraft version is required - pick one in the "
                "import dialog"
            )

        return core.resolve_version(mc, core.manifest())

    # ---------- 1) version JSON from a versions/ folder ----------
    # (TLauncher-style custom clients, OptiFine standalone versions...)

    if kind == "version_json":
        with open(src, encoding="utf-8") as f:
            vj = json.load(f)

        vid = _sanitize_version_id(vj.get("id") or base)

        if instance_name:
            name = instance_name
        else:
            name = _unique_instance_name(base)

        cfg = _ensure_instance(name, vid, None, ram, username)

        d = instance_dir(name)
        vdest = os.path.join(d, "versions", vid)

        os.makedirs(vdest, exist_ok=True)

        # JSON (under the sanitized id so load_version_json finds it)
        shutil.copy2(src, os.path.join(vdest, vid + ".json"))

        # The matching client jar, if the user selected the json from
        # an existing versions/<x>/ folder.
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

        msg = "custom version '" + vid + "' imported"
        msg += " (client jar included)" if jar else ""

        return name, msg

    # ---------- 2) mod JAR (hack clients that are mods) ----------

    if kind == "mod":
        if instance_name:
            name = instance_name
            cfg = _ensure_instance(name, None, None, ram, username)
        else:
            mv = _resolve(mc_version)
            name = _unique_instance_name(base)
            cfg = _ensure_instance(name, mv, loader, ram, username)

        d = instance_dir(name)

        core.set_game_dir(
            d,
            assets_dir=SHARED_ASSETS,
            tools_dir=SHARED_TOOLS
        )

        mods_dir = os.path.join(d, "mods")

        os.makedirs(mods_dir, exist_ok=True)

        shutil.copy2(src, os.path.join(mods_dir, os.path.basename(src)))

        mod_name = os.path.basename(src)

        if core.looks_like_optifine(src):
            cfg["optifine"] = True

        save_cfg(name, cfg)

        return name, "installed into mods/: " + mod_name

    # ---------- 3) bare custom client JAR (hacked client) -------
    # A jar that REPLACES the vanilla client.jar. We wrap it in an
    # OptiFine-style version folder: versions/<id>/<id>.jar plus a
    # JSON inheriting from the vanilla version, so everything (java,
    # libraries, assets, mainClass) resolves automatically.

    mv = _resolve(mc_version)
    vid = _sanitize_version_id(base)

    if instance_name:
        name = instance_name
    else:
        name = _unique_instance_name(base)

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
        "time": "2024-01-01T00:00:00+00:00",
    }

    with open(os.path.join(vdest, vid + ".json"), "w", encoding="utf-8") as f:
        json.dump(vjson, f, indent=2)

    cfg["version"] = vid
    cfg["loader"] = None

    save_cfg(name, cfg)

    return (
        name,
        "custom client '" + vid + "' imported (based on Minecraft " + mv + ")"
    )


# ============================================================
# EXPORT / IMPORT (whole instances)
# ============================================================

def export(name, dest_zip):
    d = instance_dir(name)

    if not os.path.isdir(d):
        raise RuntimeError("no instance '" + str(name) + "'")

    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(d):
            if (
                os.sep + "libraries" in root
                or os.sep + "natives" in root
                or os.sep + "log-configs" in root
            ):
                continue

            for f in files:
                if f.endswith(".part") or f.endswith(".disabled"):
                    continue

                p = os.path.join(root, f)
                z.write(
                    p,
                    os.path.join(name, os.path.relpath(p, d))
                )


def import_from_zip(src_zip):
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(src_zip) as z:
            z.extractall(td)

        for n in os.listdir(td):
            if os.path.exists(
                os.path.join(td, n, "blemm.json")
            ):
                if not isafe(n):
                    raise RuntimeError(
                        "bad instance name in zip: '" + str(n) + "'"
                    )

                if os.path.exists(instance_dir(n)):
                    i = 1

                    while os.path.exists(instance_dir(n + " (" + str(i) + ")")):
                        i += 1

                    n = n + " (" + str(i) + ")"

                shutil.move(
                    os.path.join(td, n),
                    instance_dir(n)
                )

                return n

    raise RuntimeError("zip had no instance (missing blemm.json)")


# ============================================================
# DESKTOP SHORTCUT
# ============================================================

def shortcut(name):
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")

    bat = os.path.join(desktop, "Blemm - " + name + ".bat")

    if getattr(sys, "frozen", False):
        cmd = '"' + sys.executable + '" --instance "' + name + '"'
    else:
        base = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        runpy = os.path.join(base, "run.py")

        cmd = 'python "' + runpy + '" --instance "' + name + '"'

    with open(bat, "w", encoding="utf-8") as f:
        f.write("@echo off\n" + cmd + "\n")

    return bat


# ============================================================
# LOADERS
# ============================================================

def _java(mc_version):
    from . import core
    return core.java_bin_for(mc_version)


def _version_installed(core, vid):
    p = os.path.join(
        core.GAME_DIR,
        "versions",
        vid,
        vid + ".json"
    )
    return os.path.exists(p)


def install_fabric(mc_version):
    """Install Fabric for this instance. RETURNS the installed version
    id (like 'fabric-loader-0.16.x-1.21.1').
    """

    from . import core

    existing = glob.glob(
        os.path.join(
            core.GAME_DIR,
            "versions",
            "fabric-loader-*-" + mc_version
        )
    )

    for p in sorted(existing, reverse=True):
        vid = os.path.basename(p)

        if os.path.exists(
            os.path.join(p, vid + ".json")
        ):
            return vid

    try:
        installers = _fetch_json(
            "https://meta.fabricmc.net/v2/versions/installer"
        )
    except Exception as e:
        raise RuntimeError(
            "couldn't fetch the Fabric installer list: " + str(e)
        ) from e

    if not installers:
        raise RuntimeError("Fabric returned no installers")

    inst = installers[0]

    try:
        loaders = _fetch_json(
            "https://meta.fabricmc.net/v2/versions/loader/" + mc_version
        )
    except Exception as e:
        raise RuntimeError(
            "Fabric doesn't seem to support Minecraft "
            + mc_version + ": " + str(e)
        ) from e

    if not loaders:
        raise RuntimeError(
            "no Fabric loader found for Minecraft " + mc_version
        )

    loader_ver = loaders[0]["loader"]["version"]

    with tempfile.TemporaryDirectory() as td:
        ij = os.path.join(td, "fabric-installer.jar")
        _download(inst["url"], ij)

        r = subprocess.run(
            [
                _java(mc_version),
                "-jar", ij,
                "client",
                "-dir", core.GAME_DIR,
                "-mcversion", mc_version,
                "-loader", loader_ver,
                "-nogui"
            ],
            capture_output=True,
            timeout=900
        )

        if r.returncode != 0:
            outp = ((r.stderr or b"") + (r.stdout or b"")).decode(
                errors="replace"
            )

            raise RuntimeError(
                "Fabric install failed (exit code "
                + str(r.returncode) + "): " + outp[-600:]
            )

    vid = "fabric-loader-" + loader_ver + "-" + mc_version

    if not _version_installed(core, vid):
        raise RuntimeError(
            "Fabric installer finished but version '" + vid
            + "' was not created - the installer output was unclear."
        )

    return vid


def _neoforge_series(mc_version):
    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?$", str(mc_version))

    if not m:
        return None

    minor = m.group(2)
    patch = m.group(3) or "0"

    return minor + "." + patch


def install_neoforge(mc_version, build=None):
    """Install NeoForge for this instance. RETURNS the installed
    version id (like 'neoforge-21.1.95').
    """

    from . import core

    if build and _version_installed(core, "neoforge-" + str(build)):
        return "neoforge-" + str(build)

    try:
        vers = _fetch_json(
            "https://maven.neoforged.net/api/maven/versions/releases/"
            "net/neoforged/neoforge"
        )
    except Exception as e:
        raise RuntimeError(
            "couldn't fetch the NeoForge version list: " + str(e)
        ) from e

    if build is None:
        series = _neoforge_series(mc_version)

        if series is None:
            raise RuntimeError(
                "can't map Minecraft '" + str(mc_version)
                + "' to a NeoForge version."
            )

        def key(v):
            return [int(x) for x in v.split(".") if x.isdigit()]

        cands = [
            v for v in vers
            if v.startswith(series + ".")
            and "beta" not in v.lower()
        ]

        cands = sorted(cands, key=key, reverse=True)

        if not cands:
            raise RuntimeError(
                "no NeoForge build found for Minecraft " + mc_version
                + " (series " + series + "). "
                "Use Forge or Fabric for this version instead."
            )

        build = cands[0]

    if _version_installed(core, "neoforge-" + str(build)):
        return "neoforge-" + str(build)

    with tempfile.TemporaryDirectory() as td:
        ij = os.path.join(td, "neoforge-installer.jar")

        try:
            _download(
                "https://maven.neoforged.net/releases/"
                "net/neoforged/neoforge/" + str(build) + "/"
                "neoforge-" + str(build) + "-installer.jar",
                ij
            )
        except Exception as e:
            raise RuntimeError(
                "couldn't download the NeoForge "
                + str(build) + " installer: " + str(e)
            ) from e

        r = subprocess.run(
            [
                _java(mc_version),
                "-jar", ij,
                "--installClient"
            ],
            cwd=core.GAME_DIR,
            capture_output=True,
            timeout=1800
        )

        if r.returncode != 0:
            outp = ((r.stderr or b"") + (r.stdout or b"")).decode(
                errors="replace"
            )

            raise RuntimeError(
                "NeoForge install failed (exit code "
                + str(r.returncode) + "): " + outp[-600:]
            )

    vid = "neoforge-" + str(build)

    if not _version_installed(core, vid):
        raise RuntimeError(
            "NeoForge installer finished but version '" + vid
            + "' was not created."
        )

    return vid


def install_loader(loader, mc_version, build=None):
    from . import core

    if loader == "forge":
        return core.install_forge(mc_version, build)

    if loader == "fabric":
        return install_fabric(mc_version)

    if loader == "neoforge":
        return install_neoforge(mc_version, build)

    raise RuntimeError("unknown loader " + str(loader))


# ============================================================
# MODRINTH
# ============================================================

def _modrinth_json(path, params=None):
    url = MODRINTH_API + path

    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
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
            "Modrinth API error (HTTP " + str(e.code) + "): "
            + body[:500]
        ) from e

    except urllib.error.URLError as e:
        txt = str(e)

        if "CERTIFICATE_VERIFY_FAILED" in txt or "certificate" in txt.lower():
            ctx = ssl._create_unverified_context()

            with urllib.request.urlopen(
                req, timeout=25, context=ctx
            ) as r:
                return json.load(r)

        raise RuntimeError(
            "Modrinth API request failed: " + str(e)
        ) from e

    except Exception as e:
        raise RuntimeError(
            "Modrinth API request failed: " + str(e)
        ) from e


def _modrinth_project_type(ptype):
    return {
        "mod": "mod",
        "shader": "shader",
        "resourcepack": "resourcepack"
    }.get(ptype, "mod")


def modrinth_search(query, mc_version, loader=None, project_type="mod"):
    pt = _modrinth_project_type(project_type)

    facets = [
        ["project_type:" + pt],
        ["versions:" + str(mc_version)]
    ]

    if pt == "mod" and loader:
        facets.append(["categories:" + str(loader).lower().strip()])

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


def modrinth_install(project_id, mc_version, loader=None, project_type="mod"):
    """Download the best compatible file into the CURRENT instance."""

    from . import core

    pt = _modrinth_project_type(project_type)

    params = {
        "game_versions": json.dumps([str(mc_version)], separators=(",", ":")),
    }

    if pt == "mod" and loader:
        params["loaders"] = json.dumps(
            [str(loader).lower().strip()],
            separators=(",", ":")
        )

    versions = _modrinth_json(
        "/project/"
        + urllib.parse.quote(project_id, safe="")
        + "/version",
        params
    )

    if not versions:
        raise RuntimeError(
            "No Modrinth version found for this project on Minecraft "
            + str(mc_version)
            + ((" with " + str(loader)) if loader else "")
        )

    ver = versions[0]
    files = ver.get("files", [])

    if not files:
        raise RuntimeError(
            "Modrinth version " + str(ver.get("id", "?"))
            + " has no downloadable files"
        )

    f = next((x for x in files if x.get("primary")), files[0])

    url = f.get("url")
    filename = f.get("filename")

    if not url or not filename:
        raise RuntimeError("Modrinth returned an invalid file entry")

    if pt == "shader":
        folder = "shaderpacks"
    elif pt == "resourcepack":
        folder = "resourcepacks"
    else:
        folder = "mods"

    dest = os.path.join(core.GAME_DIR, folder, filename)

    _download(url, dest)

    if pt == "resourcepack":
        try:
            core.enable_resourcepack(filename)
        except Exception as e:
            raise RuntimeError(
                "Resource pack downloaded, but it could not be "
                "enabled automatically: " + str(e)
            ) from e

    return filename
