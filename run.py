"""BlemmLauncher entry point - admin elevation + shortcut launches."""


import os
import sys


def is_admin():
    """True if the process already has administrator rights."""

    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        # Non-Windows (or ctypes unavailable): assume fine.

        return True


def relaunch_as_admin():
    """Relaunch this script/exe with the UAC elevation prompt.

    Returns True if elevation was (probably) triggered, False on
    failure.
    """

    try:
        import ctypes

        params = " ".join('"' + a + '"' for a in sys.argv)

        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            None,
            1
        )

        # ShellExecuteW returns <= 32 on failure.

        return ret > 32

    except Exception:
        return False


def run_named_instance(name):
    """Headless launch for a single instance (desktop shortcuts)."""

    from blemmlauncher import core, instances

    # Current reporter protocol: (kind, text, done, total).

    core.set_reporter(
        lambda kind, text, done=None, total=None:
            print("[Blemm] " + str(text))
    )

    cfg = instances.load_cfg(name)
    instances.use(name, core)

    vid = cfg["version"]
    loader = cfg.get("loader")

    if loader == "forge":
        vid = core.install_forge(vid, cfg.get("loader_build"))

    elif loader == "neoforge":
        vid = instances.install_neoforge(vid, cfg.get("loader_build"))

    elif loader == "fabric":
        vid = instances.install_fabric(vid)

    core.launch(
        vid,
        cfg.get("username", "Blemm"),
        cfg.get("ram", "4G"),
        optifine=bool(cfg.get("optifine", False))
    )


def main():
    args = sys.argv[1:]

    # Elevation first, BEFORE any window or heavy import, so there is
    # never more than one launcher window / Java process.

    if os.name == "nt" and not is_admin():
        print("BlemmLauncher needs administrator rights - "
              "asking for elevation...")

        if relaunch_as_admin():
            sys.exit(0)

        print("WARNING: running WITHOUT administrator rights. "
              "If Minecraft/Java downloads fail, run the launcher "
              "as administrator.")

    if "--agent" in args:
        from Dev import agent
        agent.main()
        return

    if "--instance" in args:
        i = args.index("--instance")
        name = args[i + 1]

        run_named_instance(name)

    else:
        from blemmlauncher import gui
        gui.run()


if __name__ == "__main__":
    main()
