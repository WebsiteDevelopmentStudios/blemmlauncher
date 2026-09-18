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
import re

from concurrent.futures import ThreadPoolExecutor, as_completed

LAUNCHER_NAME, LAUNCHER_VERSION = "BlemmLauncher", "1.3.0"

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
LIB_BASE = "https://libraries.minecraft.net/"
RESOURCE_BASE = "https://resources.download.minecraft.net/"
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN = "https://maven.minecraftforge.net"
ADOPTIUM_API = "https://api.adoptium.net/v3/binary/latest/{major}/ga/windows/x64/jdk/hotspot/normal/eclipse"

OPTIFINE_DOWNLOADS_URL = "https://optifine.net/downloads"
OPTIFINE_DOWNLOADX_URL = "https://optifine.net/downloadx?f={filename}"

USER_AGENT = (
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
f"{LAUNCHER_NAME}/{LAUNCHER_VERSION} (contact: local)"
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(**file**)))
GAME_DIR = os.environ.get("BLEMM_DIR", os.path.join(ROOT, "minecraft"))
ASSETS = os.path.join(GAME_DIR, "assets")
LIBS = os.path.join(GAME_DIR, "libraries")
TOOLS = os.path.join(GAME_DIR, "tools")

def log(msg):
print(f"[Blemm] {msg}")

# ---------- progress reporting ----------

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

# ---------- helpers ----------

def os_name():
return {"Windows": "windows", "Darwin": "osx"}.get(platform.system(), "linux")

def file_sha1(p):
h = hashlib.sha1()
with open(p, "rb") as f:
for chunk in iter(lambda: f.read(1 << 16), b""):
h.update(chunk)
return h.hexdigest()

def _open(url):
req = urllib.request.Request(
url,
headers={
"User-Agent": USER_AGENT,
"Accept": "*/*",
},
)
return urllib.request.urlopen(req, timeout=25)

def download(url, dest, sha1=None):
dest = os.path.normpath(dest)
os.makedirs(os.path.dirname(dest), exist_ok=True)

```
if os.path.exists(dest) and (
    sha1 is None or file_sha1(dest) == sha1
):
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
```

def fetch_json(url):
with _open(url) as r:
return json.load(r)

def maven_path(name):
g, aid, ver, *ext = name.split(":")
return (
f"{g.replace('.', '/')}/{aid}/{ver}/"
f"{aid}-{ver}{'-' + ext[0] if ext else ''}.jar"
)

# ---------- Java ----------

def _required_java(vid):
try:
parts = [int(x) for x in vid.split(".") if x.isdigit()]
major = parts[1] if len(parts) > 1 else 0
minor = parts[2] if len(parts) > 2 else 0

```
    if major > 20 or (major == 20 and minor >= 5):
        return "21"

    if major >= 18:
        return "17"

    if major == 17:
        return "16"

    return "8"

except Exception:
    return "17"
```

def java_bin_for(version_id, major=None):
exe = "java.exe" if os_name() == "windows" else "java"

```
if shutil.which(exe):
    return exe

if major is None:
    major = _required_java(version_id)

jdir = os.path.join(TOOLS, f"java-{major}")
jbin = os.path.join(jdir, "bin", exe)

if not os.path.exists(jbin):
    report(f"Downloading Java {major} (one time, ~180 MB)...")

    os.makedirs(TOOLS, exist_ok=True)

    zpath = os.path.join(TOOLS, f"jdk{major}.zip")
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
```

def _mc_major(version_id):
try:
return int(version_id.split(".")[1])
except Exception:
return 20

# ---------- manifest / versions ----------

def manifest():
for attempt in (1, 2, 3):
try:
return fetch_json(MANIFEST_URL)

```
    except Exception as e:
        if attempt == 3:
            raise RuntimeError(
                f"can't reach Mojang (attempt 3): {e}\n"
                f"check internet / firewall / proxy, then retry"
            ) from e

        log(f"manifest fetch failed ({e}) - retrying...")
```

def list_versions():
m = manifest()
return (
[v["id"] for v in m["versions"]],
m["latest"]["release"],
m["latest"]["snapshot"],
)

def resolve_version(version_id, m):
if version_id in (None, "", "release"):
return m["latest"]["release"]

```
if version_id == "snapshot":
    return m["latest"]["snapshot"]

if not any(v["id"] == version_id for v in m["versions"]):
    if os.path.exists(
        os.path.join(
            GAME_DIR,
            "versions",
            version_id,
            version_id + ".json",
        )
    ):
        return version_id

    raise RuntimeError(f"Unknown version '{version_id}'.")

return version_id
```

def load_version_json(vid, m):
"""Load a version JSON, resolving Forge-style inheritsFrom parents."""

```
path = os.path.join(
    GAME_DIR,
    "versions",
    vid,
    vid + ".json",
)

if not os.path.exists(path):
    vurl = next(v["url"] for v in m["versions"] if v["id"] == vid)
    report("Downloading version info...")
    download(vurl, path)

vj = json.load(open(path, encoding="utf-8"))

if "inheritsFrom" in vj:
    parent = load_version_json(vj["inheritsFrom"], m)

    vj["libraries"] = (
        vj.get("libraries", []) +
        parent.get("libraries", [])
    )

    pj = parent.get("arguments", {})
    cj = vj.get("arguments", {})

    vj["arguments"] = {
        "game": pj.get("game", []) + cj.get("game", []),
        "jvm": pj.get("jvm", []) + cj.get("jvm", []),
    }

    vj.setdefault("mainClass", parent["mainClass"])
    vj.setdefault("assetIndex", parent.get("assetIndex"))
    vj.setdefault("downloads", parent.get("downloads"))
    vj.setdefault("logging", parent.get("logging"))

    vj["_java_major"] = (
        vj.get("javaVersion", {}).get("majorVersion")
        or parent.get("_java_major")
        or parent.get("javaVersion", {}).get("majorVersion")
    )

    vj["_vanilla_id"] = vj["inheritsFrom"]

else:
    vj["_java_major"] = vj.get(
        "javaVersion", {}
    ).get("majorVersion")

    vj["_vanilla_id"] = vid

report("Downloading game files...", 5, 100)

d = vj["downloads"]["client"]

jar = os.path.join(
    GAME_DIR,
    "versions",
    vj["_vanilla_id"],
    vj["_vanilla_id"] + ".jar",
)

download(d["url"], jar, d.get("sha1"))

return vj
```

# ---------- rules / libraries / natives ----------

def rule_matches(rule):
if "os" not in rule:
return True

```
osr = rule["os"]

if osr.get("name") and osr["name"] != os_name():
    return False

return True
```

def is_allowed(rules):
if not rules:
return True

```
allowed, matched = True, False

for r in rules:
    if rule_matches(r):
        allowed = r.get("action") == "allow"
        matched = True

return allowed if matched else True
```

def install_libraries(vj):
natives_dir = os.path.join(
GAME_DIR,
"natives",
vj.get("id", vj["_vanilla_id"]),
)

```
os.makedirs(natives_dir, exist_ok=True)

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
        max(len(todo), 1),
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

    jar = os.path.join(LIBS, rp)

    url = (
        (art.get("url") if art else None)
        or (FORGE_MAVEN + "/" + rp)
    )

    try:
        download(
            url,
            jar,
            art.get("sha1") if art else None,
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

            download(other + rp, jar)

    classpath.append(jar)

    classifier = lib.get("natives", {}).get(os_name())

    if classifier:
        nart = dl.get("classifiers", {}).get(classifier)

        if nart:
            njar = os.path.join(
                LIBS,
                nart["path"],
            )

            download(
                nart["url"],
                njar,
                nart.get("sha1"),
            )

            with zipfile.ZipFile(njar) as z:
                for info in z.infolist():
                    n = os.path.basename(info.filename)

                    if (
                        info.filename.startswith("META-INF/")
                        or n.endswith(
                            (".sha1", ".sha", ".git")
                        )
                    ):
                        continue

                    if n:
                        with z.open(info) as s, open(
                            os.path.join(natives_dir, n),
                            "wb",
                        ) as o:
                            shutil.copyfileobj(s, o)

return classpath, natives_dir
```

def install_assets(vj):
"""Download all asset objects for this version."""

```
idx = vj.get("assetIndex")

if not idx:
    return vj.get("assets", "legacy")

idp = os.path.join(
    ASSETS,
    "indexes",
    idx["id"] + ".json",
)

download(
    idx["url"],
    idp,
    idx.get("sha1"),
)

objects = json.load(
    open(idp, encoding="utf-8")
).get("objects", {})

items = list(objects.items())
total = max(len(items), 1)
done = 0

def _fetch(entry):
    name, obj = entry
    h = obj["hash"]

    try:
        download(
            RESOURCE_BASE + f"{h[:2]}/{h}",
            os.path.join(
                ASSETS,
                "objects",
                h[:2],
                h,
            ),
            h,
        )
        return None

    except Exception as e:
        return f"{name}: {e}"

report(
    "Downloading game assets (biggest step, first time only)...",
    0,
    total,
)

with ThreadPoolExecutor(max_workers=24) as ex:
    futures = [
        ex.submit(_fetch, item)
        for item in items
    ]

    for fut in as_completed(futures):
        done += 1

        if done % 25 == 0 or done == total:
            report(
                "Downloading game assets (biggest step, first time only)...",
                done,
                total,
            )

        err = fut.result()

        if err:
            log(f"  ! {err}")

return idx["id"]
```

# ---------- OptiFine ----------

def _optifine_mods_dir():
d = os.path.join(GAME_DIR, "mods")
os.makedirs(d, exist_ok=True)
return d

def find_optifine_jars():
"""
Find normal OptiFine mod jars already installed in mods/.

```
This intentionally does not treat an OptiFine installer as the final
mod jar.
"""
mods = _optifine_mods_dir()
found = []

for filename in os.listdir(mods):
    if not filename.lower().endswith(".jar"):
        continue

    if "optifine" not in filename.lower():
        continue

    path = os.path.join(mods, filename)

    if os.path.isfile(path):
        found.append(path)

return found
```

def _find_optifine_installers():
"""
Find OptiFine installer jars in the tools folder.
"""
found = []

```
if not os.path.isdir(TOOLS):
    return found

for filename in os.listdir(TOOLS):
    low = filename.lower()

    if (
        low.endswith(".jar")
        and "optifine" in low
        and "_installer" in low
    ):
        found.append(
            os.path.join(TOOLS, filename)
        )

return found
```

def install_optifine(installer_jar, with_forge=True):
"""
Extract an OptiFine installer into the instance's mods directory.

```
The original installer is kept in tools/ so the user can retry it.
"""

if not os.path.isfile(installer_jar):
    raise RuntimeError(
        f"OptiFine installer not found:\n{installer_jar}"
    )

mods_dir = _optifine_mods_dir()

base = os.path.basename(installer_jar)

output_name = base.replace(
    "_installer",
    "",
)

if not output_name.lower().endswith(".jar"):
    output_name += ".jar"

out = os.path.join(
    mods_dir,
    output_name,
)

if os.path.exists(out):
    log(f"OptiFine already installed: {out}")
    return out

work = tempfile.mkdtemp(
    prefix="blemm_optifine_"
)

try:
    java = (
        shutil.which("java")
        or java_bin_for("1.21")
    )

    log(
        f"Extracting OptiFine installer: {base}"
    )

    r = subprocess.run(
        [
            java,
            "-jar",
            os.path.abspath(installer_jar),
            "extract",
        ],
        cwd=work,
        capture_output=True,
    )

    jars = [
        f
        for f in os.listdir(work)
        if f.lower().endswith(".jar")
    ]

    if r.returncode != 0 or not jars:
        outp = (
            (r.stdout or b"") +
            (r.stderr or b"")
        ).decode(errors="replace")

        raise RuntimeError(
            "OptiFine extraction failed.\n"
            "Make sure this is the official OptiFine "
            "installer for the correct Minecraft version.\n\n"
            f"--- output ---\n{outp[-1200:]}"
        )

    extracted = os.path.join(
        work,
        jars[0],
    )

    # Avoid accidentally overwriting a different manual OptiFine.
    if os.path.exists(out):
        stem, ext = os.path.splitext(output_name)
        out = os.path.join(
            mods_dir,
            stem + "_Blemm" + ext,
        )

    shutil.copy2(extracted, out)

    log(
        f"OptiFine installed: {out}"
        + (
            " (Forge mod)"
            if with_forge
            else ""
        )
    )

    return out

finally:
    shutil.rmtree(
        work,
        ignore_errors=True,
    )
```

def install_optifine_from_file(installer_path):
"""
Install an OptiFine installer selected manually by the user.
"""

```
if not os.path.isfile(installer_path):
    raise RuntimeError(
        "The selected OptiFine file does not exist."
    )

if not installer_path.lower().endswith(".jar"):
    raise RuntimeError(
        "Please select the OptiFine .jar installer."
    )

if "optifine" not in os.path.basename(
    installer_path
).lower():
    raise RuntimeError(
        "That does not look like an OptiFine installer."
    )

os.makedirs(TOOLS, exist_ok=True)

saved = os.path.join(
    TOOLS,
    os.path.basename(installer_path),
)

shutil.copy2(
    installer_path,
    saved,
)

return install_optifine(
    saved,
    with_forge=True,
)
```

def _get_optifine_download_filename(mc_version):
"""
Look at OptiFine's downloads page and find an installer matching
the requested Minecraft version.

```
OptiFine changes build letters/numbers over time, so the launcher
should not hard-code something like HD_U_J9 forever.
"""

try:
    req = urllib.request.Request(
        OPTIFINE_DOWNLOADS_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=25,
    ) as r:
        html = r.read().decode(
            "utf-8",
            errors="replace",
        )

except Exception as e:
    raise RuntimeError(
        f"Could not access OptiFine's downloads page: {e}"
    ) from e

# Example target:
# OptiFine_1.21.11_HD_U_J9.jar
pattern = re.compile(
    r"OptiFine_"
    + re.escape(mc_version)
    + r"_HD_U_[A-Za-z0-9]+"
    r"\.jar",
    re.IGNORECASE,
)

matches = pattern.findall(html)

if not matches:
    raise RuntimeError(
        f"No OptiFine release for Minecraft {mc_version} "
        "was found on OptiFine's downloads page."
    )

# Remove duplicates while preserving page order.
unique = []

for x in matches:
    if x not in unique:
        unique.append(x)

# The first matching download on the current OptiFine page is
# normally the newest matching release.
return unique[0]
```

def install_optifine_for_version(mc_version):
"""
Automatically download and install the OptiFine release matching
the selected Minecraft version.

```
If OptiFine's website blocks the launcher, the caller can fall back
to the manual installer workflow.
"""

mods_dir = _optifine_mods_dir()

existing = find_optifine_jars()

if existing:
    log(
        "OptiFine is already installed manually or from a previous "
        "launcher installation."
    )
    return existing[0]

report(
    f"Finding OptiFine for Minecraft {mc_version}..."
)

filename = _get_optifine_download_filename(
    mc_version
)

installer_path = os.path.join(
    TOOLS,
    filename,
)

if not os.path.exists(installer_path):
    report(
        f"Downloading OptiFine {mc_version}..."
    )

    url = OPTIFINE_DOWNLOADX_URL.format(
        filename=filename
    )

    try:
        download(
            url,
            installer_path,
        )

    except Exception as e:
        try:
            if os.path.exists(installer_path):
                os.remove(installer_path)
        except Exception:
            pass

        raise RuntimeError(
            "BlemmLauncher could not download OptiFine "
            f"automatically.\n\n"
            f"OptiFine: {filename}\n"
            f"Reason: {e}\n\n"
            "Use the 'Install OptiFine manually' button "
            "instead."
        ) from e

report(
    "Installing OptiFine..."
)

return install_optifine(
    installer_path,
    with_forge=True,
)
```

def get_optifine_status():
"""
Return a small status object used by the GUI.
"""

```
jars = find_optifine_jars()

return {
    "installed": bool(jars),
    "jars": jars,
    "filenames": [
        os.path.basename(x)
        for x in jars
    ],
}
```

# ---------- Forge ----------

def ensure_launcher_profile(game_dir):
"""
Forge's installer refuses to run --installClient unless it finds a
launcher_profiles.json in the target directory.
"""

```
lp = os.path.join(
    game_dir,
    "launcher_profiles.json",
)

if not os.path.exists(lp):
    os.makedirs(
        game_dir,
        exist_ok=True,
    )

    with open(
        lp,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            {
                "profiles": {},
                "settings": {},
                "version": 3,
            },
            f,
        )
```

def _forge_locally_processed(vj):
"""
Forge's own client/server/universal jars are built locally by the
installer's processors step.
"""

```
for lib in vj.get("libraries", []):
    if not lib.get(
        "name",
        "",
    ).startswith("net.minecraftforge:forge:"):
        continue

    art = lib.get(
        "downloads",
        {},
    ).get("artifact")

    if art and not os.path.exists(
        os.path.join(
            LIBS,
            art["path"],
        )
    ):
        return False

return True
```

def install_forge(mc_version, build=None):
if build in (
None,
"auto",
"",
"recommended",
"latest",
):
try:
promos = fetch_json(
FORGE_PROMOS
)["promos"]

```
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
            f"No Forge build found for {mc_version} "
            "(promos fetch failed)"
        )

vid = f"{mc_version}-forge-{build}"

existing = os.path.join(
    GAME_DIR,
    "versions",
    vid,
    vid + ".json",
)

if os.path.exists(existing):
    try:
        if _forge_locally_processed(
            json.load(
                open(
                    existing,
                    encoding="utf-8",
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
        f"Forge {vid} install looks incomplete - "
        "reinstalling..."
    )

    shutil.rmtree(
        os.path.dirname(existing),
        ignore_errors=True,
    )

m = manifest()

load_version_json(
    resolve_version(
        mc_version,
        m,
    ),
    m,
)

os.makedirs(
    TOOLS,
    exist_ok=True,
)

installer = os.path.join(
    TOOLS,
    f"forge-{vid}-installer.jar",
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
    installer,
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
        "--installClient",
    ],
    cwd=GAME_DIR,
    capture_output=True,
)

outp = (
    (r.stdout or b"") +
    (r.stderr or b"")
).decode(errors="replace")

matches = [
    p
    for p in glob.glob(
        os.path.join(
            GAME_DIR,
            "versions",
            f"{mc_version}*forge*",
        )
    )
    if os.path.exists(
        os.path.join(
            p,
            os.path.basename(p) + ".json",
        )
    )
]

matches.sort(
    key=os.path.getmtime,
    reverse=True,
)

if r.returncode != 0 or not matches:
    raise RuntimeError(
        f"Forge install failed "
        f"(installer exit code {r.returncode}).\n"
        f"--- installer output ---\n"
        f"{outp[-1500:]}"
    )

found = os.path.basename(
    matches[0]
)

vj_check = json.load(
    open(
        os.path.join(
            matches[0],
            found + ".json",
        ),
        encoding="utf-8",
    )
)

if not _forge_locally_processed(
    vj_check
):
    raise RuntimeError(
        "Forge installer exited OK but its processors "
        "step didn't finish (the local client/server "
        "jars are missing).\n"
        f"--- installer output ---\n"
        f"{outp[-1500:]}"
    )

log(
    f"Forge installed: {found}"
)

return found
```

# ---------- content: mods / packs / shaders ----------

def detect_kind(path):
try:
with zipfile.ZipFile(path) as z:
names = set(z.namelist())

```
except (
    zipfile.BadZipFile,
    OSError,
):
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
```

def add_content_auto(paths, kind=None):
folders = {
"mod": "mods",
"resourcepack": "resourcepacks",
"shaderpack": "shaderpacks",
}

```
installed = []

for p in paths:
    filename = os.path.basename(p)

    # If the user selects an OptiFine installer through the normal
    # Add Files button, install it properly instead of putting the
    # installer itself into mods/.
    if (
        filename.lower().endswith(".jar")
        and "optifine" in filename.lower()
        and "_installer" in filename.lower()
    ):
        try:
            out = install_optifine_from_file(p)
            installed.append(
                f"OptiFine: {os.path.basename(out)}"
            )
            continue

        except Exception as e:
            raise RuntimeError(
                f"OptiFine installation failed:\n{e}"
            ) from e

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
        folders[use_kind],
    )

    os.makedirs(
        dest_dir,
        exist_ok=True,
    )

    shutil.copy2(
        p,
        os.path.join(
            dest_dir,
            filename,
        ),
    )

    installed.append(
        f"{use_kind}: {filename}"
    )

    if use_kind == "resourcepack":
        enable_resourcepack(filename)

log(
    f"Imported {len(installed)} file(s): "
    f"{', '.join(installed)}"
)

return installed
```

def enable_resourcepack(filename):
opts_path = os.path.join(
GAME_DIR,
"options.txt",
)

```
entry = f'resourcePacks:["file/{filename}"]'
lines = []

if os.path.exists(opts_path):
    lines = open(
        opts_path,
        encoding="utf-8",
    ).read().splitlines()

lines = [
    l
    for l in lines
    if not l.startswith("resourcePacks:")
]

lines.append(entry)

open(
    opts_path,
    "w",
    encoding="utf-8",
).write(
    "\n".join(lines) + "\n"
)
```

# ---------- instance support ----------

def set_game_dir(path):
global GAME_DIR, ASSETS, LIBS, TOOLS

```
GAME_DIR = path
ASSETS = os.path.join(
    GAME_DIR,
    "assets",
)
LIBS = os.path.join(
    GAME_DIR,
    "libraries",
)
TOOLS = os.path.join(
    GAME_DIR,
    "tools",
)
```

# ---------- launch ----------

def subst(s, subs):
for k, v in subs.items():
s = s.replace(k, v)

```
return s
```

def resolve_arglist(items, subs):
"""Resolve Minecraft arguments while respecting OS rules."""

```
out = []

quick_play_options = {
    "--quickPlaySingleplayer",
    "--quickPlayMultiplayer",
    "--quickPlayRealms",
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
            subs,
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
```

def launch(
version_id,
username="Blemm",
ram="2G",
optifine=False,
):
m = manifest()

```
vid = resolve_version(
    version_id,
    m,
)

vj = load_version_json(
    vid,
    m,
)

java = java_bin_for(
    vid,
    vj.get("_java_major"),
)

vanilla_jar = os.path.join(
    GAME_DIR,
    "versions",
    vj["_vanilla_id"],
    vj["_vanilla_id"] + ".jar",
)

classpath, natives_dir = install_libraries(vj)

classpath.insert(
    0,
    vanilla_jar,
)

asset_id = install_assets(vj)

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
        "${classpath}",
    ]
)

forge_active = (
    "-forge-" in vid.lower()
    or "neoforge" in vid.lower()
)

# ---------- OptiFine ----------
if optifine:
    optifine_jars = find_optifine_jars()

    if optifine_jars:
        log(
            "OptiFine enabled."
        )

        for jar in optifine_jars:
            log(
                f"Using OptiFine: "
                f"{os.path.basename(jar)}"
            )

    else:
        log(
            "OptiFine is enabled, but no OptiFine "
            "mod jar was found in mods/."
        )

        if not forge_active:
            log(
                "OptiFine is normally used as a Forge "
                "mod in this launcher, so Forge should "
                "be enabled for OptiFine."
            )

subs = {
    "${auth_player_name}": username,
    "${auth_uuid}": str(
        uuid.uuid3(
            uuid.NAMESPACE_OID,
            "offline:" + username,
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
        asset_id,
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
    "${resolution_height}": "480",
}

cmd = [
    java,
    "-Xms512M",
    f"-Xmx{ram}",
]

log_cfg = vj.get(
    "logging",
    {},
).get(
    "client",
    {},
)

if log_cfg:
    lf = os.path.join(
        GAME_DIR,
        "log-configs",
        log_cfg["file"]["id"],
    )

    download(
        log_cfg["file"]["url"],
        lf,
        log_cfg["file"].get("sha1"),
    )

    cmd.append(
        "-Dlog4j.configurationFile="
        + os.path.abspath(lf)
    )

cmd += (
    resolve_arglist(
        jvm_args,
        subs,
    )
    + [vj["mainClass"]]
    + resolve_arglist(
        game_args,
        subs,
    )
)

os.makedirs(
    GAME_DIR,
    exist_ok=True,
)

log(
    f"Launching {vid} as {username} "
    f"(Java {vj.get('_java_major') or _required_java(vid)})..."
)

report(
    "Starting Minecraft...",
    99,
    100,
)

result = subprocess.run(
    cmd,
    cwd=GAME_DIR,
    capture_output=True,
)

report(
    "Minecraft closed.",
    100,
    100,
)

if result.returncode != 0:
    out = (
        (result.stdout or b"") +
        (result.stderr or b"")
    )

    tail = (
        out.decode(
            errors="replace"
        )
        .strip()[-1200:]
    )

    raise RuntimeError(
        f"Minecraft crashed instantly "
        f"(exit code {result.returncode}).\n"
        f"--- last output ---\n"
        f"{tail}\n"
        f"-------------------\n"
        f"If this mentions "
        f"'UnsupportedClassVersionError', "
        f"the Java version is wrong for this Minecraft."
    )
```
