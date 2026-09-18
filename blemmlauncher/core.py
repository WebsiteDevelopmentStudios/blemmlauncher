```python
"""BlemmLauncher core - versions, Forge, OptiFine, mods, packs, Java, progress."""
import socket
socket.setdefaulttimeout(25)

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile
import glob

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
    f"{LAUNCHER_NAME}/{LAUNCHER_VERSION} (contact: local)"
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GAME_DIR = os.environ.get(
    "BLEMM_DIR",
    os.path.join(ROOT, "minecraft")
)

ASSETS = os.path.join(GAME_DIR, "assets")
LIBS = os.path.join(GAME_DIR, "libraries")
TOOLS = os.path.join(GAME_DIR, "tools")


def log(msg):
    print(f"[Blemm] {msg}")


# ============================================================
# PROGRESS REPORTING
# ============================================================

_reporter = None


def set_reporter(fn):
    global _reporter
    _reporter = fn


def report(stage, done=None, total=None):
    if _reporter:
        try:
            _reporter(stage, done, total)
        except Exception:
            pass


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

    os.makedirs(
        os.path.dirname(dest),
        exist_ok=True
    )

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
                    f"download failed: {url} -> {e}"
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
        f"{g.replace('.', '/')}/{aid}/{ver}/"
        f"{aid}-{ver}"
        f"{'-' + ext[0] if ext else ''}.jar"
    )


# ============================================================
# JAVA
# ============================================================

def _required_java(vid):
    try:
        parts = [
            int(x)
            for x in vid.split(".")
            if x.isdigit()
        ]

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


def java_bin_for(version_id, major=None):
    exe = (
        "java.exe"
        if os_name() == "windows"
        else "java"
    )

    if shutil.which(exe):
        return exe

    if major is None:
        major = _required_java(version_id)

    jdir = os.path.join(
        TOOLS,
        f"java-{major}"
    )

    jbin = os.path.join(
        jdir,
        "bin",
        exe
    )

    if not os.path.exists(jbin):
        report(
            f"Downloading Java {major} "
            "(one time, ~180 MB)..."
        )

        os.makedirs(
            TOOLS,
            exist_ok=True
        )

        zpath = os.path.join(
            TOOLS,
            f"jdk{major}.zip"
        )

        download(
            ADOPTIUM_API.format(major=major),
            zpath
        )

        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(zpath) as z:
                z.extractall(td)

            inner = os.listdir(td)[0]

            os.replace(
                os.path.join(td, inner),
                jdir
            )

        os.remove(zpath)

        if os_name() != "windows":
            import stat

            for r, _, fs in os.walk(jdir):
                for f in fs:
                    p = os.path.join(r, f)

                    st = os.stat(p)

                    os.chmod(
                        p,
                        st.st_mode | stat.S_IEXEC
                    )

    return jbin


def _mc_major(version_id):
    try:
        return int(
            version_id.split(".")[1]
        )

    except Exception:
        return 20


# ============================================================
# MANIFEST / VERSIONS
# ============================================================

def manifest():
    for attempt in (1, 2, 3):
        try:
            return fetch_json(
                MANIFEST_URL
            )

        except Exception as e:
            if attempt == 3:
                raise RuntimeError(
                    f"can't reach Mojang (attempt 3): {e}\n"
                    "check internet / firewall / proxy, then retry"
                ) from e

            log(
                f"manifest fetch failed ({e}) - retrying..."
            )


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

    if not any(
        v["id"] == version_id
        for v in m["versions"]
    ):
        if os.path.exists(
            os.path.join(
                GAME_DIR,
                "versions",
                version_id,
                version_id + ".json"
            )
        ):
            return version_id

        raise RuntimeError(
            f"Unknown version '{version_id}'."
        )

    return version_id


def load_version_json(vid, m):
    """Load a version JSON and resolve Forge-style parents."""

    path = os.path.join(
        GAME_DIR,
        "versions",
        vid,
        vid + ".json"
    )

    if not os.path.exists(path):
        vurl = next(
            v["url"]
            for v in m["versions"]
            if v["id"] == vid
        )

        report("Downloading version info...")
        download(vurl, path)

    vj = json.load(
        open(path, encoding="utf-8")
    )

    if "inheritsFrom" in vj:
        parent = load_version_json(
            vj["inheritsFrom"],
            m
        )

        vj["libraries"] = (
            vj.get("libraries", [])
            + parent.get("libraries", [])
        )

        pj = parent.get("arguments", {})
        cj = vj.get("arguments", {})

        vj["arguments"] = {
            "game": pj.get("game", [])
            + cj.get("game", []),

            "jvm": pj.get("jvm", [])
            + cj.get("jvm", [])
        }

        vj.setdefault(
            "mainClass",
            parent["mainClass"]
        )

        vj.setdefault(
            "assetIndex",
            parent.get("assetIndex")
        )

        vj.setdefault(
            "downloads",
            parent.get("downloads")
        )

        vj.setdefault(
            "logging",
            parent.get("logging")
        )

        vj["_java_major"] = (
            vj.get("javaVersion", {}).get("majorVersion")
            or parent.get("_java_major")
            or parent.get("javaVersion", {}).get("majorVersion")
        )

        vj["_vanilla_id"] = vj["inheritsFrom"]

    else:
        vj["_java_major"] = (
            vj.get("javaVersion", {}).get("majorVersion")
        )

        vj["_vanilla_id"] = vid

    report(
        "Downloading game files...",
        5,
        100
    )

    d = vj["downloads"]["client"]

    jar = os.path.join(
        GAME_DIR,
        "versions",
        vj["_vanilla_id"],
        vj["_vanilla_id"] + ".jar"
    )

    download(
        d["url"],
        jar,
        d.get("sha1")
    )

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
    natives_dir = os.path.join(
        GAME_DIR,
        "natives",
        vj.get(
            "id",
            vj["_vanilla_id"]
        )
    )

    os.makedirs(
        natives_dir,
        exist_ok=True
    )

    classpath = []
    seen = set()

    todo = [
        lib
        for lib in vj.get("libraries", [])
        if is_allowed(lib.get("rules"))
    ]

    for i, lib in enumerate(todo):
        report(
            "Downloading libraries...",
            i,
            max(len(todo), 1)
        )

        dl = lib.get("downloads", {})

        art = dl.get("artifact")

        rp = (
            art["path"]
            if art
            else maven_path(lib["name"])
        )

        if rp in seen or not rp:
            continue

        seen.add(rp)

        jar = os.path.join(
            LIBS,
            rp
        )

        url = (
            art.get("url")
            if art
            else None
        ) or (
            FORGE_MAVEN
            + "/"
            + rp
        )

        try:
            download(
                url,
                jar,
                art.get("sha1")
                if art
                else None
            )

        except Exception:
            if (
                url.startswith(LIB_BASE)
                or url.startswith(FORGE_MAVEN)
            ):
                other = (
                    LIB_BASE
                    if url.startswith(FORGE_MAVEN)
                    else FORGE_MAVEN
                )

                download(
                    other + rp,
                    jar
                )

        classpath.append(jar)

        classifier = lib.get(
            "natives",
            {}
        ).get(os_name())

        if classifier:
            nart = dl.get(
                "classifiers",
                {}
            ).get(classifier)

            if nart:
                njar = os.path.join(
                    LIBS,
                    nart["path"]
                )

                download(
                    nart["url"],
                    njar,
                    nart.get("sha1")
                )

                with zipfile.ZipFile(njar) as z:
                    for info in z.infolist():
                        n = os.path.basename(
                            info.filename
                        )

                        if (
                            info.filename.startswith("META-INF/")
                            or n.endswith(
                                (".sha1", ".sha", ".git")
                            )
                        ):
                            continue

                        if n:
                            with z.open(info) as s, open(
                                os.path.join(
                                    natives_dir,
                                    n
                                ),
                                "wb"
                            ) as o:
                                shutil.copyfileobj(
                                    s,
                                    o
                                )

    return classpath, natives_dir


def install_assets(vj):
    idx = vj.get("assetIndex")

    if not idx:
        return vj.get(
            "assets",
            "legacy"
        )

    idp = os.path.join(
        ASSETS,
        "indexes",
        idx["id"] + ".json"
    )

    download(
        idx["url"],
        idp,
        idx.get("sha1")
    )

    objects = json.load(
        open(idp, encoding="utf-8")
    ).get(
        "objects",
        {}
    )

    items = list(objects.items())
    total = max(len(items), 1)
    done = 0

    def _fetch(entry):
        name, obj = entry
        h = obj["hash"]

        try:
            download(
                RESOURCE_BASE
                + f"{h[:2]}/{h}",

                os.path.join(
                    ASSETS,
                    "objects",
                    h[:2],
                    h
                ),

                h
            )

            return None

        except Exception as e:
            return f"{name}: {e}"

    report(
        "Downloading game assets "
        "(biggest step, first time only)...",
        0,
        total
    )

    with ThreadPoolExecutor(
        max_workers=24
    ) as ex:
        futures = [
            ex.submit(_fetch, item)
            for item in items
        ]

        for fut in as_completed(futures):
            done += 1

            if done % 25 == 0 or done == total:
                report(
                    "Downloading game assets "
                    "(biggest step, first time only)...",
                    done,
                    total
                )

            err = fut.result()

            if err:
                log(f"  ! {err}")

    return idx["id"]


# ============================================================
# OPTIFINE
# ============================================================

def install_optifine(installer_jar, with_forge=True):
    """
    Install an OptiFine installer supplied by the user.

    The launcher does NOT download OptiFine itself.

    The user selects the official OptiFine installer JAR and
    BlemmLauncher extracts the actual OptiFine mod JAR into
    the instance's mods folder.

    This gives users two ways to use OptiFine:

    1. Install through the launcher.
    2. Manually place an OptiFine JAR in mods/.

    The checkbox in the GUI decides whether OptiFine is enabled.
    """

    if not installer_jar:
        raise RuntimeError(
            "No OptiFine installer was selected."
        )

    installer_jar = os.path.abspath(
        installer_jar
    )

    if not os.path.isfile(installer_jar):
        raise RuntimeError(
            f"OptiFine installer not found:\n{installer_jar}"
        )

    if not zipfile.is_zipfile(installer_jar):
        raise RuntimeError(
            "The selected OptiFine file is not a valid JAR."
        )

    mods_dir = os.path.join(
        GAME_DIR,
        "mods"
    )

    os.makedirs(
        mods_dir,
        exist_ok=True
    )

    base = os.path.basename(
        installer_jar
    )

    output_name = base.replace(
        "_installer",
        ""
    )

    if not output_name.lower().endswith(".jar"):
        output_name += ".jar"

    out = os.path.join(
        mods_dir,
        output_name
    )

    # If the selected installer itself is already a normal mod JAR,
    # simply copy it into mods.
    if "optifine" in base.lower() and "_installer" not in base.lower():
        shutil.copy2(
            installer_jar,
            out
        )

        log(
            f"OptiFine copied to mods: {out}"
        )

        return out

    work = tempfile.mkdtemp(
        prefix="blemm_optifine_"
    )

    try:
        java = (
            shutil.which("java")
            or java_bin_for("1.20")
        )

        log(
            f"Installing OptiFine from: {base}"
        )

        r = subprocess.run(
            [
                java,
                "-jar",
                installer_jar,
                "extract"
            ],
            cwd=work,
            capture_output=True
        )

        jars = [
            f
            for f in os.listdir(work)
            if f.lower().endswith(".jar")
        ]

        if r.returncode != 0 or not jars:
            outp = (
                (r.stdout or b"")
                + (r.stderr or b"")
            ).decode(
                errors="replace"
            )

            raise RuntimeError(
                "OptiFine installation failed.\n"
                "Make sure you selected the official "
                "OptiFine installer JAR.\n\n"
                "--- output ---\n"
                + outp[-1200:]
            )

        source = os.path.join(
            work,
            jars[0]
        )

        shutil.copy2(
            source,
            out
        )

        log(
            f"OptiFine installed: {out}"
        )

        return out

    finally:
        shutil.rmtree(
            work,
            ignore_errors=True
        )


def find_optifine_jars():
    """
    Find manually installed OptiFine JARs in the instance's mods folder.
    """

    mods_dir = os.path.join(
        GAME_DIR,
        "mods"
    )

    if not os.path.isdir(mods_dir):
        return []

    found = []

    for filename in os.listdir(mods_dir):
        if not filename.lower().endswith(".jar"):
            continue

        if "optifine" in filename.lower():
            found.append(
                os.path.join(
                    mods_dir,
                    filename
                )
            )

    return found


# ============================================================
# FORGE
# ============================================================

def ensure_launcher_profile(game_dir):
    lp = os.path.join(
        game_dir,
        "launcher_profiles.json"
    )

    if not os.path.exists(lp):
        os.makedirs(
            game_dir,
            exist_ok=True
        )

        with open(
            lp,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "profiles": {},
                    "settings": {},
                    "version": 3
                },
                f
            )


def _forge_locally_processed(vj):
    for lib in vj.get(
        "libraries",
        []
    ):
        if not lib.get(
            "name",
            ""
        ).startswith(
            "net.minecraftforge:forge:"
        ):
            continue

        art = lib.get(
            "downloads",
            {}
        ).get("artifact")

        if art and not os.path.exists(
            os.path.join(
                LIBS,
                art["path"]
            )
        ):
            return False

    return True


def install_forge(mc_version, build=None):
    if build in (
        None,
        "auto",
        "",
        "recommended",
        "latest"
    ):
        try:
            promos = fetch_json(
                FORGE_PROMOS
            )["promos"]

            build = (
                promos.get(
                    f"{mc_version}-recommended"
                )
                or promos.get(
                    f"{mc_version}-latest"
                )
            )

        except Exception:
            build = None

        if not build:
            raise RuntimeError(
                f"No Forge build found for {mc_version}"
            )

    vid = (
        f"{mc_version}-forge-{build}"
    )

    existing = os.path.join(
        GAME_DIR,
        "versions",
        vid,
        vid + ".json"
    )

    if os.path.exists(existing):
        try:
            if _forge_locally_processed(
                json.load(
                    open(
                        existing,
                        encoding="utf-8"
                    )
                )
            ):
                log(
                    f"Forge {vid} already installed."
                )

                return vid

        except Exception:
            pass

        log(
            f"Forge {vid} install looks incomplete - reinstalling..."
        )

        shutil.rmtree(
            os.path.dirname(existing),
            ignore_errors=True
        )

    m = manifest()

    load_version_json(
        resolve_version(
            mc_version,
            m
        ),
        m
    )

    os.makedirs(
        TOOLS,
        exist_ok=True
    )

    installer = os.path.join(
        TOOLS,
        f"forge-{vid}-installer.jar"
    )

    ilurl = (
        f"{FORGE_MAVEN}/net/minecraftforge/forge/"
        f"{mc_version}-{build}/"
        f"forge-{mc_version}-{build}-installer.jar"
    )

    report(
        "Downloading Forge installer..."
    )

    download(
        ilurl,
        installer
    )

    report(
        "Installing Forge (running official installer)..."
    )

    ensure_launcher_profile(
        GAME_DIR
    )

    java = (
        shutil.which("java")
        or java_bin_for(mc_version)
    )

    r = subprocess.run(
        [
            java,
            "-jar",
            installer,
            "--installClient"
        ],
        cwd=GAME_DIR,
        capture_output=True
    )

    outp = (
        (r.stdout or b"")
        + (r.stderr or b"")
    ).decode(
        errors="replace"
    )

    matches = [
        p
        for p in glob.glob(
            os.path.join(
                GAME_DIR,
                "versions",
                f"{mc_version}*forge*"
            )
        )
        if os.path.exists(
            os.path.join(
                p,
                os.path.basename(p) + ".json"
            )
        )
    ]

    matches.sort(
        key=os.path.getmtime,
        reverse=True
    )

    if r.returncode != 0 or not matches:
        raise RuntimeError(
            "Forge install failed "
            f"(installer exit code {r.returncode}).\n"
            "--- installer output ---\n"
            f"{outp[-1500:]}"
        )

    found = os.path.basename(
        matches[0]
    )

    vj_check = json.load(
        open(
            os.path.join(
                matches[0],
                found + ".json"
            ),
            encoding="utf-8"
        )
    )

    if not _forge_locally_processed(
        vj_check
    ):
        raise RuntimeError(
            "Forge installer exited OK but its "
            "processors step didn't finish "
            "(the local client/server jars are missing).\n"
            f"--- installer output ---\n{outp[-1500:]}"
        )

    log(
        f"Forge installed: {found}"
    )

    return found


# ============================================================
# CONTENT: MODS / PACKS / SHADERS
# ============================================================

def detect_kind(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = set(
                z.namelist()
            )

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
        if any(
            n.startswith("shaders/")
            for n in names
        ):
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
                or (
                    "mod"
                    if p.lower().endswith(".jar")
                    else "resourcepack"
                )
            )
        )

        dest_dir = os.path.join(
            GAME_DIR,
            folders[use_kind]
        )

        os.makedirs(
            dest_dir,
            exist_ok=True
        )

        shutil.copy2(
            p,
            os.path.join(
                dest_dir,
                os.path.basename(p)
            )
        )

        installed.append(
            f"{use_kind}: {os.path.basename(p)}"
        )

        if use_kind == "resourcepack":
            enable_resourcepack(
                os.path.basename(p)
            )

    log(
        f"Imported {len(installed)} file(s): "
        + ", ".join(installed)
    )

    return installed


def enable_resourcepack(filename):
    opts_path = os.path.join(
        GAME_DIR,
        "options.txt"
    )

    entry = (
        f'resourcePacks:["file/{filename}"]'
    )

    lines = []

    if os.path.exists(opts_path):
        lines = open(
            opts_path,
            encoding="utf-8"
        ).read().splitlines()

    lines = [
        l
        for l in lines
        if not l.startswith(
            "resourcePacks:"
        )
    ]

    lines.append(entry)

    open(
        opts_path,
        "w",
        encoding="utf-8"
    ).write(
        "\n".join(lines)
        + "\n"
    )


# ============================================================
# INSTANCE SUPPORT
# ============================================================

def set_game_dir(path):
    global GAME_DIR, ASSETS, LIBS, TOOLS

    GAME_DIR = path

    ASSETS = os.path.join(
        GAME_DIR,
        "assets"
    )

    LIBS = os.path.join(
        GAME_DIR,
        "libraries"
    )

    TOOLS = os.path.join(
        GAME_DIR,
        "tools"
    )


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
            rules = None

        else:
            rules = a.get("rules")

            if not is_allowed(rules):
                continue

            v = a["value"]

            values = (
                v
                if isinstance(v, list)
                else [v]
            )

        for value in values:
            value = subst(
                value,
                subs
            )

            if (
                value == "-XstartOnFirstThread"
                and platform.system() != "Darwin"
            ):
                continue

            if value in quick_play_options:
                continue

            out.append(value)

    return out


def launch(
    version_id,
    username="Blemm",
    ram="2G",
    optifine=False
):
    m = manifest()

    vid = resolve_version(
        version_id,
        m
    )

    vj = load_version_json(
        vid,
        m
    )

    java = java_bin_for(
        vid,
        vj.get("_java_major")
    )

    vanilla_jar = os.path.join(
        GAME_DIR,
        "versions",
        vj["_vanilla_id"],
        vj["_vanilla_id"] + ".jar"
    )

    classpath, natives_dir = install_libraries(
        vj
    )

    classpath.insert(
        0,
        vanilla_jar
    )

    asset_id = install_assets(
        vj
    )

    game_args = (
        vj.get("arguments", {}).get("game")
        or vj["minecraftArguments"].split()
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

    forge_active = (
        "-forge-" in vid.lower()
        or "neoforge" in vid.lower()
    )

    # --------------------------------------------------------
    # OPTIFINE
    # --------------------------------------------------------

    if optifine:
        optifine_jars = find_optifine_jars()

        if optifine_jars:
            log(
                "OptiFine enabled - using OptiFine "
                "JAR(s) from the instance mods folder."
            )

            for jar in optifine_jars:
                log(
                    f"OptiFine: {os.path.basename(jar)}"
                )

        else:
            log(
                "OptiFine is enabled, but no OptiFine JAR "
                "was found in mods/."
            )

            if not forge_active:
                log(
                    "Note: OptiFine is intended to be used "
                    "with a compatible mod loader."
                )

    else:
        log(
            "OptiFine checkbox is OFF."
        )

    subs = {
        "${auth_player_name}": username,

        "${auth_uuid}": str(
            uuid.uuid3(
                uuid.NAMESPACE_OID,
                "offline:" + username
            )
        ),

        "${auth_access_token}": "0",
        "${auth_session}": "0",
        "${user_type}": "legacy",
        "${user_properties}": "{}",

        "${version_name}": vid,
        "${version_type}": LAUNCHER_NAME,

        "${game_directory}": os.path.abspath(
            GAME_DIR
        ),

        "${assets_root}": os.path.abspath(
            ASSETS
        ),

        "${assets_index_name}": asset_id,

        "${game_assets}": os.path.join(
            ASSETS,
            "virtual",
            asset_id
        ),

        "${natives_directory}": os.path.abspath(
            natives_dir
        ),

        "${launcher_name}": LAUNCHER_NAME,
        "${launcher_version}": LAUNCHER_VERSION,

        "${classpath}": os.pathsep.join(
            classpath
        ),

        "${classpath_separator}": os.pathsep,

        "${library_directory}": os.path.abspath(
            LIBS
        ),

        "${primary_jar}": os.path.abspath(
            vanilla_jar
        ),

        "${clientid}": "0" * 32,
        "${auth_xuid}": "0",

        "${resolution_width}": "854",
        "${resolution_height}": "480"
    }

    cmd = [
        java,
        "-Xms512M",
        f"-Xmx{ram}"
    ]

    log_cfg = vj.get(
        "logging",
        {}
    ).get(
        "client",
        {}
    )

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
            "-Dlog4j.configurationFile="
            + os.path.abspath(lf)
        )

    cmd += (
        resolve_arglist(
            jvm_args,
            subs
        )
        + [vj["mainClass"]]
        + resolve_arglist(
            game_args,
            subs
        )
    )

    os.makedirs(
        GAME_DIR,
        exist_ok=True
    )

    log(
        f"Launching {vid} as {username} "
        f"(Java {vj.get('_java_major') or _required_java(vid)})..."
    )

    report(
        "Starting Minecraft...",
        99,
        100
    )

    result = subprocess.run(
        cmd,
        cwd=GAME_DIR,
        capture_output=True
    )

    report(
        "Minecraft closed.",
        100,
        100
    )

    if result.returncode != 0:
        out = (
            (result.stdout or b"")
            + (result.stderr or b"")
        )

        tail = (
            out.decode(
                errors="replace"
            )
            .strip()[-1200:]
        )

        raise RuntimeError(
            "Minecraft crashed instantly "
            f"(exit code {result.returncode}).\n"
            "--- last output ---\n"
            f"{tail}\n"
            "-------------------\n"
            "If this mentions "
            "'UnsupportedClassVersionError', "
            "the Java version is wrong for this Minecraft."
        )
```

### `gui.py`

```python
import os
import threading
import queue

import tkinter as tk
from tkinter import (
    ttk,
    filedialog,
    scrolledtext,
    messagebox
)

from . import core, instances


BG = "#1e1f24"
PANEL = "#272930"
FIELD = "#2f323b"

FG = "#e8e9ee"
MUTED = "#8b8fa3"
ACCENT = "#4ade80"
DANGER = "#f87171"


def style_dark(root):
    ttk.Style().theme_use("clam")

    s = ttk.Style()

    s.configure(
        ".",
        background=BG,
        foreground=FG,
        fieldbackground=FIELD,
        bordercolor=PANEL,
        lightcolor=PANEL,
        darkcolor=PANEL,
        troughcolor=FIELD,
        arrowcolor=MUTED
    )

    for n, bg in [
        ("TFrame", BG),
        ("Card.TFrame", PANEL)
    ]:
        s.configure(
            n,
            background=bg
        )

    s.configure(
        "TLabel",
        background=BG,
        foreground=FG
    )

    s.configure(
        "Muted.TLabel",
        background=BG,
        foreground=MUTED
    )

    s.configure(
        "MutedP.TLabel",
        background=PANEL,
        foreground=MUTED
    )

    s.configure(
        "Title.TLabel",
        background=BG,
        foreground=ACCENT,
        font=("Segoe UI", 18, "bold")
    )

    s.configure(
        "TEntry",
        foreground=FG,
        insertcolor=FG,
        padding=4
    )

    s.configure(
        "TCombobox",
        foreground=FG,
        padding=4
    )

    s.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", FIELD)
        ]
    )

    s.configure(
        "Inst.TButton",
        background=FIELD,
        foreground=FG,
        padding=6,
        width=13
    )

    s.map(
        "Inst.TButton",
        background=[
            ("active", "#3a3e49")
        ]
    )

    s.configure(
        "Play.TButton",
        background=ACCENT,
        foreground="#10240f",
        font=("Segoe UI", 12, "bold"),
        padding=(30, 10)
    )

    s.map(
        "Play.TButton",
        background=[
            ("active", "#6ce89a"),
            ("disabled", "#39543f")
        ]
    )

    s.configure(
        "TButton",
        background=FIELD,
        foreground=FG,
        padding=6
    )

    s.map(
        "TButton",
        background=[
            ("active", "#3a3e49")
        ]
    )

    s.configure(
        "TCheckbutton",
        background=PANEL,
        foreground=FG
    )

    s.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=FIELD,
        thickness=10
    )

    root.configure(
        bg=BG
    )


class App:

    def __init__(self, root):
        self.root = root

        root.title(
            "BlemmLauncher"
        )

        root.geometry(
            "860x600"
        )

        root.minsize(
            760,
            540
        )

        style_dark(root)

        self.q = queue.Queue()
        self.sel = None
        self.version_map = {}

        self._optifine = tk.BooleanVar(
            value=False
        )

        head = ttk.Frame(root)

        head.pack(
            fill="x",
            padx=14,
            pady=(10, 2)
        )

        ttk.Label(
            head,
            text="◈ BlemmLauncher",
            style="Title.TLabel"
        ).pack(
            side="left"
        )

        ttk.Label(
            head,
            text="instances · loaders · modrinth · import/export",
            style="Muted.TLabel"
        ).pack(
            side="left",
            padx=10,
            pady=(10, 0)
        )

        body = ttk.Frame(root)

        body.pack(
            fill="both",
            expand=True,
            padx=14,
            pady=8
        )

        body.columnconfigure(
            1,
            weight=1
        )

        body.rowconfigure(
            0,
            weight=1
        )

        # ====================================================
        # LEFT
        # ====================================================

        left = ttk.Frame(
            body,
            style="Card.TFrame",
            padding=8
        )

        left.grid(
            row=0,
            column=0,
            sticky="ns",
            padx=(0, 10)
        )

        self.ilist = tk.Listbox(
            left,
            width=26,
            bg=FIELD,
            fg=FG,
            relief="flat",
            highlightthickness=0,
            selectbackground=ACCENT,
            selectforeground="#10240f",
            font=("Segoe UI", 11)
        )

        self.ilist.pack(
            fill="y"
        )

        self.ilist.bind(
            "<<ListboxSelect>>",
            self._sel_ev
        )

        bb = ttk.Frame(
            left,
            style="Card.TFrame"
        )

        bb.pack(
            fill="x",
            pady=(8, 0)
        )

        buttons = [
            ("＋ New", self.new_inst),
            ("⭳ Import", self.import_inst),
            ("⭱ Export", self.export_inst),
            ("✂ Shortcut", self.make_shortcut),
            ("🗑 Delete", self.del_inst)
        ]

        for i, (t, c) in enumerate(buttons):
            ttk.Button(
                bb,
                text=t,
                style="Inst.TButton",
                command=c
            ).grid(
                row=i // 2,
                column=i % 2,
                sticky="we",
                pady=2,
                padx=2
            )

        bb.columnconfigure(
            0,
            weight=1
        )

        bb.columnconfigure(
            1,
            weight=1
        )

        # ====================================================
        # RIGHT
        # ====================================================

        right = ttk.Frame(
            body,
            style="Card.TFrame",
            padding=16
        )

        right.grid(
            row=0,
            column=1,
            sticky="nsew"
        )

        right.columnconfigure(
            1,
            weight=1
        )

        self.i_title = ttk.Label(
            right,
            text="pick or create an instance →",
            style="Title.TLabel"
        )

        self.i_title.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6)
        )

        self.i_info = ttk.Label(
            right,
            text="",
            style="MutedP.TLabel",
            justify="left",
            anchor="w"
        )

        self.i_info.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8)
        )

        settings = ttk.Frame(
            right,
            style="Card.TFrame"
        )

        settings.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w"
        )

        ttk.Label(
            settings,
            text="Username:",
            style="MutedP.TLabel"
        ).pack(
            side="left"
        )

        self._uname = tk.StringVar(
            value="Blemm"
        )

        ttk.Entry(
            settings,
            textvariable=self._uname,
            width=16
        ).pack(
            side="left",
            padx=(6, 14)
        )

        ttk.Label(
            settings,
            text="RAM:",
            style="MutedP.TLabel"
        ).pack(
            side="left"
        )

        self._ram = tk.StringVar(
            value="4G"
        )

        ttk.Combobox(
            settings,
            textvariable=self._ram,
            values=[
                "2G",
                "4G",
                "6G",
                "8G"
            ],
            width=6,
            state="readonly"
        ).pack(
            side="left",
            padx=6
        )

        # ====================================================
        # OPTIFINE CHECKBOX
        # ====================================================

        self.optifine_check = ttk.Checkbutton(
            settings,
            text="OptiFine",
            variable=self._optifine,
            command=self._save_optifine_setting
        )

        self.optifine_check.pack(
            side="left",
            padx=(14, 0)
        )

        # ====================================================
        # PLAY
        # ====================================================

        self.play_btn = ttk.Button(
            right,
            text="▶   PLAY",
            style="Play.TButton",
            command=self.play,
            state="disabled"
        )

        self.play_btn.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="we",
            pady=(12, 6)
        )

        # ====================================================
        # OPTIFINE INSTALL BUTTON
        # ====================================================

        ttk.Button(
            right,
            text="⚙ Install OptiFine from JAR…",
            command=self.install_optifine
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6)
        )

        ttk.Label(
            right,
            text="You can also manually place an OptiFine JAR in mods/.",
            style="MutedP.TLabel"
        ).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6)
        )

        ttk.Button(
            right,
            text="🔎 Browse & install (Modrinth) — mods / shaders / packs",
            command=self.browse_mods
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="w"
        )

        ttk.Button(
            right,
            text="＋ add files… (Ctrl+click several: mods, packs, shaders)",
            command=self.add_file
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0)
        )

        # ====================================================
        # STATUS
        # ====================================================

        self.status = ttk.Label(
            root,
            text="Loading version list…",
            anchor="w"
        )

        self.status.pack(
            fill="x",
            padx=14
        )

        self.bar = ttk.Progressbar(
            root,
            mode="indeterminate"
        )

        self.bar.pack(
            fill="x",
            padx=14,
            pady=(2, 6)
        )

        logcard = ttk.Frame(
            root,
            style="Card.TFrame",
            padding=6
        )

        logcard.pack(
            fill="both",
            expand=True,
            padx=14,
            pady=(0, 10)
        )

        self.log = scrolledtext.ScrolledText(
            logcard,
            height=6,
            state="disabled",
            font=("Consolas", 9),
            bg=FIELD,
            fg=FG,
            insertbackground=FG,
            relief="flat"
        )

        self.log.pack(
            fill="both",
            expand=True
        )

        self.root.after(
            100,
            self._drain
        )

        threading.Thread(
            target=self._load_versions,
            daemon=True
        ).start()

        self._refresh_list()

    # ========================================================
    # VERSION LIST
    # ========================================================

    def _load_versions(self):
        try:
            versions, latest, _ = core.list_versions()

            def sk(v):
                try:
                    return [
                        int(x)
                        for x in v.split(".")
                        if x.isdigit()
                    ]

                except Exception:
                    return [-1]

            chosen = sorted(
                [
                    v
                    for v in versions
                    if sk(v) >= [1, 12, 2]
                    and "-" not in v
                    and not v.startswith(
                        ("w", "pre", "rc")
                    )
                ],
                key=sk,
                reverse=True
            )

            self.q.put(
                ("versions", chosen)
            )

        except Exception as e:
            self.q.put(
                (
                    "error",
                    f"version list failed: {e}"
                )
            )

    # ========================================================
    # INSTANCE LIST
    # ========================================================

    def _refresh_list(self):
        self.ilist.delete(
            0,
            "end"
        )

        for n in instances.list_instances():
            self.ilist.insert(
                "end",
                n
            )

        self.sel = None

        self._optifine.set(
            False
        )

        self.play_btn.config(
            state="disabled"
        )

    def _sel_ev(self, _=None):
        sel = self.ilist.curselection()

        if not sel:
            return

        name = self.ilist.get(
            sel[0]
        )

        cfg = instances.load_cfg(
            name
        )

        self.sel = name

        self.version = cfg["version"]
        self.loader = cfg.get("loader")

        self._uname.set(
            cfg.get(
                "username",
                "Blemm"
            )
        )

        self._ram.set(
            cfg.get(
                "ram",
                "4G"
            )
        )

        self._optifine.set(
            bool(
                cfg.get(
                    "optifine",
                    False
                )
            )
        )

        self.i_title.config(
            text=name
        )

        self.i_info.config(
            text=(
                f"version: {cfg['version']}    "
                f"loader: {cfg.get('loader') or 'vanilla'}\n"
                f"ram: {cfg.get('ram')}    "
                f"mods: {self._count_mods(name)}"
            )
        )

        self.play_btn.config(
            state="normal"
        )

    def _count_mods(self, name):
        d = os.path.join(
            instances.instance_dir(name),
            "mods"
        )

        return (
            len(os.listdir(d))
            if os.path.isdir(d)
            else 0
        )

    # ========================================================
    # OPTIFINE SETTING
    # ========================================================

    def _save_optifine_setting(self):
        if not self.sel:
            return

        try:
            cfg = instances.load_cfg(
                self.sel
            )

            cfg["optifine"] = bool(
                self._optifine.get()
            )

            instances.save_cfg(
                self.sel,
                cfg
            )

        except Exception as e:
            self.log_message(
                f"Could not save OptiFine setting: {e}"
            )

    # ========================================================
    # OPTIFINE INSTALLER
    # ========================================================

    def install_optifine(self):
        if not self.sel:
            messagebox.showinfo(
                "BlemmLauncher",
                "Select an instance first."
            )
            return

        p = filedialog.askopenfilename(
            title="Select OptiFine installer JAR",
            filetypes=[
                (
                    "OptiFine JAR",
                    "*.jar"
                ),
                (
                    "All files",
                    "*.*"
                )
            ]
        )

        if not p:
            return

        try:
            core.set_game_dir(
                instances.instance_dir(
                    self.sel
                )
            )

            installed = core.install_optifine(
                p,
                with_forge=True
            )

            self._optifine.set(
                True
            )

            self._save_optifine_setting()

            self._sel_ev()

            self.status.config(
                text=(
                    "OptiFine installed: "
                    + os.path.basename(installed)
                ),
                foreground=ACCENT
            )

            self.log_message(
                "OptiFine installed successfully."
            )

        except Exception as e:
            messagebox.showerror(
                "OptiFine installation failed",
                str(e)
            )

    # ========================================================
    # CREATE
    # ========================================================

    def new_inst(self):
        d = tk.Toplevel(
            self.root
        )

        d.title(
            "New instance"
        )

        d.configure(
            bg=BG
        )

        d.geometry(
            "380x260"
        )

        style_dark(d)

        f = ttk.Frame(
            d,
            style="Card.TFrame",
            padding=14
        )

        f.pack(
            fill="both",
            expand=True
        )

        name = tk.StringVar()
        version = tk.StringVar(
            value="release"
        )
        loader = tk.StringVar(
            value="vanilla"
        )
        ram = tk.StringVar(
            value="4G"
        )
        uname = tk.StringVar(
            value="Blemm"
        )

        rows = [
            (
                "Name:",
                ttk.Entry(
                    f,
                    textvariable=name
                )
            ),
            (
                "Version:",
                ttk.Combobox(
                    f,
                    textvariable=version,
                    values=["release"]
                )
            ),
            (
                "Loader:",
                ttk.Combobox(
                    f,
                    textvariable=loader,
                    state="readonly",
                    values=[
                        "vanilla",
                        "forge",
                        "fabric",
                        "neoforge"
                    ]
                )
            ),
            (
                "RAM:",
                ttk.Combobox(
                    f,
                    textvariable=ram,
                    state="readonly",
                    values=[
                        "2G",
                        "4G",
                        "6G",
                        "8G"
                    ]
                )
            ),
            (
                "Username:",
                ttk.Entry(
                    f,
                    textvariable=uname
                )
            )
        ]

        for r, (label, widget) in enumerate(rows):
            ttk.Label(
                f,
                text=label,
                style="MutedP.TLabel"
            ).grid(
                row=r,
                column=0,
                sticky="w",
                pady=3
            )

            widget.grid(
                row=r,
                column=1,
                sticky="we",
                pady=3,
                padx=(8, 0)
            )

        f.columnconfigure(
            1,
            weight=1
        )

        def fill_versions():
            try:
                versions, _, _ = core.list_versions()

                def sk(v):
                    try:
                        return [
                            int(x)
                            for x in v.split(".")
                            if x.isdigit()
                        ]

                    except Exception:
                        return [-1]

                chosen = sorted(
                    [
                        v
                        for v in versions
                        if sk(v) >= [1, 12, 2]
                        and "-" not in v
                        and not v.startswith(
                            ("w", "pre", "rc")
                        )
                    ],
                    key=sk,
                    reverse=True
                )

                widget = f.grid_slaves(
                    row=1,
                    column=1
                )[0]

                widget.config(
                    values=[
                        "release"
                    ] + chosen[:60]
                )

            except Exception:
                pass

        threading.Thread(
            target=fill_versions,
            daemon=True
        ).start()

        def go():
            nm = (
                name.get().strip()
                or "New Instance"
            )

            v = version.get()

            if v == "release":
                try:
                    v = core.manifest()[
                        "latest"
                    ]["release"]

                except Exception:
                    messagebox.showerror(
                        "Blemm",
                        "couldn't resolve 'release' - "
                        "type a specific version",
                        parent=d
                    )

                    return

            ld = loader.get()

            ld = (
                None
                if ld == "vanilla"
                else ld
            )

            try:
                instances.create(
                    nm,
                    v,
                    ld,
                    ram.get(),
                    uname.get()
                )

                d.destroy()

                self._refresh_list()

            except Exception as e:
                messagebox.showerror(
                    "Blemm",
                    str(e),
                    parent=d
                )

        ttk.Button(
            f,
            text="Create",
            style="Play.TButton",
            command=go
        ).grid(
            row=len(rows),
            column=0,
            columnspan=2,
            sticky="we",
            pady=(10, 0)
        )

    # ========================================================
    # DELETE / IO
    # ========================================================

    def del_inst(self):
        if not self.sel:
            return

        if messagebox.askyesno(
            "Blemm",
            f"Delete instance '{self.sel}'?\n"
            "(saves are deleted too!)"
        ):
            instances.delete(
                self.sel
            )

            self._refresh_list()

    def export_inst(self):
        if not self.sel:
            return

        p = filedialog.asksaveasfilename(
            defaultextension=".zip",
            initialfile=f"{self.sel}.zip"
        )

        if p:
            try:
                instances.export(
                    self.sel,
                    p
                )

                self.status.config(
                    text=f"exported → {p}",
                    foreground=ACCENT
                )

            except Exception as e:
                messagebox.showerror(
                    "Blemm",
                    str(e)
                )

    def import_inst(self):
        p = filedialog.askopenfilename(
            filetypes=[
                (
                    "Instance zip",
                    "*.zip"
                )
            ]
        )

        if not p:
            return

        try:
            n = instances.import_from_zip(
                p
            )

            self._refresh_list()

            self.status.config(
                text=f"imported {n}",
                foreground=ACCENT
            )

        except Exception as e:
            messagebox.showerror(
                "Blemm",
                str(e)
            )

    def make_shortcut(self):
        if not self.sel:
            return

        try:
            p = instances.shortcut(
                self.sel
            )

            self.status.config(
                text=f"shortcut → {p}",
                foreground=ACCENT
            )

        except Exception as e:
            messagebox.showerror(
                "Blemm",
                str(e)
            )

    # ========================================================
    # ADD FILE
    # ========================================================

    def add_file(self):
        if not self.sel:
            return

        paths = filedialog.askopenfilenames(
            title="Pick mods / packs (Ctrl+click for several)",
            filetypes=[
                (
                    "Minecraft files",
                    "*.jar *.zip"
                ),
                (
                    "All files",
                    "*.*"
                )
            ]
        )

        if paths:
            core.set_game_dir(
                instances.instance_dir(
                    self.sel
                )
            )

            try:
                added = core.add_content_auto(
                    paths
                )

                self.status.config(
                    text=", ".join(added),
                    foreground=ACCENT
                )

                self._sel_ev()

            except Exception as e:
                messagebox.showerror(
                    "Blemm",
                    str(e)
                )

    # ========================================================
    # MODRINTH
    # ========================================================

    def browse_mods(self):
        if not self.sel:
            return

        d = tk.Toplevel(
            self.root
        )

        d.title(
            f"Modrinth — {self.sel}"
        )

        d.configure(
            bg=BG
        )

        style_dark(d)

        d.geometry(
            "600x460"
        )

        f = ttk.Frame(
            d,
            style="Card.TFrame",
            padding=10
        )

        f.pack(
            fill="both",
            expand=True
        )

        top = ttk.Frame(
            f,
            style="Card.TFrame"
        )

        top.pack(
            fill="x"
        )

        q = tk.StringVar()

        ttk.Entry(
            top,
            textvariable=q
        ).pack(
            side="left",
            fill="x",
            expand=True
        )

        ptype = tk.StringVar(
            value="mod"
        )

        ttk.Combobox(
            top,
            textvariable=ptype,
            width=12,
            state="readonly",
            values=[
                "mod",
                "shader",
                "resourcepack"
            ]
        ).pack(
            side="left",
            padx=6
        )

        results = tk.Listbox(
            f,
            bg=FIELD,
            fg=FG,
            relief="flat",
            highlightthickness=0,
            selectbackground=ACCENT,
            selectforeground="#10240f",
            selectmode="extended",
            exportselection=False
        )

        results.pack(
            fill="both",
            expand=True,
            pady=8
        )

        mid = ttk.Frame(
            f,
            style="Card.TFrame"
        )

        mid.pack(
            fill="x"
        )

        lbl = ttk.Label(
            f,
            text=(
                "type a name, Search, Ctrl/Shift+click "
                "to multi-select, Install"
            ),
            style="MutedP.TLabel"
        )

        def search():
            try:
                ld = (
                    self.loader
                    if (
                        self.loader
                        and ptype.get() == "mod"
                    )
                    else None
                )

                hits = instances.modrinth_search(
                    q.get(),
                    self.version,
                    ld,
                    ptype.get()
                )

                results.delete(
                    0,
                    "end"
                )

                for h in hits:
                    results.insert(
                        "end",
                        f'{h["title"]} — '
                        f'{h["author"]} '
                        f'({h["downs"]}↓)'
                    )

                lbl.config(
                    text=(
                        f"{len(hits)} results for "
                        f"{self.version} / "
                        f"{ptype.get()}"
                    )
                    + (
                        f" / {ld}"
                        if ld
                        else ""
                    ),
                    foreground=FG
                )

                d._hits = hits

            except Exception as e:
                lbl.config(
                    text=f"search failed: {e}"
                )

        def install():
            sel = results.curselection()

            if not sel:
                return

            hits = getattr(
                d,
                "_hits",
                []
            )

            ok = []
            errs = []

            for i in sel:
                h = hits[i]

                try:
                    ld = (
                        self.loader
                        if (
                            self.loader
                            and ptype.get() == "mod"
                        )
                        else None
                    )

                    fn = instances.modrinth_install(
                        h["id"],
                        self.version,
                        ld,
                        ptype.get()
                    )

                    ok.append(fn)

                except Exception as e:
                    errs.append(
                        f'{h["title"]}: {e}'
                    )

            msg = (
                f"installed {len(ok)}: "
                + ", ".join(ok)
                if ok
                else ""
            )

            if errs:
                msg += (
                    "\nfailed: "
                    + "; ".join(errs)
                )

            lbl.config(
                text=msg,
                foreground=(
                    ACCENT
                    if ok and not errs
                    else DANGER
                )
            )

            self._sel_ev()

        ttk.Button(
            top,
            text="Search",
            command=search
        ).pack(
            side="left",
            padx=6
        )

        ttk.Button(
            mid,
            text="⬇  Install selected",
            style="Play.TButton",
            command=install
        ).pack(
            side="left"
        )

        lbl.pack(
            anchor="w",
            pady=(6, 0)
        )

    # ========================================================
    # PLAY
    # ========================================================

    def play(self):
        if not self.sel:
            return

        self.play_btn.config(
            state="disabled",
            text="Working…"
        )

        self.bar.config(
            mode="indeterminate"
        )

        self.bar.start(
            20
        )

        self.status.config(
            text="Preparing…",
            foreground=FG
        )

        core.set_reporter(
            lambda t, dn=None, tt=None:
                self.q.put(
                    ("stage", t, dn, tt)
                )
        )

        name = self.sel

        def worker():
            try:
                cfg = instances.load_cfg(
                    name
                )

                instances.use(
                    name,
                    core
                )

                self.q.put(
                    (
                        "stage",
                        "Preparing instance…",
                        None,
                        None
                    )
                )

                # Save the current settings.
                cfg["username"] = (
                    self._uname.get()
                    or "Blemm"
                )

                cfg["ram"] = (
                    self._ram.get()
                    or "4G"
                )

                cfg["optifine"] = bool(
                    self._optifine.get()
                )

                instances.save_cfg(
                    name,
                    cfg
                )

                vid = cfg["version"]
                ld = cfg.get("loader")

                if ld == "forge":
                    vid = core.install_forge(
                        vid,
                        cfg.get(
                            "loader_build"
                        )
                    )

                elif ld == "neoforge":
                    b = instances.install_neoforge(
                        vid,
                        cfg.get(
                            "loader_build"
                        )
                    )

                    cfg["loader_build"] = b

                    instances.save_cfg(
                        name,
                        cfg
                    )

                elif ld == "fabric":
                    b = instances.install_fabric(
                        vid
                    )

                    cfg.setdefault(
                        "loader_build",
                        b
                    )

                    instances.save_cfg(
                        name,
                        cfg
                    )

                self.q.put(
                    (
                        "msg",
                        f"launching {name}: {vid}"
                    )
                )

                core.launch(
                    vid,
                    cfg.get(
                        "username",
                        "Blemm"
                    ),
                    cfg.get(
                        "ram",
                        "4G"
                    ),
                    optifine=bool(
                        cfg.get(
                            "optifine",
                            False
                        )
                    )
                )

                core.set_reporter(
                    None
                )

                self.q.put(
                    (
                        "done",
                        f"played {name} ♥"
                    )
                )

            except SystemExit as e:
                core.set_reporter(
                    None
                )

                self.q.put(
                    (
                        "error",
                        f"aborted: {e}"
                    )
                )

            except Exception as e:
                core.set_reporter(
                    None
                )

                self.q.put(
                    (
                        "error",
                        str(e)
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    # ========================================================
    # LOG HELPER
    # ========================================================

    def log_message(self, message):
        self.log.config(
            state="normal"
        )

        self.log.insert(
            "end",
            message + "\n"
        )

        self.log.see(
            "end"
        )

        self.log.config(
            state="disabled"
        )

    # ========================================================
    # QUEUE
    # ========================================================

    def _drain(self):
        try:
            while True:
                kind, *data = self.q.get_nowait()

                if kind == "stage":
                    t, dn, tt = data

                    if tt:
                        self.status.config(
                            text=(
                                f"{t} "
                                f"({dn:,} / {tt:,})"
                            ),
                            foreground=FG
                        )

                        self.bar.config(
                            mode="determinate",
                            value=dn / tt * 100
                        )

                    else:
                        self.status.config(
                            text=t,
                            foreground=FG
                        )

                        self.bar.config(
                            mode="indeterminate"
                        )

                elif kind == "versions":
                    self.status.config(
                        text=(
                            f"{len(data[0])} "
                            "versions loaded"
                        ),
                        foreground=MUTED
                    )

                elif kind == "msg":
                    self.log_message(
                        data[0]
                    )

                elif kind == "done":
                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY"
                    )

                    self.bar.stop()

                    self.bar.config(
                        mode="determinate",
                        value=100
                    )

                    self.status.config(
                        text=data[0],
                        foreground=ACCENT
                    )

                elif kind == "error":
                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY"
                    )

                    self.bar.stop()

                    self.bar.config(
                        mode="determinate",
                        value=0
                    )

                    self.status.config(
                        text="Failed — see log",
                        foreground=DANGER
                    )

                    self.log_message(
                        f"ERROR: {data[0]}"
                    )

        except queue.Empty:
            pass

        self.root.after(
            100,
            self._drain
        )


def run():
    root = tk.Tk()

    App(root)

    root.mainloop()
```

This version fixes the specific `IndentationError` and changes the OptiFine workflow to what you described: **the launcher can install a user-provided OptiFine installer, while manual OptiFine JAR installation remains supported.**
