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
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

from concurrent.futures import ThreadPoolExecutor, as_completed


LAUNCHER_NAME, LAUNCHER_VERSION = "BlemmLauncher", "1.3.0"

# ============================================================
# FORCE REMOVE DEMO MODE GLOBAL BYPASS
# ============================================================
_orig_run = subprocess.run
def _patched_run(cmd, *args, **kwargs):
    if isinstance(cmd, list) and "--demo" in cmd:
        cmd.remove("--demo")
    return _orig_run(cmd, *args, **kwargs)
subprocess.run = _patched_run

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

LAUNCHWRAPPER_URL = (
    LIB_BASE + "net/minecraft/launchwrapper/1.12/"
    "launchwrapper-1.12.jar"
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
_reporters = []

def set_reporter(fn):
    global _reporter, _reporters
    _reporter = fn
    _reporters = [fn] if fn else []

def add_reporter(fn):
    if fn and fn not in _reporters:
        _reporters.append(fn)

def remove_reporter(fn):
    try:
        _reporters.remove(fn)
    except ValueError:
        pass

def _emit(kind, text, done=None, total=None):
    targets = list(_reporters)
    if _reporter and _reporter not in targets:
        targets.append(_reporter)
    for reporter in targets:
        try:
            reporter(kind, text, done, total)
        except Exception:
            pass

def report(stage, done=None, total=None):
    _emit("stage", stage, done, total)


def log(msg):
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
    """Open a URL. If certificate verification fails (broken cert
    store / wrong system clock), retry once without strict
    verification so a single bad chain can't block the launcher."""

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    try:
        return urllib.request.urlopen(req, timeout=25)
    except urllib.error.URLError as e:
        txt = str(e)

        if "CERTIFICATE_VERIFY_FAILED" in txt or "certificate" in txt.lower():
            log(
                "SSL certificate problem while downloading - retrying "
                "without strict verification. (Check your system clock / "
                "cert store!)"
            )

            ctx = ssl._create_unverified_context()

            return urllib.request.urlopen(req, timeout=25, context=ctx)

        raise


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
                total = r.headers.get("Content-Length")
                try:
                    total = int(total) if total else None
                except (TypeError, ValueError):
                    total = None

                downloaded = 0
                last_report = 0
                chunk_size = 1024 * 256

                while True:
                    chunk = r.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    # Don't flood the GUI queue. Update roughly every
                    # 512 KiB while still making large downloads visible.
                    if downloaded - last_report >= 512 * 1024 or (
                        total and downloaded >= total
                    ):
                        last_report = downloaded

                        if total:
                            mb = downloaded / (1024 * 1024)
                            total_mb = total / (1024 * 1024)
                            report(
                                "Downloading "
                                + os.path.basename(dest)
                                + " — "
                                + "{:.1f}".format(mb)
                                + " / "
                                + "{:.1f}".format(total_mb)
                                + " MB",
                                downloaded,
                                total
                            )
                        else:
                            report(
                                "Downloading "
                                + os.path.basename(dest)
                                + " — "
                                + "{:.1f}".format(downloaded / (1024 * 1024))
                                + " MB",
                                None,
                                None
                            )

                if total and downloaded < total:
                    raise RuntimeError(
                        "download ended early: received "
                        + str(downloaded)
                        + " of "
                        + str(total)
                        + " bytes"
                    )

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
        text = str(vid).strip()

        # Starting with Minecraft 26.1, the game/server requires Java 25.
        # The new 26.x versioning scheme means the first numeric component
        # is the Minecraft release year, not the old 1.x minor component.
        m = re.match(r"^(\d+)\.(\d+)", text)

        if m:
            first = int(m.group(1))
            second = int(m.group(2))

            if first >= 26:
                return "25"

            # Old 1.x Minecraft versioning.
            if first == 1:
                major = second

                parts = [int(x) for x in text.split(".") if x.isdigit()]
                minor = parts[2] if len(parts) > 2 else 0

                if major > 20 or (major == 20 and minor >= 5):
                    return "21"

                if major >= 18:
                    return "17"

                if major == 17:
                    return "16"

                return "8"

        return "17"

    except Exception:
        return "17"


def _system_java_major():
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

    # Only trust the system java if it exists AND is new enough for
    # the Minecraft version being launched.

    if shutil.which(exe) and major_int is not None:
        sysmaj = _system_java_major()

        # A 32-bit JVM can report the correct Java major but cannot reserve
        # the multi-gigabyte heaps Minecraft servers commonly need. Only use
        # the system JVM when it is explicitly a 64-bit VM.
        try:
            r = subprocess.run(
                [exe, "-version"],
                capture_output=True,
                timeout=30
            )
            txt = ((r.stderr or b"") + (r.stdout or b"")).decode(errors="replace")
            is_64 = (
                "64-Bit" in txt
                or "amd64" in txt.lower()
                or "x86_64" in txt.lower()
                or "aarch64" in txt.lower()
            )
        except Exception:
            is_64 = False

        if sysmaj is not None and sysmaj >= major_int and is_64:
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
            try:
                with zipfile.ZipFile(zpath) as z:
                    z.extractall(td)
            except zipfile.BadZipFile as e:
                raise RuntimeError(
                    "Java download was not a valid ZIP archive. "
                    "The runtime was not installed."
                ) from e

            # Adoptium archives contain one top-level JDK directory, but
            # don't assume its exact name or ordering.
            candidates = []
            for r, dirs, files in os.walk(td):
                if os.path.isfile(os.path.join(r, "bin", exe)):
                    candidates.append(r)

            if not candidates:
                raise RuntimeError(
                    "Java " + str(major) + " downloaded, but no executable "
                    + exe + " was found in the archive."
                )

            if os.path.exists(jdir):
                shutil.rmtree(jdir, ignore_errors=True)
            os.replace(candidates[0], jdir)

        try:
            os.remove(zpath)
        except OSError:
            pass

        if os_name() != "windows":
            import stat
            for r, _, fs in os.walk(jdir):
                for f in fs:
                    p = os.path.join(r, f)
                    st = os.stat(p)
                    os.chmod(p, st.st_mode | stat.S_IEXEC)

    if not os.path.exists(jbin):
        raise RuntimeError("Managed Java " + str(major) + " installation is incomplete.")

    # Verify the runtime before returning it. This catches silent/corrupt
    # downloads instead of letting a later installer fail with a vague error.
    try:
        check = subprocess.run(
            [jbin, "-version"],
            capture_output=True,
            timeout=30
        )
        if check.returncode != 0:
            raise RuntimeError(
                "Managed Java " + str(major) + " was installed but could not start:\n"
                + ((check.stderr or b"") + (check.stdout or b"")).decode(errors="replace")[-1200:]
            )
    except FileNotFoundError as e:
        raise RuntimeError("Managed Java executable was not found after installation.") from e

    return jbin


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
    """Load a version JSON and resolve inheritsFrom-style parents.

    If the version folder contains its OWN jar (versions/<vid>/<vid>.jar
    - the way OptiFine standalone versions and custom/hack clients are
    distributed), that jar REPLACES the vanilla client jar and no
    vanilla jar is downloaded for it.
    """

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

    # --------------------------------------------------------
    # Which jar is the actual game jar?
    # --------------------------------------------------------
    # A version folder with its own <id>.jar (OptiFine standalone
    # versions, imported hack clients) replaces the vanilla client
    # jar entirely. Otherwise the vanilla/parent client jar is used
    # (Forge/Fabric version folders contain only the JSON).

    own_jar = os.path.join(GAME_DIR, "versions", vid, vid + ".jar")

    if os.path.isfile(own_jar):
        vj["_client_jar"] = own_jar

        report("Using custom client jar: " + vid + ".jar", 5, 100)

    else:
        d = vj.get("downloads", {}).get("client")

        if not d:
            raise RuntimeError(
                "version JSON for '" + str(vid) + "' has no client download "
                "(its parent version may be missing or corrupt)"
            )

        report("Downloading game files...", 5, 100)

        jar = os.path.join(
            GAME_DIR,
            "versions",
            vj["_vanilla_id"],
            vj["_vanilla_id"] + ".jar"
        )

        download(d["url"], jar, d.get("sha1"))

        vj["_client_jar"] = jar

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
    name = os.path.basename(path).lower()

    if not name.endswith(".jar"):
        return False

    if "optifine" in name or "preview_" in name:
        return True

    names = _jar_names(path)

    if "Config.class" in names and any(
        n in names
        for n in ("OptiFineTweaker.class", "OptiFineForgeTweaker.class")
    ):
        return True

    return False


def _is_optifine_installer(path):
    names = _jar_names(path)

    if any(n.startswith("optifine/Installer") for n in names):
        return True

    if "InstallerFrame.class" in names:
        return True

    return False


def find_optifine_jars():
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
    m = re.search(
        r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)",
        os.path.basename(path)
    )

    return m.group(1) if m else None


def install_optifine(installer_jar, version_id=None):
    """Install OptiFine into the CURRENT instance.

    - Plain OptiFine mod JAR: copied to mods/ as-is.
    - Official installer JAR: the real OptiFine mod JAR is EXTRACTED
      from it (using the installer's own 'extract' command, headless)
      and placed in mods/. If extraction fails, the installer itself
      is copied - Forge can load OptiFine installer JARs directly
      from mods/.
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

    if not _is_optifine_installer(src):
        shutil.copy2(src, out)
        log("OptiFine mod JAR copied to mods: " + out)
        return out

    work = tempfile.mkdtemp(prefix="blemm_optifine_")

    try:
        java = java_bin_for(version_id or "1.20")

        log("Extracting OptiFine mod JAR from installer...")

        r = subprocess.run(
            [java, "-jar", src, "extract"],
            cwd=work,
            capture_output=True,
            timeout=300
        )

        jars = [
            f
            for f in os.listdir(work)
            if f.lower().endswith(".jar")
        ]

        if r.returncode == 0 and jars:
            jars.sort(key=lambda f: os.path.getsize(os.path.join(work, f)))

            source = os.path.join(work, jars[-1])

            shutil.copy2(source, out)

            log("OptiFine extracted and installed: " + out)

            return out

        log(
            "OptiFine installer 'extract' step didn't produce a JAR - "
            "copying the installer into mods/ instead."
        )

    except Exception as e:
        log(
            "OptiFine extract failed (" + str(e) + ") - falling back to "
            "copying the installer JAR into mods/."
        )

    finally:
        shutil.rmtree(work, ignore_errors=True)

    shutil.copy2(src, out)

    log("OptiFine installed (as installer JAR): " + out)

    return out


def _temp_disable_optifine():
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
    """Install Forge for ANY Minecraft version using the promotions API."""

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
    this launch. When it's False, OptiFine JARs in mods/ are renamed
    to <name>.jar.disabled for the launch and ALWAYS restored after,
    even if the game crashes.
    """

    m = manifest()

    vid = resolve_version(version_id, m)

    vj = load_version_json(vid, m)

    java = java_bin_for(vid, vj.get("_java_major"))

    client_jar = vj.get("_client_jar") or os.path.join(
        GAME_DIR,
        "versions",
        vj["_vanilla_id"],
        vj["_vanilla_id"] + ".jar"
    )

    classpath, natives_dir = install_libraries(vj)

    if os.path.exists(client_jar):
        classpath.insert(0, client_jar)

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

    main_class = vj["mainClass"]

    loader_kind = _detect_loader(vj)

    # --------------------------------------------------------
    # AUTH (TLauncher-style offline "trick" to avoid demo mode)
    # --------------------------------------------------------

    player_uuid = str(
        uuid.uuid3(uuid.NAMESPACE_OID, "offline:" + username)
    )

    user_token = uuid.uuid3(
        uuid.NAMESPACE_OID, "token:" + username
    ).hex

    subs = {
        "${auth_player_name}": username,

        "${auth_uuid}": player_uuid,

        "${auth_access_token}": user_token,
        "${auth_session}": "token:" + user_token + ":" + player_uuid,

        "${auth_xuid}": "0",
        "${clientid}": "0" * 32,
        "${user_type}": "msa",
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

        "${primary_jar}": os.path.abspath(client_jar),

        "${resolution_width}": "854",
        "${resolution_height}": "480"
    }

    # --------------------------------------------------------
    # OPTIFINE (activation - installation is separate)
    # --------------------------------------------------------

    optifine_jars = find_optifine_jars() if optifine else []

    if optifine and not optifine_jars:
        log(
            "OptiFine is enabled, but no OptiFine JAR was found in "
            "mods/. Use 'Install OptiFine...' or add the JAR manually."
        )

    elif optifine_jars:
        if len(optifine_jars) > 1:
            log(
                "WARNING: multiple OptiFine JARs found in mods/ - this "
                "can crash the game. Remove all but one."
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

        if loader_kind == "fabric":
            log(
                "WARNING: Fabric does not load OptiFine as a mod. "
                "Use Forge/NeoForge for this instance if you want OptiFine."
            )

        elif loader_kind in ("forge", "neoforge"):
            log(
                "OptiFine will be loaded by "
                + ("Forge" if loader_kind == "forge" else "NeoForge")
                + " from the mods folder."
            )

        else:
            # VANILLA instance: launchwrapper boot so mods/ is honored.

            log(
                "Vanilla instance: loading OptiFine through "
                "launchwrapper (optifine.OptiFineTweaker)..."
            )

            lw_path = os.path.join(
                LIBS,
                "net",
                "minecraft",
                "launchwrapper",
                "1.12",
                "launchwrapper-1.12.jar"
            )

            report("Downloading launchwrapper for OptiFine...")
            download(LAUNCHWRAPPER_URL, lw_path)

            classpath.insert(0, os.path.abspath(lw_path))

            for jar in optifine_jars:
                classpath.append(os.path.abspath(jar))

            subs["${classpath}"] = os.pathsep.join(classpath)

            main_class = "net.minecraft.launchwrapper.Launch"

            game_args = list(game_args) + [
                "--tweakClass",
                "optifine.OptiFineTweaker"
            ]

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
        + [main_class]
        + resolve_arglist(game_args, subs)
    )

    os.makedirs(GAME_DIR, exist_ok=True)

    log(
        "Launching " + vid + " as " + username
        + " (Java " + str(vj.get("_java_major") or _required_java(vid)) + ")..."
    )

    if os.path.basename(vid) != vid:
        pass

    report("Starting Minecraft...", 99, 100)

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
