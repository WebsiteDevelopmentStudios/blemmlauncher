# You can check this for malware yourself:
'https://www.virustotal.com/'

## BLEMMLAUNCHER
=============

A custom Minecraft launcher for anyone to use.

FEATURES
--------
- GUI mode for browsing and managing instances.
- Headless instance launching via desktop shortcuts (--instance <instance-name>).
- Fabric, NeoForge, and Forge installer support.
- Automatic Java/runtime downloads through the launcher's existing runtime system.
- Tabbed UI: Play, Install, Modrinth, Server, and Logs.
- Store-style Modrinth browser for compatible mods, shaders, and resource packs.
- Per-instance Minecraft version, username, RAM, loader, loader build, and OptiFine settings.
- Windows EXE builds through GitHub Actions.

INSTALLATION
------------
Download the Windows EXE from a GitHub Actions artifact or a tagged GitHub release.

The launcher needs an internet connection when downloading Minecraft versions,
libraries, loaders, Java runtimes, or Modrinth content for the first time.

USAGE
-----
Use the Play tab to create and launch isolated instances.

Use the Install tab to:
- choose an existing instance and install Fabric, NeoForge, or Forge; or
- choose "+ New instance", select a Minecraft version and loader, and let
  BlemmLauncher create and install the complete instance.

Use the Modrinth tab as the built-in store. Select the destination instance,
search for a project, and press Install.

The Server tab currently displays "Coming soon…" as a placeholder.

PROJECT STRUCTURE
-----------------
run.py                    - Entry point and Windows elevation handling.
blemmlauncher/             - Launcher core, GUI, instances, and version tools.
.github/workflows/build.yml - GitHub Actions Windows EXE build.

NOTES
-----
Fabric installation creates the minimal launcher profile required by the
headless Fabric client installer. Loader installation reports installer
output when a version is not created, making failed installations easier
to diagnose.
