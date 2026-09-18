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
            # Broken cert store / wrong system clock. Retry unverified.
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
            # Certificate problems (an expired/unknown chain, often a
            # wrong system clock) shouldn't block a game download.
            # Retry once with verification disabled.

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
    """Point core at this instance. Everything (mods, libraries,
    version JSONs, natives) is per-instance; assets and Java runtimes
    are shared globally so they aren't re-downloaded per instance.
    """

    d = instance_dir(name)

    core.set_game_dir(
        d,
        assets_dir=SHARED_ASSETS,
        tools_dir=SHARED_TOOLS
    )

    return d


# ============================================================
# EXPORT / IMPORT
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
                or os.sep + "versions" in root
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
    """True if versions/<vid>/<vid>.json exists for this instance."""
    p = os.path.join(
        core.GAME_DIR,
        "versions",
        vid,
        vid + ".json"
    )
    return os.path.exists(p)


def install_fabric(mc_version):
    """Install Fabric for this instance. RETURNS the installed version
    id (like 'fabric-loader-0.16.x-1.21.1') so the caller can launch
    the Fabric version instead of vanilla.
    """

    from . import core

    # Fast path: already installed for this instance?
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
    """Compute the NeoForge version series from a Minecraft version.

    1.20.1 -> '20.1', 1.21.4 -> '21.4', 1.21 -> '21.0' etc.
    """

    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?$", str(mc_version))

    if not m:
        return None

    minor = m.group(2)
    patch = m.group(3) or "0"

    return minor + "." + patch


def install_neoforge(mc_version, build=None):
    """Install NeoForge for this instance. RETURNS the installed version
    id (like 'neoforge-21.1.95') so the caller launches the modded
    version, not vanilla.
    """

    from . import core

    # Fast path: known build already installed?
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

    # Fast path once more with the resolved build.
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
    """Search Modrinth for projects compatible with a Minecraft version."""

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
    """Download the best compatible file into the CURRENT instance.

    The destination depends on the project type: mods/ for mods,
    shaderpacks/ for shaders, resourcepacks/ for resource packs
    (which are also auto-enabled). core.GAME_DIR must already point
    at the right instance (the GUI handles that).
    """

    from . import core

    pt = _modrinth_project_type(project_type)

    params = {
        "game_versions": json.dumps([str(mc_version)], separators=(",", ":")),
    }

    # Loader filtering only makes sense for mods; shaders/packs list
    # 'iris'/'optifine'/'minecraft' as loaders, so don't filter there.

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
