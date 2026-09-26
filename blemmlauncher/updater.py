"""BlemmLauncher GitHub release updater."""

import json
import os
import re
import subprocess
import tempfile
import urllib.request

from .core import LAUNCHER_VERSION

RELEASES_URL = (
    "https://api.github.com/repos/WebsiteDevelopmentStudios/"
    "blemmlauncher/releases/latest"
)
USER_AGENT = "BlemmLauncher/" + LAUNCHER_VERSION


def _version_tuple(value):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        return (0, 0, 0)
    return tuple(int(x) for x in match.groups())


def check_latest():
    req = urllib.request.Request(
        RELEASES_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        release = json.load(response)

    latest = str(release.get("tag_name") or release.get("name") or "")
    if _version_tuple(latest) <= _version_tuple(LAUNCHER_VERSION):
        return None

    installer = None
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if name.lower().endswith(".exe") and (
            "setup" in name.lower() or "installer" in name.lower()
        ):
            installer = asset
            break

    if not installer:
        return None

    return {
        "version": latest.lstrip("vV"),
        "tag": latest,
        "name": release.get("name") or ("BlemmLauncher " + latest),
        "url": installer.get("browser_download_url"),
        "release_url": release.get("html_url"),
    }


def install(update):
    url = update.get("url")
    if not url:
        raise RuntimeError("The update does not contain an installer.")

    fd, path = tempfile.mkstemp(prefix="BlemmLauncher-update-", suffix=".exe")
    os.close(fd)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as response, open(path, "wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise

    subprocess.Popen([path], close_fds=True)
    return path
