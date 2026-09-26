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

from . import database


def _user_data_root():
    """
    Return the persistent launcher data directory.

    Packaged Windows builds keep user data in %APPDATA% so updates and
    reinstalls never replace Minecraft servers, instances, assets, or tools.
    BLEMM_DIR remains an explicit override for advanced/custom setups.
    """
    override = os.environ.get("BLEMM_DIR")
    if override:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(override)))

    if os.name == "nt" and getattr(sys, "frozen", False):
        roaming = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming"
        )
        new_root = os.path.join(roaming, "BlemmLauncher", "minecraft")
        old_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "minecraft"
        )

        if os.path.abspath(old_root) != os.path.abspath(new_root) and os.path.isdir(old_root):
            marker = os.path.join(new_root, ".legacy_migration_complete")
            if not os.path.exists(marker):
                os.makedirs(new_root, exist_ok=True)
                for base, dirs, files in os.walk(old_root):
                    rel = os.path.relpath(base, old_root)
                    target = new_root if rel == "." else os.path.join(new_root, rel)
                    os.makedirs(target, exist_ok=True)
                    for filename in files:
                        src = os.path.join(base, filename)
                        dst = os.path.join(target, filename)
                        if not os.path.exists(dst):
                            try:
                                shutil.copy2(src, dst)
                            except OSError:
                                pass
                try:
                    with open(marker, "w", encoding="utf-8") as f:
                        f.write("BlemmLauncher legacy data migration completed.\\n")
                except OSError:
                    pass

        return new_root

    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "minecraft"
    )


LAUNCHERS_ROOT = _user_data_root()

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
        os.makedirs(INSTANCES_DIR, exist_ok=True)
        return database.reconcile("instances", [])
    disk = [
        n for n in sorted(os.listdir(INSTANCES_DIR))
        if os.path.exists(os.path.join(INSTANCES_DIR, n, "blemm.json"))
    ]
    # Reconcile with the persistent registry so instances survive restarts
    # and older launcher versions are migrated automatically.
    return database.reconcile("instances", disk)


def load_cfg(name):
    with open(os.path.join(instance_dir(name), "blemm.json"), encoding="utf-8") as f:
        return json.load(f)


def save_cfg(name, cfg):
    os.makedirs(instance_dir(name), exist_ok=True)
    with open(os.path.join(instance_dir(name), "blemm.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    database.register("instances", name)


def install_vanilla(mc_version):
    """Download and prepare a real Mojang client version."""
    from . import core
    m = core.manifest()
    vid = core.resolve_version(mc_version, m)
    vj = core.load_version_json(vid, m)
    core.install_libraries(vj)
    core.install_assets(vj)
    return vid


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
        "optifine": False,
        "demo": False
    }
    save_cfg(name, cfg)
    return cfg



# ============================================================
# JAVA MULTIPLAYER SERVER LIST
# ============================================================

_NBT_END = 0
_NBT_BYTE = 1
_NBT_SHORT = 2
_NBT_INT = 3
_NBT_LONG = 4
_NBT_FLOAT = 5
_NBT_DOUBLE = 6
_NBT_BYTE_ARRAY = 7
_NBT_STRING = 8
_NBT_LIST = 9
_NBT_COMPOUND = 10
_NBT_INT_ARRAY = 11
_NBT_LONG_ARRAY = 12


def _nbt_read_string(data, pos):
    import struct
    if pos + 2 > len(data):
        raise ValueError("truncated NBT string")
    size = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    end = pos + size
    if end > len(data):
        raise ValueError("truncated NBT string data")
    return data[pos:end].decode("utf-8"), end


def _nbt_read_payload(data, pos, tag_type):
    import struct
    if tag_type == _NBT_BYTE:
        return struct.unpack_from(">b", data, pos)[0], pos + 1
    if tag_type == _NBT_SHORT:
        return struct.unpack_from(">h", data, pos)[0], pos + 2
    if tag_type == _NBT_INT:
        return struct.unpack_from(">i", data, pos)[0], pos + 4
    if tag_type == _NBT_LONG:
        return struct.unpack_from(">q", data, pos)[0], pos + 8
    if tag_type == _NBT_FLOAT:
        return struct.unpack_from(">f", data, pos)[0], pos + 4
    if tag_type == _NBT_DOUBLE:
        return struct.unpack_from(">d", data, pos)[0], pos + 8
    if tag_type == _NBT_STRING:
        return _nbt_read_string(data, pos)
    if tag_type == _NBT_BYTE_ARRAY:
        n = struct.unpack_from(">i", data, pos)[0]
        pos += 4
        return list(data[pos:pos + n]), pos + n
    if tag_type == _NBT_INT_ARRAY:
        n = struct.unpack_from(">i", data, pos)[0]
        pos += 4
        values = []
        for _ in range(n):
            values.append(struct.unpack_from(">i", data, pos)[0])
            pos += 4
        return values, pos
    if tag_type == _NBT_LONG_ARRAY:
        n = struct.unpack_from(">i", data, pos)[0]
        pos += 4
        values = []
        for _ in range(n):
            values.append(struct.unpack_from(">q", data, pos)[0])
            pos += 8
        return values, pos
    if tag_type == _NBT_LIST:
        child_type = data[pos]
        n = struct.unpack_from(">i", data, pos + 1)[0]
        pos += 5
        values = []
        for _ in range(n):
            value, pos = _nbt_read_payload(data, pos, child_type)
            values.append(value)
        return {"type": child_type, "items": values}, pos
    if tag_type == _NBT_COMPOUND:
        values = {}
        while True:
            child_type = data[pos]
            pos += 1
            if child_type == _NBT_END:
                break
            name, pos = _nbt_read_string(data, pos)
            value, pos = _nbt_read_payload(data, pos, child_type)
            values[name] = {"type": child_type, "value": value}
        return values, pos
    raise ValueError("unsupported NBT tag type: " + str(tag_type))


def _nbt_read(data):
    if not data or data[0] != _NBT_COMPOUND:
        raise ValueError("servers.dat is not a compound NBT file")
    _, pos = _nbt_read_string(data, 1)
    return _nbt_read_payload(data, pos, _NBT_COMPOUND)[0]


def _nbt_write_string(value):
    import struct
    raw = str(value).encode("utf-8")
    if len(raw) > 65535:
        raise ValueError("NBT string is too long")
    return struct.pack(">H", len(raw)) + raw


def _nbt_write_payload(tag_type, value):
    import struct
    if tag_type == _NBT_BYTE:
        return struct.pack(">b", int(value))
    if tag_type == _NBT_SHORT:
        return struct.pack(">h", int(value))
    if tag_type == _NBT_INT:
        return struct.pack(">i", int(value))
    if tag_type == _NBT_LONG:
        return struct.pack(">q", int(value))
    if tag_type == _NBT_FLOAT:
        return struct.pack(">f", float(value))
    if tag_type == _NBT_DOUBLE:
        return struct.pack(">d", float(value))
    if tag_type == _NBT_STRING:
        return _nbt_write_string(value)
    if tag_type == _NBT_BYTE_ARRAY:
        return struct.pack(">i", len(value)) + bytes((int(x) & 255) for x in value)
    if tag_type == _NBT_INT_ARRAY:
        return struct.pack(">i", len(value)) + b"".join(struct.pack(">i", int(x)) for x in value)
    if tag_type == _NBT_LONG_ARRAY:
        return struct.pack(">i", len(value)) + b"".join(struct.pack(">q", int(x)) for x in value)
    if tag_type == _NBT_LIST:
        child_type = int(value["type"])
        items = value.get("items", [])
        return bytes([child_type]) + struct.pack(">i", len(items)) + b"".join(
            _nbt_write_payload(child_type, item) for item in items
        )
    if tag_type == _NBT_COMPOUND:
        out = bytearray()
        for name, entry in value.items():
            child_type = int(entry["type"])
            out.append(child_type)
            out.extend(_nbt_write_string(name))
            out.extend(_nbt_write_payload(child_type, entry["value"]))
        out.append(_NBT_END)
        return bytes(out)
    raise ValueError("unsupported NBT tag type: " + str(tag_type))


def _nbt_write(root):
    return bytes([_NBT_COMPOUND]) + _nbt_write_string("") + _nbt_write_payload(_NBT_COMPOUND, root)


def _server_list_entry(name, address):
    return {
        "type": _NBT_COMPOUND,
        "value": {
            "name": {"type": _NBT_STRING, "value": str(name)},
            "ip": {"type": _NBT_STRING, "value": str(address)},
            "acceptTextures": {"type": _NBT_BYTE, "value": 0},
        }
    }


def ensure_online_server(name="Survival", address="survival.blemm.devs.surf:25565"):
    """Add/update the managed server in an instance's Minecraft Multiplayer list."""
    d = instance_dir(name)
    os.makedirs(d, exist_ok=True)
    target = os.path.join(d, "servers.dat")
    root = {}

    if os.path.isfile(target):
        try:
            import gzip
            with gzip.open(target, "rb") as f:
                root = _nbt_read(f.read())
        except Exception:
            root = {}

    existing = root.get("servers")
    if not isinstance(existing, dict) or existing.get("type") != _NBT_LIST:
        existing = {"type": _NBT_LIST, "items": []}

    list_value = existing.get("value") if isinstance(existing.get("value"), dict) else {"type": _NBT_COMPOUND, "items": []}
    items = list_value.setdefault("items", [])
    entry = _server_list_entry("Survival", address)
    replaced = False

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        value = item.get("value", {})
        if not isinstance(value, dict):
            continue
        item_name = value.get("name", {}).get("value")
        item_ip = value.get("ip", {}).get("value")
        if item_name == "Survival" or item_ip == address:
            items[i] = entry
            replaced = True
            break

    if not replaced:
        items.append(entry)

    root["servers"] = {
        "type": _NBT_LIST,
        "value": {"type": _NBT_COMPOUND, "items": items},
    }

    import gzip
    tmp = target + ".part"
    with gzip.open(tmp, "wb") as f:
        f.write(_nbt_write(root))
    os.replace(tmp, target)
    return target


def delete(name):
    d = instance_dir(name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    database.unregister("instances", name)


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
    client_dest = os.path.join(vdest, vid + ".jar")
    shutil.copy2(src, client_dest)

    dependency_result = scan_custom_client_dependencies(client_dest, name)

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
    extra = " and " + str(len(dependency_result["downloaded"])) + " dependencies prepared" if dependency_result["downloaded"] else ""
    return name, "custom client '" + vid + "' imported (based on Minecraft " + mv + ")" + extra



def scan_custom_client_dependencies(jar_path, instance_name):
    """Scan a custom client JAR for declared dependency coordinates and download them.

    Supported declarations:
    - META-INF/blemm-dependencies.json
    - META-INF/dependencies.json
    - dependencies.json
    - META-INF/MANIFEST.MF Class-Path entries that point to dependency JARs

    JSON may contain:
      {"libraries": ["group:artifact:version"]}
    or:
      {"dependencies": [{"name": "group:artifact:version", "url": "..."}]}
    """
    from . import core

    jar_path = os.path.abspath(jar_path)
    if not os.path.isfile(jar_path):
        raise RuntimeError("custom client JAR not found: " + jar_path)

    instance_root = instance_dir(instance_name)
    libraries_dir = os.path.join(instance_root, "libraries")
    os.makedirs(libraries_dir, exist_ok=True)

    declarations = []
    manifest_classpath = []

    with zipfile.ZipFile(jar_path, "r") as z:
        names = set(z.namelist())

        for candidate in (
            "META-INF/blemm-dependencies.json",
            "META-INF/dependencies.json",
            "dependencies.json",
        ):
            if candidate not in names:
                continue
            try:
                data = json.loads(z.read(candidate).decode("utf-8"))
            except Exception as e:
                raise RuntimeError(
                    "Invalid dependency manifest in custom client: " + candidate
                ) from e

            values = data.get("libraries", data.get("dependencies", [])) if isinstance(data, dict) else data
            if not isinstance(values, list):
                continue

            for value in values:
                if isinstance(value, str):
                    declarations.append({"name": value})
                elif isinstance(value, dict):
                    name = value.get("name") or value.get("coordinate") or value.get("maven")
                    if name:
                        declarations.append({
                            "name": str(name),
                            "url": value.get("url"),
                        })

        if "META-INF/MANIFEST.MF" in names:
            try:
                manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
                manifest = manifest.replace("\r\n ", "").replace("\n ", "")
                for line in manifest.splitlines():
                    if line.lower().startswith("class-path:"):
                        manifest_classpath.extend(line.split(":", 1)[1].strip().split())
                    elif line.lower().startswith("class-path "):
                        manifest_classpath.extend(line.split(":", 1)[1].strip().split())
            except Exception:
                pass

    downloaded = []
    unresolved = []

    def coordinate_path(coordinate):
        parts = str(coordinate).split(":")
        if len(parts) < 3:
            raise ValueError("expected group:artifact:version")
        group, artifact, version = parts[:3]
        classifier = parts[3] if len(parts) > 3 and parts[3] else None
        ext = "jar"
        if classifier and classifier.startswith("http"):
            classifier = None
        filename = artifact + "-" + version
        if classifier:
            filename += "-" + classifier
        filename += "." + ext
        rel = os.path.join(*group.split("."), artifact, version, filename)
        return group, artifact, version, rel

    for item in declarations:
        coordinate = item["name"].strip()
        try:
            _, _, _, rel = coordinate_path(coordinate)
        except ValueError:
            unresolved.append(coordinate)
            continue

        dest = os.path.join(libraries_dir, rel)
        url = item.get("url")
        if not url:
            url = "https://repo1.maven.org/maven2/" + rel.replace(os.sep, "/")

        try:
            _download(url, dest)
            downloaded.append((coordinate, dest))
        except Exception as e:
            unresolved.append(coordinate + " (" + str(e) + ")")

    # Manifest Class-Path entries are often filenames beside the client JAR.
    # Copy any dependency JARs that were bundled next to the imported client
    # into the instance's libraries directory rather than silently losing them.
    if manifest_classpath:
        source_dir = os.path.dirname(jar_path)
        for relname in manifest_classpath:
            relname = os.path.basename(relname)
            source = os.path.join(source_dir, relname)
            if os.path.isfile(source) and relname.lower().endswith(".jar"):
                dest = os.path.join(libraries_dir, relname)
                if os.path.abspath(source) != os.path.abspath(dest):
                    shutil.copy2(source, dest)
                downloaded.append(("bundled:" + relname, dest))

    # Also load any dependency JARs already bundled inside the client.
    # They are extracted only when they live under a conventional
    # dependencies/libraries folder, avoiding accidental extraction of
    # ordinary client resources.
    with zipfile.ZipFile(jar_path, "r") as z:
        for name in z.namelist():
            normalized = name.replace("\\", "/")
            if not normalized.lower().endswith(".jar"):
                continue
            if not (normalized.startswith("libraries/") or normalized.startswith("dependencies/")):
                continue
            out = os.path.join(libraries_dir, os.path.basename(normalized))
            with z.open(name) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            downloaded.append(("embedded:" + os.path.basename(normalized), out))

    if downloaded:
        core.log(
            "Custom client dependency scan: installed "
            + str(len(downloaded)) + " dependency file(s)."
        )

    if unresolved:
        core.log(
            "Custom client dependency scan: unresolved declarations: "
            + ", ".join(unresolved[:20])
        )

    return {
        "downloaded": downloaded,
        "unresolved": unresolved,
    }


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
    return {
        "mod": "mod",
        "modpack": "modpack",
        "shader": "shader",
        "resourcepack": "resourcepack",
        "datapack": "datapack",
        "world": "world",
    }.get(ptype, "mod")


def modrinth_search(query, mc_version, loader=None, project_type="mod"):
    pt = _modrinth_project_type(project_type)
    facets = [["project_type:" + pt], ["versions:" + str(mc_version)]]
    if pt == "mod" and loader:
        facets.append(["categories:" + str(loader).lower().strip()])

    try:
        data = _modrinth_json("/search", {
            "limit": "12",
            "query": query or "",
            "facets": json.dumps(facets, separators=(",", ":"))
        })
    except Exception:
        data = None

    if not data or not data.get("hits"):
        fallback = _modrinth_json("/search", {
            "limit": "12",
            "query": query or "",
            "facets": json.dumps([["project_type:" + pt]], separators=(",", ":"))
        })
        hits = fallback.get("hits", [])
    else:
        hits = data.get("hits", [])

    return [
        {
            "title": h.get("title", "Unknown"),
            "id": h.get("project_id", ""),
            "desc": (h.get("description") or "")[:160],
            "downs": h.get("downloads", 0),
            "author": h.get("author", "Unknown"),
            "icon": h.get("icon_url"),
        }
        for h in hits
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
        else "datapacks" if pt == "datapack"
        else "saves" if pt == "world"
        else "modpacks" if pt == "modpack"
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
