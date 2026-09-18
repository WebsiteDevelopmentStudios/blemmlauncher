BLEMMLAUNCHER
=============
A custom Minecraft launcher for anyone to use.


ABOUT
-----
BlemmLauncher is a lightweight custom launcher for Minecraft. It supports
both a normal graphical mode and a fast "headless" mode for launching a
saved instance straight from a desktop shortcut, so you can jump into a
modpack or profile with one click instead of opening a launcher window
every time.


FEATURES
--------
- GUI mode for browsing and managing instances.
- Headless instance launching via desktop shortcuts (--instance <name>).
- Mod loader support: Forge (working). NeoForge and Fabric are listed as
  options but are NOT implemented yet — selecting either one will just
  give you an error, not a working install.
- Optional OptiFine installation per instance.
- Per-instance settings: Minecraft version, username, RAM allocation,
  loader, and loader build.
- On Windows, automatically relaunches itself with administrator rights
  (UAC prompt) before doing any downloads or launching Java, so there's
  never more than one launcher window or Java process running.


REQUIREMENTS
------------
- Windows (administrator elevation is Windows-specific; the launcher
  still runs on other platforms, just without the elevation step).
- Python 3 (if running from source rather than a packaged build).
- Java, matching whatever Minecraft version/loader you intend to launch.


INSTALLATION
------------
1. Download the latest release from the Releases page, or clone this
   repository:
       git clone https://github.com/WebsiteDevelopmentStudios/blemmlauncher.git
2. If running from source, make sure Python 3 is installed and the
   `blemmlauncher` package is available on your Python path (it lives
   alongside run.py in this repository).


USAGE
-----
Launch the GUI:
    python run.py

Launch a saved instance directly (e.g. from a desktop shortcut), without
opening the GUI:
    python run.py --instance <instance-name>

On Windows, if the launcher is not already running with administrator
rights, it will relaunch itself and prompt for elevation. If you decline
elevation, the launcher still runs, but Minecraft/Java downloads may
fail — in that case, run it as administrator.

Each instance is configured with:
    version      - Minecraft version ID
    loader       - "forge" (working); "neoforge" and "fabric" are
                    recognized but not yet implemented and will error
                    out if selected (optional)
    loader_build - specific loader build (optional)
    username     - player name (default: "Blemm")
    ram          - memory allocation, e.g. "4G" (default: "4G")
    optifine     - true/false, whether to install OptiFine (default: false)


PROJECT STRUCTURE
------------------
run.py           - Entry point: handles admin elevation and dispatches to
                    either the GUI or a headless instance launch.
blemmlauncher/   - Core launcher package (instance management, version/
                    loader installation, and launch logic).
.github/workflows/ - CI/CD workflow definitions for this repository.


OPTIFINE INSTALLATION NOTE
--------------------------
When installing OptiFine and you click "OK" on the upload/install prompt,
the file picker will NOT default to a useful folder. You need to manually
navigate to:

    Users\<username>\AppData\Local\Temp\_MEI0000xxxxx\minecraft\instances\<name of instance>\

...and then click "Open" there. (The _MEI0000xxxxx folder name is a
temporary PyInstaller extraction folder and its exact number will vary
each time you run the launcher.)


KNOWN ISSUES
------------
- NeoForge and Fabric loader support is not finished. Choosing either of
  these for an instance will result in an error rather than a working
  install — only Forge is functional right now.


CONTRIBUTING
------------
Issues and pull requests are welcome on GitHub:
    https://github.com/WebsiteDevelopmentStudios/blemmlauncher


LICENSE
-------
See the repository for license details.
