# You can check this for malware yourself:
"https://www.virustotal.com/gui/url-analysis/u-8bdb66629b45530f013d216e724ee7e8d188e617679eae28f273f3bb67a7388f-63ba47c8"

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
- Minecraft server creation and management with automatic Java and server software downloads.
- Server console with live output and command input.
- Server file browser, editor, and file import tools.
- Owner developer tools for remotely managing the Survival server.
- Windows EXE builds through GitHub Actions.

INSTALLATION
------------
Download the Windows EXE from a GitHub Actions artifact or a tagged GitHub release.

The launcher needs an internet connection when downloading Minecraft versions,
libraries, loaders, Java runtimes, server software, or Modrinth content for the first time.

BlemmLauncher stores packaged Windows launcher data in the user's Roaming
application data folder instead of inside the installed program files.

MINECRAFT DATA LOCATION
-----------------------
For an installed Windows build, Minecraft data is stored at:

C:\Users\<YourName>\AppData\Roaming\BlemmLauncher\minecraft\

Server files are stored at:

C:\Users\<YourName>\AppData\Roaming\BlemmLauncher\minecraft\servers\

For example, the Survival server is:

C:\Users\<YourName>\AppData\Roaming\BlemmLauncher\minecraft\servers\Survival\

This location contains the actual server files, including the server jar,
world data, configuration files, logs, plugins, mods, and other files created
by the server.

Older packaged installations that stored data under the launcher's _internal
folder can be migrated automatically to the Roaming location when the launcher
starts.

USAGE
-----
Use the Play tab to create and launch isolated Minecraft instances.

Each instance has its own Minecraft files, settings, mods, loader files, and
other instance-specific data. This keeps separate installations from
interfering with each other.

Use the Install tab to:
- choose an existing instance and install Fabric, NeoForge, or Forge; or
- choose "+ New instance", select a Minecraft version and loader, and let
  BlemmLauncher create and install the complete instance.

Use the Profile tab to choose the Minecraft username used by local/offline
launches.

SERVERS
-------
The Server tab is used to create and manage Minecraft servers.

When creating a server, choose:
- a server name;
- server software such as Vanilla, Paper, Fabric, Forge, or NeoForge;
- a Minecraft version;
- the amount of RAM to allocate.

BlemmLauncher downloads the selected server software and automatically
installs the required Java runtime when needed. A progress bar shows the
installation and download progress.

The Server Management window lets you:
- start, stop, and restart servers;
- view live server console output;
- send commands directly to the running server;
- browse server files and folders;
- edit text files;
- create, rename, and delete files and folders;
- import files from Windows File Explorer;
- delete a server and all of its files.

The developer-reserved server name "Survival" can be used by the developer
and owner server-management tools. Normal server creation does not use
reserved developer names.

MODRINTH
--------
The Modrinth tab works as a built-in project browser.

Choose an instance, Minecraft version, and project type, then search for
compatible Modrinth projects. BlemmLauncher can display project artwork,
titles, authors, download counts, and descriptions.

The Discover page can also show popular compatible projects for the selected
Minecraft version and loader.

Supported project types include mods, modpacks, shaders, resource packs,
datapacks, and worlds when supported by the selected instance and Minecraft
version.

Select a project and press Install to download it through Modrinth and place
it into the appropriate location for the selected instance.

MANUALLY UPLOADING FILES TO INSTANCES
-------------------------------------
If you want to manually add a file to a Minecraft instance, open the instance
data folder and place the file in the appropriate directory.

The launcher stores its Minecraft data under:

C:\Users\<YourName>\AppData\Roaming\BlemmLauncher\minecraft\

Instances are located inside the launcher's instance directory. The exact
instance folder is based on the instance name shown in BlemmLauncher.

For example, a mod normally belongs in that instance's "mods" folder, while a
resource pack normally belongs in "resourcepacks". Shaders normally belong in
"shaderpacks" when the selected loader and Minecraft version support them.

You can also use the launcher's file management features where available.
For server files, use Server Management -> Import to open Windows File
Explorer, select a file, and copy it directly into the server folder currently
being viewed.

When manually uploading files, make sure the file is compatible with the
Minecraft version and loader used by the instance. Do not place client-only
mods into a server unless they are designed for server use.

PROJECT STRUCTURE
-----------------
run.py                     - Entry point and Windows elevation handling.
blemmlauncher/             - Launcher core, GUI, instances, server, and updater tools.
Dev/                       - Developer authentication and remote server agent tools.
.github/workflows/build.yml - GitHub Actions Windows EXE and release build.
installer.iss              - Inno Setup installer configuration.

NOTES
-----
Fabric installation creates the minimal launcher profile required by the
headless Fabric client installer. Loader installation reports installer
output when a version is not created, making failed installations easier to
diagnose.

The launcher checks the GitHub releases page for newer BlemmLauncher releases.
When a newer release with an installer is available, the launcher can prompt
the user to install the update.
