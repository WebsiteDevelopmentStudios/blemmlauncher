"""BlemmLauncher core - versions, Forge, OptiFine, mods, packs, Java, progress."""
import socket
socket.setdefaulttimeout(25)

import hashlib
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile

from concurrent.futures import ThreadPoolExecutor, as_completed


LAUNCHER_NAME, LAUNCHER_VERSION = "BlemmLauncher", "1.3.0"

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
LIB_BASE = "https://libraries.minecraft.net/"
RESOURCE_BASE = "https://resources.download.minecraft.net/"
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN = "https://maven.minecraftforge.net"

ADOPTIUM_API = (
    "https://api.adoptium.net/v3/binary/latest/{major}/ga/"
    "windows/x64/jdk/hotspot/normal/eclipse"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    + LAUNCHER_NAME + "/" + LAUNCHER_VERSION + " (contact: local)"
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GAME_DIR = os.environ.get(
    "BLEMM_DIR",
    os.path.join(ROOT, "minecraft")
)

ASSETS = os.path.join(GAME_DIR, "assets")
LIBS = os.path.join(GAME_DIR, "libraries")
TOOLS = os.path.join(GAME_DIR, "tools")


# ============================================================
# PROGRESS REPORTING
# ============================================================

_reporter = None


def set_reporter(fn):
    global _reporter
    _reporter = fn


def _emit(kind, text, done=None, total=None):
    """Send something to the GUI (if a reporter is installed).

    The reporter is always called from worker threads, so it must only
    put things on a queue - never touch Tkinter directly.
    """

    if _reporter:
        try:
            _reporter(kind, text, done, total)
        except Exception:
            pass


def report(stage, done=None, total=None):
    _emit("stage", stage, done, total)


def log(msg):
    """Print to stdout (when it exists - PyInstaller --noconsole kills it)
    and forward to the GUI log."""

    line = "[Blemm] " + str(msg)

    if sys.stdout is not None:
        try:
            print(line)
        except Exception:
            pass

    _emit("log", line)


# ============================================================
# HELPERS
# ============================================================

def os_name():
    return {
        "Windows": "windows",
        "Darwin": "osx"
    }.get(platform.system(), "linux")


def file_sha1(p):
    h = hashlib.sha1()

    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)

    return h.hexdigest()


def _open(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    return urllib.request.urlopen(req, timeout=25)


def download(url, dest, sha1=None):
    dest = os.path.normpath(dest)

    d = os.path.dirname(dest)

    if d:
        os.makedirs(d, exist_ok=True)

    if os.path.exists(dest):
        if sha1 is None or file_sha1(dest) == sha1:
            return

    tmp = dest + ".part"

    for attempt in (1, 2, 3):
        try:
            with _open(url) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)

            break

        except Exception as e:
            if attempt == 3:
                raise RuntimeError(
                    "download failed: " + url + " -> " + str(e)
                ) from e

            import time
            time.sleep(1 * attempt)

    os.replace(tmp, dest)


def fetch_json(url):
    with _open(url) as r:
        return json.load(r)


def maven_path(name):
    g, aid, ver, *ext = name.split(":")

    return (
        g.replace(".", "/") + "/" + aid + "/" + ver + "/"
        + aid + "-" + ver
        + (("-" + ext[0]) if ext else "")
        + ".jar"
    )


# ============================================================
# JAVA
# ============================================================

def _required_java(vid):
    try:
        parts = [int(x) for x in vid.split(".") if x.isdigit()]

        major = parts[1] if len(parts) > 1 else 0
        minor = parts[2] if len(parts) > 2 else 0

        if major > 20 or (major == 20 and minor >= 5):
            return "21"

        if major >= 18:
            return "17"

        if major == 17:
            return "16"

        return "8"

    except Exception:
        return "17"


def _system_java_major():
    """Return the major version of the `java` on PATH, or None."""

    try:
        exe = "java.exe" if os_name() == "windows" else "java"

        if not shutil.which(exe):
            return None

        r = subprocess.run(
            [exe, "-version"],
            capture_output=True,
            timeout=30
        )

        txt = ((r.stderr or b"") + (r.stdout or b"")).decode(errors="replace")

        m = re.search(r'version "([^"]+)"', txt)

        if not m:
            return None

        v = m.group(1).split(".")

        if v and v[0] == "1":
            return int(v[1]) if len(v) > 1 else None

        return int(v[0])

    except Exception:
        return None


def java_bin_for(version_id, major=None):
    exe = "java.exe" if os_name() == "windows" else "java"

    if major is None:
        major = _required_java(version_id)

    try:
        major_int = int(major)
    except Exception:
        major_int = None

    # Only trust the system java if it exists AND is new enough
    # for the Minecraft version being launched. This is what keeps
    # old PATH javas from crashing modern versions.

    if shutil.which(exe) and major_int is not None:
        sysmaj = _system_java_major()

        if sysmaj is None or sysmaj >= major_int:
            return exe

    jdir = os.path.join(TOOLS, "java-" + str(major))

    jbin = os.path.join(jdir, "bin", exe)

    if not os.path.exists(jbin):
        report(
            "Downloading Java " + str(major)
            + " (one time, ~180 MB)..."
        )

        os.makedirs(TOOLS, exist_ok=True)

        zpath = os.path.join(TOOLS, "jdk" + str(major) + ".zip")

        download(ADOPTIUM_API.format(major=major), zpath)

        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(zpath) as z:
                z.extractall(td)

            inner = os.listdir(td)[0]

            os.replace(os.path.join(td, inner), jdir)

        os.remove(zpath)

        if os_name() != "windows":
            import stat

            for r, _, fs in os.walk(jdir):
                for f in fs:
                    p = os.path.join(r, f)
                    st = os.stat(p)
                    os.chmod(p, st.st_mode | stat.S_IEXEC)

    return jbin


def _mc_major(version_id):
    try:
        return int(version_id.split(".")[1])
    except Exception:
        return 20


# ============================================================
# GAME DIR
# ============================================================

def set_game_dir(path, assets_dir=None, tools_dir=None, libs_dir=None):
    """Point the whole launcher at an instance directory.

    ASSETS / TOOLS can be overridden so instances can share the big
    global asset index and downloaded Java runtimes (instances.py uses
    this), while LIBS stays per-instance. Every dependent path is
    updated together so nothing leaks from a previous instance.
    """

    global GAME_DIR, ASSETS, LIBS, TOOLS

    GAME_DIR = path

    ASSETS = assets_dir or os.path.join(GAME_DIR, "assets")
    LIBS = libs_dir or os.path.join(GAME_DIR, "libraries")
    TOOLS = tools_dir or os.path.join(GAME_DIR, "tools")


# ============================================================
# MANIFEST / VERSIONS
# ============================================================

def manifest():
    for attempt in (1, 2, 3):
        try:
            return fetch_json(MANIFEST_URL)

        except Exception as e:
            if attempt == 3:
                raise RuntimeError(
                    "can't reach Mojang (attempt 3): " + str(e) + "\n"
                    "check internet / firewall / proxy, then retry"
                ) from e

            log("manifest fetch failed (" + str(e) + ") - retrying...")


def list_versions():
    m = manifest()

    return (
        [v["id"] for v in m["versions"]],
        m["latest"]["release"],
        m["latest"]["snapshot"]
    )


def resolve_version(version_id, m):
    if version_id in (None, "", "release"):
        return m["latest"]["release"]

    if version_id == "snapshot":
        return m["latest"]["snapshot"]

    if not any(v["id"] == version_id for v in m["versions"]):
        if os.path.exists(
            os.path.join(GAME_DIR, "versions", version_id, version_id + ".json")
        ):
            return version_id

        raise RuntimeError("Unknown version '" + str(version_id) + "'.")

    return version_id


def load_version_json(vid, m):
    """Load a version JSON and resolve inheritsFrom-style parents."""

    path = os.path.join(GAME_DIR, "versions", vid, vid + ".json")

    if not os.path.exists(path):
        vurl = None

        for v in m["versions"]:
            if v["id"] == vid:
                vurl = v["url"]
                break

        if vurl is None:
            raise RuntimeError(
                "Version info for '" + str(vid) + "' could not be found "
                "in the Mojang manifest or locally."
            )

        report("Downloading version info...")
        download(vurl, path)

    with open(path, encoding="utf-8") as f:
        vj = json.load(f)

    if "inheritsFrom" in vj:
        parent = load_version_json(vj["inheritsFrom"], m)

        vj["libraries"] = (
            vj.get("libraries", []) + parent.get("libraries", [])
        )

        pj = parent.get("arguments", {})
        cj = vj.get("arguments", {})

        vj["arguments"] = {
            "game": pj.get("game", []) + cj.get("game", []),
            "jvm": pj.get("jvm", []) + cj.get("jvm", [])
        }

        vj.setdefault("mainClass", parent["mainClass"])
        vj.setdefault("assetIndex", parent.get("assetIndex"))
        vj.setdefault("downloads", parent.get("downloads"))
        vj.setdefault("logging", parent.get("logging"))
        vj.setdefault("minecraftArguments", parent.get("minecraftArguments"))

        vj["_java_major"] = (
            vj.get("javaVersion", {}).get("majorVersion")
            or parent.get("_java_major")
            or parent.get("javaVersion", {}).get("majorVersion")
        )

        vj["_vanilla_id"] = vj["inheritsFrom"]

    else:
        vj["_java_major"] = vj.get("javaVersion", {}).get("majorVersion")
        vj["_vanilla_id"] = vid

    report("Downloading game files...", 5, 100)

    d = vj.get("downloads", {}).get("client")

    if not d:
        raise RuntimeError(
            "version JSON for '" + str(vid) + "' has no client download "
            "(its parent version may be missing or corrupt)"
        )

    jar = os.path.join(
        GAME_DIR,
        "versions",
        vj["_vanilla_id"],
        vj["_vanilla_id"] + ".jar"
    )

    download(d["url"], jar, d.get("sha1"))

    return vj


# ============================================================
# RULES / LIBRARIES / NATIVES
# ============================================================

def rule_matches(rule):
    if "os" not in rule:
        return True

    osr = rule["os"]

    if osr.get("name") and osr["name"] != os_name():
        return False

    return True


def is_allowed(rules):
    if not rules:
        return True

    allowed = True
    matched = False

    for r in rules:
        if rule_matches(r):
            allowed = r.get("action") == "allow"
            matched = True

    return allowed if matched else True


def install_libraries(vj):
    natives_dir = os.path.join(GAME_DIR, "natives", vj.get("id", vj["_vanilla_id"]))

    os.makedirs(natives_dir, exist_ok=True)

    classpath = []
    seen = set()

    todo = [
        lib
        for lib in vj.get("libraries", [])
        if is_allowed(lib.get("rules"))
    ]

    for i, lib in enumerate(todo):
        report("Downloading libraries...", i, max(len(todo), 1))

        dl = lib.get("downloads", {})
        art = dl.get("artifact")

        if art:
            rp = art["path"]
        elif lib.get("name"):
            rp = maven_path(lib["name"])
        else:
            continue

        if not rp or rp in seen:
            continue

        seen.add(rp)

        jar = os.path.normpath(os.path.join(LIBS, rp))

        if art:
            url = art.get("url")
        else:
            repo = lib.get("url")

            if repo:
                # Fabric-style entries carry a maven base URL per
                # library instead of downloads.artifact.
                url = repo.rstrip("/") + "/" + rp
            else:
                url = FORGE_MAVEN + "/" + rp

        try:
            if art:
                download(url, jar, art.get("sha1"))
            else:
                download(url, jar)

        except Exception:
            if url.startswith(LIB_BASE):
                other = FORGE_MAVEN
            elif url.startswith(FORGE_MAVEN):
                other = LIB_BASE
            else:
                other = None

            if not other:
                raise RuntimeError(
                    "a required library could not be downloaded: "
                    + rp
                )

            download(other.rstrip("/") + "/" + rp, jar)

        classpath.append(jar)

        classifier = lib.get("natives", {}).get(os_name())

        if classifier:
            nart = dl.get("classifiers", {}).get(classifier)

            if nart:
                njar = os.path.normpath(os.path.join(LIBS, nart["path"]))

                download(nart["url"], njar, nart.get("sha1"))

                with zipfile.ZipFile(njar) as z:
                    for info in z.infolist():
                        n = os.path.basename(info.filename)

                        if (
                            info.filename.startswith("META-INF/")
                            or n.endswith((".sha1", ".sha", ".git"))
                        ):
                            continue

                        if n:
                            with z.open(info) as s, open(
                                os.path.join(natives_dir, n), "wb"
                            ) as o:
                                shutil.copyfileobj(s, o)

    if not classpath:
        raise RuntimeError(
            "no libraries could be resolved for this version - "
            "the version JSON may be corrupt"
        )

    return classpath, natives_dir


def install_assets(vj):
    idx = vj.get("assetIndex")

    if not idx:
        return vj.get("assets", "legacy")

    idp = os.path.join(ASSETS, "indexes", idx["id"] + ".json")

    download(idx["url"], idp, idx.get("sha1"))

    with open(idp, encoding="utf-8") as f:
        objects = json.load(f).get("objects", {})

    items = list(objects.items())
    total = max(len(items), 1)
    done = 0
    failures = []

    def _fetch(entry):
        name, obj = entry
        h = obj["hash"]

        try:
            download(
                RESOURCE_BASE + h[:2] + "/" + h,
                os.path.join(ASSETS, "objects", h[:2], h),
                h
            )

            return None

        except Exception as e:
            return name + ": " + str(e)

    report(
        "Downloading game assets (biggest step, first time only)...",
        0,
        total
    )

    with ThreadPoolExecutor(max_workers=24) as ex:
        futures = [ex.submit(_fetch, item) for item in items]

        for fut in as_completed(futures):
            done += 1

            if done % 25 == 0 or done == total:
                report(
                    "Downloading game assets (biggest step, first time only)...",
                    done,
                    total
                )

            err = fut.result()

            if err:
                failures.append(err)
                log("  ! " + err)

    if failures and len(failures) == total:
        raise RuntimeError(
            "all asset downloads failed - check your internet connection"
        )

    return idx["id"]


# ============================================================
# OPTIFINE
# ============================================================

def _jar_names(path):
    try:
        with zipfile.ZipFile(path) as z:
            return set(z.namelist())
    except Exception:
        return set()


def looks_like_optifine(path):
    """Heuristic OptiFine detection - filename first, contents second.

    Content checks pick a couple of OptiFine-specific class names that
    common unrelated mods won't have, so we don't mis-tag random mods.
    """

    name = os.path.basename(path).lower()

    if not name.endswith(".jar"):
        return False

    if "optifine" in name:
        return True

    names = _jar_names(path)

    if "Config.class" in names and any(
        n in names
        for n in ("OptiFineTweaker.class", "OptiFineForgeTweaker.class")
    ):
        return True

    return False


def _is_optifine_installer(path):
    """Distinguish the official OptiFine installer JAR from a plain
    OptiFine mod JAR."""

    names = _jar_names(path)

    if any(n.startswith("optifine/Installer") for n in names):
        return True

    if "InstallerFrame.class" in names:
        return True

    if any(n.startswith("xdelta") for n in names):
        return True

    return False


def find_optifine_jars():
    """Find ACTIVE OptiFine JARs in the CURRENT instance's mods folder.

    Files renamed to <name>.jar.disabled while OptiFine is switched
    off are ignored - they are restored automatically after a launch.
    Multiple matches are returned sorted so behavior is deterministic.
    """

    mods_dir = os.path.join(GAME_DIR, "mods")

    if not os.path.isdir(mods_dir):
        return []

    found = []

    for filename in os.listdir(mods_dir):
        if not filename.lower().endswith(".jar"):
            continue

        p = os.path.join(mods_dir, filename)

        if looks_like_optifine(p):
            found.append(p)

    return sorted(found)


def _optifine_detected_version(path):
    """Pull the Minecraft version out of an OptiFine filename, or None.

    OptiFine files are named like 'OptiFine_1.20.1_HD_U_I6.jar'.
    """

    m = re.search(
        r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)",
        os.path.basename(path)
    )

    return m.group(1) if m else None


def install_optifine(installer_jar, version_id=None):
    """Install OptiFine into the CURRENT instance's mods folder.

    The user picks the official OptiFine installer JAR, or an already
    extracted plain OptiFine mod JAR. Installer JARs are repacked
    into a plain mod JAR (that's what Forge/NeoForge load from mods/);
    plain mod JARs are copied as-is.

    `version_id` is the instance's Minecraft version, used to catch
    obvious version mismatches before the game crashes. Nothing on
    disk is deleted or overwritten silently.
    """

    if not installer_jar:
        raise RuntimeError("No OptiFine file was selected.")

    src = os.path.abspath(installer_jar)

    if not os.path.isfile(src):
        raise RuntimeError("OptiFine file not found:\n" + src)

    if not zipfile.is_zipfile(src):
        raise RuntimeError("The selected OptiFine file is not a valid JAR.")

    if not looks_like_optifine(src):
        raise RuntimeError(
            "The selected JAR doesn't look like OptiFine "
            "(its filename and contents don't match)."
        )

    mods_dir = os.path.join(GAME_DIR, "mods")
    os.makedirs(mods_dir, exist_ok=True)

    base = os.path.basename(src)

    out_name = base.replace("_installer", "").replace("_Installing", "")

    if not out_name.lower().endswith(".jar"):
        out_name += ".jar"

    # Sanity check: OptiFine is Minecraft-version specific.
    of_ver = _optifine_detected_version(src)

    if of_ver and version_id:
        base_ver = version_id.split("-")[0]

        if of_ver != base_ver:
            raise RuntimeError(
                "OptiFine version mismatch: this OptiFine build is for "
                "Minecraft " + of_ver + ", but this instance uses "
                + base_ver + ".\n"
                "Download the OptiFine build that matches your "
                "Minecraft version."
            )

    out = os.path.join(mods_dir, out_name)

    if os.path.exists(out):
        log("OptiFine already present in mods: " + out_name)
        return out

    if _is_optifine_installer(src):
        # Repack the installer into a plain mod JAR. META-INF is
        # dropped so the installer's signing/manifest entries can't
        # confuse the mod loader.
        try:
            with zipfile.ZipFile(src) as zin, \
                    zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    if info.filename.startswith("META-INF/"):
                        continue

                    zout.writestr(info, zin.read(info.filename))

        except Exception:
            if os.path.exists(out):
                os.remove(out)

            shutil.copy2(src, out)

        log("OptiFine mod JAR installed: " + out)

    else:
        shutil.copy2(src, out)
        log("OptiFine mod JAR copied to mods: " + out)

    return out


def _temp_disable_optifine():
    """Rename OptiFine JARs to <name>.jar.disabled for one launch.

    NOTHING is ever deleted. The caller must pass the returned list
    to _restore_optifine(), which should run inside a finally block.
    """

    disabled = []

    for jar in find_optifine_jars():
        dp = jar + ".disabled"

        try:
            os.replace(jar, dp)
            disabled.append((dp, jar))
            log("OptiFine disabled for this launch: " + os.path.basename(jar))

        except OSError as e:
            log("could not temporarily disable " + jar + ": " + str(e))

    return disabled


def _restore_optifine(disabled):
    """Undo _temp_disable_optifine(). Runs even if Minecraft crashed."""

    for dp, orig in disabled:
        try:
            if os.path.exists(dp):
                os.replace(dp, orig)

        except OSError as e:
            log("WARNING: could not restore " + dp + ": " + str(e))


# ============================================================
# FORGE
# ============================================================

def ensure_launcher_profile(game_dir):
    lp = os.path.join(game_dir, "launcher_profiles.json")

    if not os.path.exists(lp):
        os.makedirs(game_dir, exist_ok=True)

        with open(lp, "w", encoding="utf-8") as f:
            json.dump({"profiles": {}, "settings": {}, "version": 3}, f)


def _forge_locally_processed(vj):
    for lib in vj.get("libraries", []):
        if not lib.get("name", "").startswith("net.minecraftforge:forge:"):
            continue

        art = lib.get("downloads", {}).get("artifact")

        if art and not os.path.exists(
            os.path.normpath(os.path.join(LIBS, art["path"]))
        ):
            return False

    return True


def install_forge(mc_version, build=None):
    """Install Forge for ANY Minecraft version using the promotions API.

    The build/version are resolved from live Forge metadata - nothing
    about the Minecraft or Forge version is hard-coded.
    """

    if build in (None, "auto", "", "recommended", "latest"):
        try:
            promos = fetch_json(FORGE_PROMOS)["promos"]

            build = (
                promos.get(mc_version + "-recommended")
                or promos.get(mc_version + "-latest")
            )

        except Exception:
            build = None

        if not build:
            raise RuntimeError(
                "No Forge build found for " + str(mc_version)
                + ". Forge may not support this version yet."
            )

    vid = mc_version + "-forge-" + str(build)

    existing = os.path.join(GAME_DIR, "versions", vid, vid + ".json")

    if os.path.exists(existing):
        try:
            with open(existing, encoding="utf-8") as f:
                vj = json.load(f)

            if _forge_locally_processed(vj):
                log("Forge " + vid + " already installed.")
                return vid

        except Exception:
            pass

        log("Forge " + vid + " install looks incomplete - reinstalling...")
        shutil.rmtree(os.path.dirname(existing), ignore_errors=True)

    m = manifest()

    load_version_json(resolve_version(mc_version, m), m)

    os.makedirs(TOOLS, exist_ok=True)

    installer = os.path.join(TOOLS, "forge-" + vid + "-installer.jar")

    ilurl = (
        FORGE_MAVEN + "/net/minecraftforge/forge/"
        + mc_version + "-" + str(build) + "/"
        + "forge-" + mc_version + "-" + str(build) + "-installer.jar"
    )

    report("Downloading Forge installer...")
    download(ilurl, installer)

    report("Installing Forge (running official installer)...")

    ensure_launcher_profile(GAME_DIR)

    java = java_bin_for(mc_version)

    r = subprocess.run(
        [java, "-jar", installer, "--installClient"],
        cwd=GAME_DIR,
        capture_output=True
    )

    outp = ((r.stdout or b"") + (r.stderr or b"")).decode(errors="replace")

    matches = [
        p
        for p in glob.glob(
            os.path.join(GAME_DIR, "versions", mc_version + "*forge*")
        )
        if os.path.exists(os.path.join(p, os.path.basename(p) + ".json"))
    ]

    matches.sort(key=os.path.getmtime, reverse=True)

    if r.returncode != 0 or not matches:
        raise RuntimeError(
            "Forge install failed (installer exit code "
            + str(r.returncode) + ").\n"
            "--- installer output ---\n" + outp[-1500:]
        )

    found = os.path.basename(matches[0])

    with open(
        os.path.join(matches[0], found + ".json"), encoding="utf-8"
    ) as f:
        vj_check = json.load(f)

    if not _forge_locally_processed(vj_check):
        raise RuntimeError(
            "Forge installer exited OK but its processors step didn't "
            "finish (the local client jars are missing).\n"
            "--- installer output ---\n" + outp[-1500:]
        )

    log("Forge installed: " + found)

    return found


# ============================================================
# CONTENT: MODS / PACKS / SHADERS
# ============================================================

def detect_kind(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())

    except zipfile.BadZipFile:
        return None

    if (
        "fabric.mod.json" in names
        or "mcmod.info" in names
        or "META-INF/mods.toml" in names
        or "quilt.mod.json" in names
    ):
        return "mod"

    if "pack.mcmeta" in names:
        if any(n.startswith("shaders/") for n in names):
            return "shaderpack"

        return "resourcepack"

    return None


def add_content_auto(paths, kind=None):
    folders = {
        "mod": "mods",
        "resourcepack": "resourcepacks",
        "shaderpack": "shaderpacks"
    }

    installed = []

    for p in paths:
        use_kind = (
            kind
            if kind in folders
            else (
                detect_kind(p)
                or ("mod" if p.lower().endswith(".jar") else "resourcepack")
            )
        )

        dest_dir = os.path.join(GAME_DIR, folders[use_kind])

        os.makedirs(dest_dir, exist_ok=True)

        shutil.copy2(p, os.path.join(dest_dir, os.path.basename(p)))

        installed.append(use_kind + ": " + os.path.basename(p))

        if use_kind == "resourcepack":
            enable_resourcepack(os.path.basename(p))

    log("Imported " + str(len(installed)) + " file(s): " + ", ".join(installed))

    return installed


def enable_resourcepack(filename):
    opts_path = os.path.join(GAME_DIR, "options.txt")

    entry = 'resourcePacks:["file/' + filename + '"]'

    lines = []

    if os.path.exists(opts_path):
        with open(opts_path, encoding="utf-8") as f:
            lines = f.read().splitlines()

    lines = [l for l in lines if not l.startswith("resourcePacks:")]

    lines.append(entry)

    with open(opts_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ============================================================
# LAUNCH
# ============================================================

def subst(s, subs):
    for k, v in subs.items():
        s = s.replace(k, v)

    return s


def resolve_arglist(items, subs):
    out = []

    quick_play_options = {
        "--quickPlaySingleplayer",
        "--quickPlayMultiplayer",
        "--quickPlayRealms"
    }

    for a in items:
        if isinstance(a, str):
            values = [a]

        else:
            if not is_allowed(a.get("rules")):
                continue

            v = a["value"]

            values = v if isinstance(v, list) else [v]

        for value in values:
            value = subst(value, subs)

            if value == "-XstartOnFirstThread" and platform.system() != "Darwin":
                continue

            if value in quick_play_options:
                continue

            out.append(value)

    return out


def _detect_loader(vj):
    """Figure out the mod loader from the version's actual library data."""

    for lib in vj.get("libraries", []):
        n = lib.get("name") or ""

        if n.startswith("net.fabricmc:fabric-loader"):
            return "fabric"

        if (
            n.startswith("net.minecraftforge:forge")
            or n.startswith("net.minecraftforge:minecraftforge")
            or n.startswith("net.minecraftforge:eventbus")
        ):
            return "forge"

        if (
            n.startswith("net.neoforged:neoforge")
            or n.startswith("net.neoforged.fancymodloader")
        ):
            return "neoforge"

    return None


def launch(version_id, username="Blemm", ram="2G", optifine=False):
    """Launch Minecraft.

    `optifine` is a BOOLEAN: whether OptiFine should be ACTIVE for
    this launch. Installing OptiFine is handled separately by
    install_optifine().

    When optifine is False, OptiFine JARs in mods/ are renamed to
    <name>.jar.disabled for the duration of the launch. They are
    ALWAYS restored afterwards - including when Minecraft crashes -
    because the game runs inside try/finally, not after it.
    """

    m = manifest()

    vid = resolve_version(version_id, m)

    vj = load_version_json(vid, m)

    java = java_bin_for(vid, vj.get("_java_major"))

    vanilla_jar = os.path.join(
        GAME_DIR,
        "versions",
        vj["_vanilla_id"],
        vj["_vanilla_id"] + ".jar"
    )

    classpath, natives_dir = install_libraries(vj)

    if os.path.exists(vanilla_jar):
        classpath.insert(0, vanilla_jar)

    asset_id = install_assets(vj)

    game_args = (
        vj.get("arguments", {}).get("game")
        or vj.get("minecraftArguments", "").split()
    )

    jvm_args = (
        vj.get("arguments", {}).get("jvm")
        or [
            "-Djava.library.path=${natives_directory}",
            "-Dminecraft.launcher.brand=${launcher_name}",
            "-Dminecraft.launcher.version=${launcher_version}",
            "-cp",
            "${classpath}"
        ]
    )

    loader_kind = _detect_loader(vj)

    # --------------------------------------------------------
    # OPTIFINE (activation - installation is separate)
    # --------------------------------------------------------

    if optifine:
        optifine_jars = find_optifine_jars()

        if not optifine_jars:
            log(
                "OptiFine is enabled, but no OptiFine JAR was found in "
                "mods/. Use 'Install OptiFine...' or add the JAR manually."
            )

        else:
            if len(optifine_jars) > 1:
                log(
                    "WARNING: multiple OptiFine JARs found in mods/ - this "
                    "can crash the game. Remove all but one."
                )

            if loader_kind is None:
                log(
                    "NOTE: this instance is VANILLA. Vanilla Minecraft "
                    "ignores the mods/ folder, so OptiFine will NOT "
                    "load. Use a Forge or NeoForge instance to load "
                    "OptiFine from mods/."
                )

            elif loader_kind == "fabric":
                log(
                    "WARNING: Fabric does not load OptiFine as a mod. "
                    "Use Forge/NeoForge for this instance, or remove "
                    "OptiFine from mods/."
                )

            for jar in optifine_jars:
                log("OptiFine active: " + os.path.basename(jar))

                of_ver = _optifine_detected_version(jar)

                if of_ver and of_ver != vj["_vanilla_id"]:
                    log(
                        "WARNING: OptiFine is for Minecraft " + of_ver
                        + " but the game is " + vj["_vanilla_id"]
                        + " - this may crash."
                    )

    subs = {
        "${auth_player_name}": username,

        "${auth_uuid}": str(
            uuid.uuid3(uuid.NAMESPACE_OID, "offline:" + username)
        ),

        "${auth_access_token}": "0",
        "${auth_session}": "0",
        "${user_type}": "legacy",
        "${user_properties}": "{}",

        "${version_name}": vid,
        "${version_type}": LAUNCHER_NAME,

        "${game_directory}": os.path.abspath(GAME_DIR),

        "${assets_root}": os.path.abspath(ASSETS),

        "${assets_index_name}": asset_id,

        "${game_assets}": os.path.join(
            ASSETS,
            "virtual",
            asset_id
        ),

        "${natives_directory}": os.path.abspath(natives_dir),

        "${launcher_name}": LAUNCHER_NAME,
        "${launcher_version}": LAUNCHER_VERSION,

        "${classpath}": os.pathsep.join(classpath),

        "${classpath_separator}": os.pathsep,

        "${library_directory}": os.path.abspath(LIBS),

        "${primary_jar}": os.path.abspath(vanilla_jar),

        "${clientid}": "0" * 32,
        "${auth_xuid}": "0",

        "${resolution_width}": "854",
        "${resolution_height}": "480"
    }

    cmd = [
        java,
        "-Xms512M",
        "-Xmx" + str(ram)
    ]

    log_cfg = vj.get("logging", {}).get("client", {})

    if log_cfg:
        lf = os.path.join(
            GAME_DIR,
            "log-configs",
            log_cfg["file"]["id"]
        )

        download(
            log_cfg["file"]["url"],
            lf,
            log_cfg["file"].get("sha1")
        )

        cmd.append(
            "-Dlog4j.configurationFile=" + os.path.abspath(lf)
        )

    cmd += (
        resolve_arglist(jvm_args, subs)
        + [vj["mainClass"]]
        + resolve_arglist(game_args, subs)
    )

    os.makedirs(GAME_DIR, exist_ok=True)

    log(
        "Launching " + vid + " as " + username
        + " (Java " + str(vj.get("_java_major") or _required_java(vid)) + ")..."
    )

    report("Starting Minecraft...", 99, 100)

    # OptiFine JARs are only hidden for the duration of the game
    # process, and the restore in `finally` runs even if the game
    # crashes or launching raises.

    disabled = [] if optifine else _temp_disable_optifine()

    try:
        result = subprocess.run(
            cmd,
            cwd=GAME_DIR,
            capture_output=True
        )

    finally:
        if disabled:
            _restore_optifine(disabled)

    report("Minecraft closed.", 100, 100)

    if result.returncode != 0:
        out = (result.stdout or b"") + (result.stderr or b"")

        tail = out.decode(errors="replace").strip()[-1200:]

        raise RuntimeError(
            "Minecraft crashed instantly (exit code "
            + str(result.returncode) + ").\n"
            "--- last output ---\n" + tail + "\n"
            "-------------------\n"
            "If this mentions 'UnsupportedClassVersionError', the Java "
            "version is wrong for this Minecraft version."
        )
