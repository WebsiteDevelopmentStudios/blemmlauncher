import sys
def main():
    args = sys.argv[1:]
    if "--instance" in args:
        i = args.index("--instance"); name = args[i + 1]
        from blemmlauncher import core, instances
        core.set_reporter(lambda t, d=None, o=None: print(f"[Blemm] {t}"))
        cfg = instances.load_cfg(name); instances.use(name, core)
        vid = cfg["version"]
        if cfg.get("loader") == "forge": vid = core.install_forge(vid, cfg.get("loader_build"))
        elif cfg.get("loader") == "fabric": instances.install_fabric(vid)
        elif cfg.get("loader") == "neoforge": instances.install_neoforge(vid, cfg.get("loader_build"))
        core.launch(vid, cfg.get("username", "Blemm"), cfg.get("ram", "4G"))
    else:
        from blemmlauncher import gui; gui.run()
main()
