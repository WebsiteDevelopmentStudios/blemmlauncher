import argparse, sys
from . import core

def main():
    p = argparse.ArgumentParser(prog="blemmlauncher", description="BlemmLauncher - Minecraft, but ours.")
    sub = p.add_subparsers(dest="cmd")

    lg = sub.add_parser("launch", help="play!") 
    lg.add_argument("version", nargs="?", default="release")
    lg.add_argument("--player", default="Blemm")
    lg.add_argument("--ram", default="2G")
    lg.add_argument("--optifine", help="OptiFine installer jar")

    fg = sub.add_parser("forge", help="install forge for a MC version")
    fg.add_argument("version")
    fg.add_argument("--build", default="recommended", help="forge build number or 'recommended'/'latest'")

    ad = sub.add_parser("add", help="add mods/packs (auto-detected)")
    ad.add_argument("files", nargs="+")

    lv = sub.add_parser("list", help="list versions")
    sub.add_parser("gui", help="open the GUI")

    a = p.parse_args()
    if a.cmd == "launch":   core.launch(a.version, a.player, a.ram, a.optifine)
    elif a.cmd == "forge":
        vid = core.install_forge(a.version, a.build)
        core.launch(vid)
    elif a.cmd == "add":   core.add_content(a.files)
    elif a.cmd == "list":
        versions, rel, snap = core.list_versions()
        print(f"latest release: {rel} | snapshot: {snap}\n" + "\n".join(versions[:30]) + "\n...")
    elif a.cmd == "gui":    from . import gui; gui.run()
    else: p.print_help()

if __name__ == "__main__": main()
