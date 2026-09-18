```python
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

from . import core, instances


BG = "#1e1f24"
PANEL = "#272930"
FIELD = "#2f323b"
FG = "#e8e9ee"
MUTED = "#8b8fa3"
ACCENT = "#4ade80"
DANGER = "#f87171"


def style_dark(root):
    style = ttk.Style()

    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        ".",
        background=BG,
        foreground=FG,
        fieldbackground=FIELD,
        bordercolor=PANEL,
        lightcolor=PANEL,
        darkcolor=PANEL,
        troughcolor=FIELD,
        arrowcolor=MUTED,
    )

    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=PANEL)

    style.configure(
        "TLabel",
        background=BG,
        foreground=FG,
    )

    style.configure(
        "Muted.TLabel",
        background=BG,
        foreground=MUTED,
    )

    style.configure(
        "MutedP.TLabel",
        background=PANEL,
        foreground=MUTED,
    )

    style.configure(
        "Title.TLabel",
        background=BG,
        foreground=ACCENT,
        font=("Segoe UI", 18, "bold"),
    )

    style.configure(
        "TEntry",
        foreground=FG,
        insertcolor=FG,
        padding=4,
    )

    style.configure(
        "TCombobox",
        foreground=FG,
        padding=4,
    )

    style.map(
        "TCombobox",
        fieldbackground=[("readonly", FIELD)],
    )

    style.configure(
        "Inst.TButton",
        background=FIELD,
        foreground=FG,
        padding=6,
        width=13,
    )

    style.map(
        "Inst.TButton",
        background=[("active", "#3a3e49")],
    )

    style.configure(
        "Play.TButton",
        background=ACCENT,
        foreground="#10240f",
        font=("Segoe UI", 12, "bold"),
        padding=(30, 10),
    )

    style.map(
        "Play.TButton",
        background=[
            ("active", "#6ce89a"),
            ("disabled", "#39543f"),
        ],
    )

    style.configure(
        "TButton",
        background=FIELD,
        foreground=FG,
        padding=6,
    )

    style.map(
        "TButton",
        background=[("active", "#3a3e49")],
    )

    style.configure(
        "TCheckbutton",
        background=PANEL,
        foreground=FG,
    )

    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=FIELD,
        thickness=10,
    )

    root.configure(bg=BG)


class App:
    def __init__(self, root):
        self.root = root

        root.title("BlemmLauncher")
        root.geometry("860x600")
        root.minsize(760, 540)

        style_dark(root)

        self.q = queue.Queue()
        self.sel = None
        self.version_map = {}

        # ------------------------------------------------------------
        # Header
        # ------------------------------------------------------------

        head = ttk.Frame(root)
        head.pack(fill="x", padx=14, pady=(10, 2))

        ttk.Label(
            head,
            text="◈ BlemmLauncher",
            style="Title.TLabel",
        ).pack(side="left")

        ttk.Label(
            head,
            text="instances · loaders · modrinth · import/export",
            style="Muted.TLabel",
        ).pack(side="left", padx=10, pady=(10, 0))

        # ------------------------------------------------------------
        # Main body
        # ------------------------------------------------------------

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=14, pady=8)

        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ------------------------------------------------------------
        # Instance list
        # ------------------------------------------------------------

        left = ttk.Frame(
            body,
            style="Card.TFrame",
            padding=8,
        )

        left.grid(
            row=0,
            column=0,
            sticky="ns",
            padx=(0, 10),
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
            font=("Segoe UI", 11),
        )

        self.ilist.pack(fill="y")
        self.ilist.bind("<<ListboxSelect>>", self._sel_ev)

        bb = ttk.Frame(
            left,
            style="Card.TFrame",
        )

        bb.pack(
            fill="x",
            pady=(8, 0),
        )

        buttons = [
            ("＋ New", self.new_inst),
            ("⭳ Import", self.import_inst),
            ("⭱ Export", self.export_inst),
            ("✂ Shortcut", self.make_shortcut),
            ("🗑 Delete", self.del_inst),
        ]

        for i, (text, command) in enumerate(buttons):
            ttk.Button(
                bb,
                text=text,
                style="Inst.TButton",
                command=command,
            ).grid(
                row=i // 2,
                column=i % 2,
                sticky="we",
                pady=2,
                padx=2,
            )

        bb.columnconfigure(0, weight=1)
        bb.columnconfigure(1, weight=1)

        # ------------------------------------------------------------
        # Right side
        # ------------------------------------------------------------

        right = ttk.Frame(
            body,
            style="Card.TFrame",
            padding=16,
        )

        right.grid(
            row=0,
            column=1,
            sticky="nsew",
        )

        right.columnconfigure(1, weight=1)

        self.i_title = ttk.Label(
            right,
            text="pick or create an instance →",
            style="Title.TLabel",
        )

        self.i_title.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6),
        )

        self.i_info = ttk.Label(
            right,
            text="",
            style="MutedP.TLabel",
            justify="left",
            anchor="w",
        )

        self.i_info.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )

        # ------------------------------------------------------------
        # Settings
        # ------------------------------------------------------------

        settings = ttk.Frame(
            right,
            style="Card.TFrame",
        )

        settings.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
        )

        ttk.Label(
            settings,
            text="Username:",
            style="MutedP.TLabel",
        ).pack(side="left")

        self._uname = tk.StringVar(value="Blemm")

        ttk.Entry(
            settings,
            textvariable=self._uname,
            width=16,
        ).pack(
            side="left",
            padx=(6, 14),
        )

        ttk.Label(
            settings,
            text="RAM:",
            style="MutedP.TLabel",
        ).pack(side="left")

        self._ram = tk.StringVar(value="4G")

        ttk.Combobox(
            settings,
            textvariable=self._ram,
            values=["2G", "4G", "6G", "8G"],
            width=6,
            state="readonly",
        ).pack(
            side="left",
            padx=6,
        )

        # ------------------------------------------------------------
        # OptiFine
        # ------------------------------------------------------------

        self._optifine = tk.BooleanVar(value=False)

        self.optifine_check = ttk.Checkbutton(
            settings,
            text="Use OptiFine",
            variable=self._optifine,
            command=self._save_optifine_setting,
        )

        self.optifine_check.pack(
            side="left",
            padx=(14, 4),
        )

        ttk.Button(
            settings,
            text="Install OptiFine…",
            command=self.install_optifine,
        ).pack(
            side="left",
            padx=(4, 0),
        )

        # ------------------------------------------------------------
        # Play button
        # ------------------------------------------------------------

        self.play_btn = ttk.Button(
            right,
            text="▶   PLAY",
            style="Play.TButton",
            command=self.play,
            state="disabled",
        )

        self.play_btn.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="we",
            pady=(12, 6),
        )

        # ------------------------------------------------------------
        # Modrinth
        # ------------------------------------------------------------

        ttk.Button(
            right,
            text="🔎 Browse & install (Modrinth) — mods / shaders / packs",
            command=self.browse_mods,
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
        )

        # ------------------------------------------------------------
        # Manual file installation
        # ------------------------------------------------------------

        ttk.Button(
            right,
            text="＋ add files… (Ctrl+click several: mods, packs, shaders)",
            command=self.add_file,
        ).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )

        # ------------------------------------------------------------
        # Status
        # ------------------------------------------------------------

        self.status = ttk.Label(
            root,
            text="Loading version list…",
            anchor="w",
        )

        self.status.pack(
            fill="x",
            padx=14,
        )

        self.bar = ttk.Progressbar(
            root,
            mode="indeterminate",
        )

        self.bar.pack(
            fill="x",
            padx=14,
            pady=(2, 6),
        )

        # ------------------------------------------------------------
        # Log
        # ------------------------------------------------------------

        logcard = ttk.Frame(
            root,
            style="Card.TFrame",
            padding=6,
        )

        logcard.pack(
            fill="both",
            expand=True,
            padx=14,
            pady=(0, 10),
        )

        self.log = scrolledtext.ScrolledText(
            logcard,
            height=6,
            state="disabled",
            font=("Consolas", 9),
            bg=FIELD,
            fg=FG,
            insertbackground=FG,
            relief="flat",
        )

        self.log.pack(
            fill="both",
            expand=True,
        )

        # ------------------------------------------------------------
        # Start
        # ------------------------------------------------------------

        self.root.after(100, self._drain)

        threading.Thread(
            target=self._load_versions,
            daemon=True,
        ).start()

        self._refresh_list()

    # ================================================================
    # Versions
    # ================================================================

    def _load_versions(self):
        try:
            versions, latest, _ = core.list_versions()

            def sk(version):
                try:
                    return [
                        int(x)
                        for x in version.split(".")
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
                    and not v.startswith(("w", "pre", "rc"))
                ],
                key=sk,
                reverse=True,
            )

            self.q.put(("versions", chosen))

        except Exception as e:
            self.q.put(
                ("error", f"version list failed: {e}")
            )

    # ================================================================
    # Instance list
    # ================================================================

    def _refresh_list(self):
        self.ilist.delete(0, "end")

        for name in instances.list_instances():
            self.ilist.insert("end", name)

        self.sel = None
        self.play_btn.config(state="disabled")

    def _sel_ev(self, _=None):
        selection = self.ilist.curselection()

        if not selection:
            return

        name = self.ilist.get(selection[0])
        cfg = instances.load_cfg(name)

        self.sel = name
        self.version = cfg["version"]
        self.loader = cfg.get("loader")

        self._uname.set(
            cfg.get("username", "Blemm")
        )

        self._ram.set(
            cfg.get("ram", "4G")
        )

        self._optifine.set(
            bool(cfg.get("optifine", False))
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
        directory = os.path.join(
            instances.instance_dir(name),
            "mods",
        )

        if os.path.isdir(directory):
            return len(os.listdir(directory))

        return 0

    # ================================================================
    # OptiFine
    # ================================================================

    def _save_optifine_setting(self):
        if not self.sel:
            return

        try:
            cfg = instances.load_cfg(self.sel)
            cfg["optifine"] = bool(
                self._optifine.get()
            )
            instances.save_cfg(
                self.sel,
                cfg,
            )

        except Exception:
            pass

    def install_optifine(self):
        if not self.sel:
            messagebox.showinfo(
                "BlemmLauncher",
                "Select an instance first.",
            )
            return

        cfg = instances.load_cfg(self.sel)
        loader = cfg.get("loader")

        if loader not in ("forge", "neoforge"):
            messagebox.showinfo(
                "OptiFine",
                "For this launcher, OptiFine is installed as a mod.\n\n"
                "Create/select a Forge or NeoForge instance, then "
                "use Install OptiFine… again.",
            )
            return

        path = filedialog.askopenfilename(
            title="Select your OptiFine installer",
            filetypes=[
                ("OptiFine installer", "*.jar"),
                ("Java files", "*.jar"),
                ("All files", "*.*"),
            ],
        )

        if not path:
            return

        name = self.sel

        self.play_btn.config(
            state="disabled"
        )

        self.status.config(
            text="Installing OptiFine…",
            foreground=FG,
        )

        def worker():
            try:
                cfg = instances.load_cfg(name)

                instances.use(
                    name,
                    core,
                )

                installed = core.install_optifine(
                    path,
                    with_forge=True,
                    version_id=cfg["version"],
                )

                cfg["optifine"] = True

                instances.save_cfg(
                    name,
                    cfg,
                )

                self.q.put(
                    (
                        "optifine_installed",
                        installed,
                    )
                )

            except Exception as e:
                self.q.put(
                    (
                        "error",
                        f"OptiFine installation failed:\n{e}",
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    # ================================================================
    # New instance
    # ================================================================

    def new_inst(self):
        d = tk.Toplevel(self.root)

        d.title("New instance")
        d.configure(bg=BG)
        d.geometry("380x260")

        style_dark(d)

        f = ttk.Frame(
            d,
            style="Card.TFrame",
            padding=14,
        )

        f.pack(
            fill="both",
            expand=True,
        )

        name = tk.StringVar()
        version = tk.StringVar(value="release")
        loader = tk.StringVar(value="vanilla")
        ram = tk.StringVar(value="4G")
        uname = tk.StringVar(value="Blemm")

        rows = [
            (
                "Name:",
                ttk.Entry(
                    f,
                    textvariable=name,
                ),
            ),
            (
                "Version:",
                ttk.Combobox(
                    f,
                    textvariable=version,
                    values=["release"],
                ),
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
                        "neoforge",
                    ],
                ),
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
                        "8G",
                    ],
                ),
            ),
            (
                "Username:",
                ttk.Entry(
                    f,
                    textvariable=uname,
                ),
            ),
        ]

        for r, (label, widget) in enumerate(rows):
            ttk.Label(
                f,
                text=label,
                style="MutedP.TLabel",
            ).grid(
                row=r,
                column=0,
                sticky="w",
                pady=3,
            )

            widget.grid(
                row=r,
                column=1,
                sticky="we",
                pady=3,
                padx=(8, 0),
            )

        f.columnconfigure(
            1,
            weight=1,
        )

        def fill_versions():
            try:
                versions, _, _ = core.list_versions()

                def sk(version):
                    try:
                        return [
                            int(x)
                            for x in version.split(".")
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
                    reverse=True,
                )

                widget = f.grid_slaves(
                    row=1,
                    column=1,
                )[0]

                widget.config(
                    values=["release"] + chosen[:60]
                )

            except Exception:
                pass

        threading.Thread(
            target=fill_versions,
            daemon=True,
        ).start()

        def go():
            nm = name.get().strip()

            if not nm:
                nm = "New Instance"

            v = version.get()

            if v == "release":
                try:
                    v = core.manifest()["latest"]["release"]

                except Exception:
                    messagebox.showerror(
                        "Blemm",
                        "couldn't resolve 'release' - "
                        "type a specific version",
                        parent=d,
                    )
                    return

            ld = loader.get()

            if ld == "vanilla":
                ld = None

            try:
                instances.create(
                    nm,
                    v,
                    ld,
                    ram.get(),
                    uname.get(),
                )

                d.destroy()
                self._refresh_list()

            except Exception as e:
                messagebox.showerror(
                    "Blemm",
                    str(e),
                    parent=d,
                )

        ttk.Button(
            f,
            text="Create",
            style="Play.TButton",
            command=go,
        ).grid(
            row=len(rows),
            column=0,
            columnspan=2,
            sticky="we",
            pady=(10, 0),
        )

    # ================================================================
    # Delete
    # ================================================================

    def del_inst(self):
        if not self.sel:
            return

        if messagebox.askyesno(
            "Blemm",
            f"Delete instance '{self.sel}'?\n"
            "(saves are deleted too!)",
        ):
            instances.delete(
                self.sel
            )

            self._refresh_list()

    # ================================================================
    # Export
    # ================================================================

    def export_inst(self):
        if not self.sel:
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            initialfile=f"{self.sel}.zip",
        )

        if not path:
            return

        try:
            instances.export(
                self.sel,
                path,
            )

            self.status.config(
                text=f"exported → {path}",
                foreground=ACCENT,
            )

        except Exception as e:
            messagebox.showerror(
                "Blemm",
                str(e),
            )

    # ================================================================
    # Import
    # ================================================================

    def import_inst(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Instance zip", "*.zip")
            ]
        )

        if not path:
            return

        try:
            name = instances.import_from_zip(
                path
            )

            self._refresh_list()

            self.status.config(
                text=f"imported {name}",
                foreground=ACCENT,
            )

        except Exception as e:
            messagebox.showerror(
                "Blemm",
                str(e),
            )

    # ================================================================
    # Shortcut
    # ================================================================

    def make_shortcut(self):
        if not self.sel:
            return

        try:
            path = instances.shortcut(
                self.sel
            )

            self.status.config(
                text=f"shortcut → {path}",
                foreground=ACCENT,
            )

        except Exception as e:
            messagebox.showerror(
                "Blemm",
                str(e),
            )

    # ================================================================
    # Add files manually
    # ================================================================

    def add_file(self):
        if not self.sel:
            return

        paths = filedialog.askopenfilenames(
            title="Pick mods / packs (Ctrl+click for several)",
            filetypes=[
                (
                    "Minecraft files",
                    "*.jar *.zip",
                ),
                (
                    "All files",
                    "*.*",
                ),
            ],
        )

        if not paths:
            return

        try:
            core.set_game_dir(
                instances.instance_dir(
                    self.sel
                )
            )

            added = core.add_content_auto(
                paths
            )

            self.status.config(
                text=", ".join(added),
                foreground=ACCENT,
            )

            self._sel_ev()

        except Exception as e:
            messagebox.showerror(
                "Blemm",
                str(e),
            )

    # ================================================================
    # Modrinth browser
    # ================================================================

    def browse_mods(self):
        if not self.sel:
            return

        d = tk.Toplevel(self.root)

        d.title(
            f"Modrinth — {self.sel}"
        )

        d.configure(bg=BG)

        style_dark(d)

        d.geometry(
            "600x460"
        )

        f = ttk.Frame(
            d,
            style="Card.TFrame",
            padding=10,
        )

        f.pack(
            fill="both",
            expand=True,
        )

        top = ttk.Frame(
            f,
            style="Card.TFrame",
        )

        top.pack(
            fill="x"
        )

        q = tk.StringVar()

        ttk.Entry(
            top,
            textvariable=q,
        ).pack(
            side="left",
            fill="x",
            expand=True,
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
                "resourcepack",
            ],
        ).pack(
            side="left",
            padx=6,
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
            exportselection=False,
        )

        results.pack(
            fill="both",
            expand=True,
            pady=8,
        )

        mid = ttk.Frame(
            f,
            style="Card.TFrame",
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
            style="MutedP.TLabel",
        )

        lbl.pack(
            anchor="w",
            pady=(6, 0),
        )

        hits = []

        def search():
            nonlocal hits

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
                    ptype.get(),
                )

                results.delete(
                    0,
                    "end",
                )

                for h in hits:
                    results.insert(
                        "end",
                        f'{h["title"]} — '
                        f'{h["author"]} '
                        f'({h["downs"]}↓)',
                    )

                lbl.config(
                    text=(
                        f"{len(hits)} results for "
                        f"{self.version} / "
                        f"{ptype.get()}"
                        + (
                            f" / {ld}"
                            if ld
                            else ""
                        )
                    ),
                    foreground=FG,
                )

            except Exception as e:
                lbl.config(
                    text=f"search failed: {e}",
                    foreground=DANGER,
                )

        def install():
            selection = results.curselection()

            if not selection:
                return

            ok = []
            errs = []

            for i in selection:
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

                    filename = instances.modrinth_install(
                        h["id"],
                        self.version,
                        ld,
                        ptype.get(),
                    )

                    ok.append(filename)

                except Exception as e:
                    errs.append(
                        f'{h["title"]}: {e}'
                    )

            msg = ""

            if ok:
                msg = (
                    f"installed {len(ok)}: "
                    f"{', '.join(ok)}"
                )

            if errs:
                if msg:
                    msg += "\n"

                msg += (
                    "failed: "
                    + "; ".join(errs)
                )

            lbl.config(
                text=msg,
                foreground=(
                    ACCENT
                    if ok and not errs
                    else DANGER
                ),
            )

            self._sel_ev()

        ttk.Button(
            top,
            text="Search",
            command=search,
        ).pack(
            side="left",
            padx=6,
        )

        ttk.Button(
            mid,
            text="⬇  Install selected",
            style="Play.TButton",
            command=install,
        ).pack(
            side="left"
        )

    # ================================================================
    # Play
    # ================================================================

    def play(self):
        if not self.sel:
            return

        self.play_btn.config(
            state="disabled",
            text="Working…",
        )

        self.bar.config(
            mode="indeterminate"
        )

        self.bar.start(20)

        self.status.config(
            text="Preparing…",
            foreground=FG,
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
                    core,
                )

                self.q.put(
                    (
                        "stage",
                        "Preparing instance…",
                        None,
                        None,
                    )
                )

                vid = cfg["version"]
                loader = cfg.get("loader")

                if loader == "forge":
                    vid = core.install_forge(
                        vid,
                        cfg.get("loader_build"),
                    )

                elif loader == "neoforge":
                    build = instances.install_neoforge(
                        vid,
                        cfg.get("loader_build"),
                    )

                    cfg["loader_build"] = build

                    instances.save_cfg(
                        name,
                        cfg,
                    )

                elif loader == "fabric":
                    build = instances.install_fabric(
                        vid
                    )

                    cfg.setdefault(
                        "loader_build",
                        build,
                    )

                    instances.save_cfg(
                        name,
                        cfg,
                    )

                self.q.put(
                    (
                        "msg",
                        f"launching {name}: {vid}",
                    )
                )

                core.launch(
                    vid,
                    self._uname.get() or "Blemm",
                    self._ram.get(),
                    optifine=bool(
                        self._optifine.get()
                    ),
                )

                core.set_reporter(
                    None
                )

                self.q.put(
                    (
                        "done",
                        f"played {name} ♥",
                    )
                )

            except SystemExit as e:
                core.set_reporter(None)

                self.q.put(
                    (
                        "error",
                        f"aborted: {e}",
                    )
                )

            except Exception as e:
                core.set_reporter(None)

                self.q.put(
                    (
                        "error",
                        str(e),
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    # ================================================================
    # Queue / UI updates
    # ================================================================

    def _drain(self):
        try:
            while True:
                kind, *data = self.q.get_nowait()

                if kind == "stage":
                    text_value, done, total = data

                    if total:
                        self.status.config(
                            text=(
                                f"{text_value} "
                                f"({done:,} / {total:,})"
                            ),
                            foreground=FG,
                        )

                        self.bar.config(
                            mode="determinate",
                            value=(
                                done / total * 100
                            ),
                        )

                    else:
                        self.status.config(
                            text=text_value,
                            foreground=FG,
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
                        foreground=MUTED,
                    )

                elif kind == "msg":
                    self.log.config(
                        state="normal"
                    )

                    self.log.insert(
                        "end",
                        data[0] + "\n",
                    )

                    self.log.see("end")

                    self.log.config(
                        state="disabled"
                    )

                elif kind == "optifine_installed":
                    installed = data[0]

                    self._optifine.set(
                        True
                    )

                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY",
                    )

                    self.status.config(
                        text=(
                            "OptiFine installed: "
                            + os.path.basename(installed)
                        ),
                        foreground=ACCENT,
                    )

                    self.log.config(
                        state="normal"
                    )

                    self.log.insert(
                        "end",
                        "OptiFine installed: "
                        + installed
                        + "\n",
                    )

                    self.log.see("end")

                    self.log.config(
                        state="disabled"
                    )

                    self._sel_ev()

                elif kind == "done":
                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY",
                    )

                    self.bar.stop()

                    self.bar.config(
                        mode="determinate",
                        value=100,
                    )

                    self.status.config(
                        text=data[0],
                        foreground=ACCENT,
                    )

                elif kind == "error":
                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY",
                    )

                    self.bar.stop()

                    self.bar.config(
                        mode="determinate",
                        value=0,
                    )

                    self.status.config(
                        text="Failed — see log",
                        foreground=DANGER,
                    )

                    self.log.config(
                        state="normal"
                    )

                    self.log.insert(
                        "end",
                        f"ERROR: {data[0]}\n",
                    )

                    self.log.see("end")

                    self.log.config(
                        state="disabled"
                    )

        except queue.Empty:
            pass

        self.root.after(
            100,
            self._drain,
        )


def run():
    root = tk.Tk()
    App(root)
    root.mainloop()
```
