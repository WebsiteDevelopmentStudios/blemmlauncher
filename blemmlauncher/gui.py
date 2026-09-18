"""BlemmLauncher GUI - dark, threaded, instance-aware."""

import os
import threading
import queue

import tkinter as tk
from tkinter import (
    ttk,
    filedialog,
    scrolledtext,
    messagebox
)

from . import core, instances


BG = "#1e1f24"
PANEL = "#272930"
FIELD = "#2f323b"
FG = "#e8e9ee"
MUTED = "#8b8fa3"
ACCENT = "#4ade80"
DANGER = "#f87171"


def style_dark(root):
    s = ttk.Style()

    try:
        s.theme_use("clam")
    except Exception:
        pass

    s.configure(
        ".",
        background=BG,
        foreground=FG,
        fieldbackground=FIELD,
        bordercolor=PANEL,
        lightcolor=PANEL,
        darkcolor=PANEL,
        troughcolor=FIELD,
        arrowcolor=MUTED
    )

    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=PANEL)

    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("MutedP.TLabel", background=PANEL, foreground=MUTED)

    s.configure(
        "Title.TLabel",
        background=BG,
        foreground=ACCENT,
        font=("Segoe UI", 18, "bold")
    )

    s.configure("TEntry", foreground=FG, insertcolor=FG, padding=4)
    s.configure("TCombobox", foreground=FG, padding=4)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD)])

    s.configure(
        "Inst.TButton",
        background=FIELD,
        foreground=FG,
        padding=6,
        width=13
    )
    s.map("Inst.TButton", background=[("active", "#3a3e49")])

    s.configure(
        "Play.TButton",
        background=ACCENT,
        foreground="#10240f",
        font=("Segoe UI", 12, "bold"),
        padding=(30, 10)
    )
    s.map(
        "Play.TButton",
        background=[
            ("active", "#6ce89a"),
            ("disabled", "#39543f")
        ]
    )

    s.configure("TButton", background=FIELD, foreground=FG, padding=6)
    s.map("TButton", background=[("active", "#3a3e49")])

    s.configure("TCheckbutton", background=PANEL, foreground=FG)

    s.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=FIELD,
        thickness=10
    )

    root.configure(bg=BG)


class App:

    def __init__(self, root):
        self.root = root

        root.title("BlemmLauncher")
        root.geometry("880x620")
        root.minsize(780, 560)

        style_dark(root)

        self.q = queue.Queue()
        self.sel = None
        self.version = None
        self.loader = None
        self._all_versions = []

        self._optifine = tk.BooleanVar(value=False)

        # ------------------------------------------------------------
        # Header
        # ------------------------------------------------------------

        head = ttk.Frame(root)
        head.pack(fill="x", padx=14, pady=(10, 2))

        ttk.Label(
            head,
            text="◈ BlemmLauncher",
            style="Title.TLabel"
        ).pack(side="left")

        ttk.Label(
            head,
            text="instances · loaders · modrinth · hack clients · import/export",
            style="Muted.TLabel"
        ).pack(side="left", padx=10, pady=(10, 0))

        # ------------------------------------------------------------
        # Body
        # ------------------------------------------------------------

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=14, pady=8)

        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left column: instance list + buttons ----------------------

        left = ttk.Frame(body, style="Card.TFrame", padding=8)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        self.ilist = tk.Listbox(
            left,
            width=26,
            bg=FIELD,
            fg=FG,
            relief="flat",
            highlightthickness=0,
            selectbackground=ACCENT,
            selectforeground="#10240f",
            font=("Segoe UI", 11)
        )

        self.ilist.pack(fill="y")
        self.ilist.bind("<<ListboxSelect>>", self._sel_ev)

        bb = ttk.Frame(left, style="Card.TFrame")
        bb.pack(fill="x", pady=(8, 0))

        buttons = [
            ("＋ New", self.new_inst),
            ("⭳ Import", self.import_inst),
            ("⬉ Client…", self.import_client_dialog),
            ("⭱ Export", self.export_inst),
            ("✂ Shortcut", self.make_shortcut),
            ("🗑 Delete", self.del_inst)
        ]

        for i, (text, command) in enumerate(buttons):
            ttk.Button(
                bb,
                text=text,
                style="Inst.TButton",
                command=command
            ).grid(
                row=i // 2,
                column=i % 2,
                sticky="we",
                pady=2,
                padx=2
            )

        bb.columnconfigure(0, weight=1)
        bb.columnconfigure(1, weight=1)

        # Right column: selected instance controls ------------------

        right = ttk.Frame(body, style="Card.TFrame", padding=16)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        self.i_title = ttk.Label(
            right,
            text="pick or create an instance →",
            style="Title.TLabel"
        )

        self.i_title.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6)
        )

        self.i_info = ttk.Label(
            right,
            text="",
            style="MutedP.TLabel",
            justify="left",
            anchor="w"
        )

        self.i_info.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8)
        )

        # Settings row: username / RAM / OptiFine -------------------

        settings = ttk.Frame(right, style="Card.TFrame")
        settings.grid(row=2, column=0, columnspan=2, sticky="w")

        ttk.Label(
            settings,
            text="Username:",
            style="MutedP.TLabel"
        ).pack(side="left")

        self._uname = tk.StringVar(value="Blemm")

        ttk.Entry(
            settings,
            textvariable=self._uname,
            width=14
        ).pack(side="left", padx=(6, 12))

        ttk.Label(settings, text="RAM:", style="MutedP.TLabel").pack(
            side="left"
        )

        self._ram = tk.StringVar(value="4G")

        ttk.Combobox(
            settings,
            textvariable=self._ram,
            values=["2G", "4G", "6G", "8G"],
            width=5,
            state="readonly"
        ).pack(side="left", padx=6)

        self.optifine_check = ttk.Checkbutton(
            settings,
            text="Use OptiFine",
            variable=self._optifine,
            command=self._save_optifine_setting
        )

        self.optifine_check.pack(side="left", padx=(14, 2))

        ttk.Button(
            settings,
            text="Install OptiFine…",
            command=self.install_optifine
        ).pack(side="left", padx=(2, 0))

        # Play ------------------------------------------------------

        self.play_btn = ttk.Button(
            right,
            text="▶   PLAY",
            style="Play.TButton",
            command=self.play,
            state="disabled"
        )

        self.play_btn.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="we",
            pady=(12, 6)
        )

        ttk.Label(
            right,
            text=(
                "Import hack clients / custom JARs with 'Client…' on the left. "
                "OptiFine: use the installer JAR or drop a JAR in mods/."
            ),
            style="MutedP.TLabel"
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6)
        )

        ttk.Button(
            right,
            text="🔎 Browse & install (Modrinth) — mods / shaders / packs",
            command=self.browse_mods
        ).grid(row=5, column=0, columnspan=2, sticky="w")

        ttk.Button(
            right,
            text="＋ add files… (Ctrl+click several: mods, packs, shaders)",
            command=self.add_file
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0)
        )

        # Status / progress ------------------------------------------

        self.status = ttk.Label(
            root,
            text="Loading version list…",
            anchor="w"
        )

        self.status.pack(fill="x", padx=14)

        self.bar = ttk.Progressbar(root, mode="indeterminate")
        self.bar.pack(fill="x", padx=14, pady=(2, 6))

        # Log -------------------------------------------------------

        logcard = ttk.Frame(root, style="Card.TFrame", padding=6)
        logcard.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.log = scrolledtext.ScrolledText(
            logcard,
            height=6,
            state="disabled",
            font=("Consolas", 9),
            bg=FIELD,
            fg=FG,
            insertbackground=FG,
            relief="flat"
        )

        self.log.pack(fill="both", expand=True)

        # Startup ---------------------------------------------------

        core.set_reporter(self._on_report)

        self.root.after(100, self._drain)

        threading.Thread(target=self._load_versions, daemon=True).start()

        self._refresh_list()

    # ================================================================
    # Reporter (called from worker threads - only queues, never widgets)
    # ================================================================

    def _on_report(self, kind, text, done=None, total=None):
        self.q.put((kind, text, done, total))

    # ================================================================
    # Version list
    # ================================================================

    def _load_versions(self):
        try:
            versions, latest, _ = core.list_versions()

            def sk(v):
                try:
                    return [int(x) for x in v.split(".") if x.isdigit()]
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
                reverse=True
            )

            self.q.put(("versions", chosen, latest, None))

        except Exception as e:
            self.q.put(
                ("error", "version list failed: " + str(e), None, None)
            )

    # ================================================================
    # Instance list
    # ================================================================

    def _refresh_list(self):
        self.ilist.delete(0, "end")

        for name in instances.list_instances():
            self.ilist.insert("end", name)

        self.sel = None
        self.version = None
        self.loader = None

        self._optifine.set(False)

        self.play_btn.config(state="disabled")

    def _select_instance(self, name):
        """Programmatically select + focus an instance in the list."""

        names = self.ilist.get(0, "end")

        if name in names:
            idx = list(names).index(name)
            self.ilist.selection_clear(0, "end")
            self.ilist.selection_set(idx)
            self.ilist.activate(idx)
            self.ilist.see(idx)
            self._sel_ev()

    def _sel_ev(self, _=None):
        selection = self.ilist.curselection()

        if not selection:
            return

        name = self.ilist.get(selection[0])

        try:
            cfg = instances.load_cfg(name)
        except Exception as e:
            messagebox.showerror(
                "BlemmLauncher",
                "Could not load instance '" + name + "':\n" + str(e)
            )
            return

        # Point core at this instance BEFORE anything else touches
        # files, so mods / downloads / OptiFine all land here.

        try:
            instances.use(name, core)
        except Exception as e:
            messagebox.showerror(
                "BlemmLauncher",
                "Could not open instance '" + name + "':\n" + str(e)
            )
            return

        self.sel = name
        self.version = cfg["version"]
        self.loader = cfg.get("loader")

        self._uname.set(cfg.get("username", "Blemm"))
        self._ram.set(cfg.get("ram", "4G"))
        self._optifine.set(bool(cfg.get("optifine", False)))

        self.i_title.config(text=name)

        self.i_info.config(
            text=(
                "version: " + str(cfg["version"]) + "    "
                "loader: " + str(cfg.get("loader") or "vanilla") + "\n"
                "ram: " + str(cfg.get("ram")) + "    "
                "optifine: " + ("on" if cfg.get("optifine") else "off")
                + "    "
                "mods: " + str(self._count_mods(name))
            )
        )

        self.play_btn.config(state="normal")

    def _count_mods(self, name):
        directory = os.path.join(instances.instance_dir(name), "mods")

        if os.path.isdir(directory):
            return len(
                [f for f in os.listdir(directory) if f.endswith(".jar")]
            )

        return 0

    # ================================================================
    # OptiFine
    # ================================================================

    def _save_optifine_setting(self):
        if not self.sel:
            return

        try:
            cfg = instances.load_cfg(self.sel)
            cfg["optifine"] = bool(self._optifine.get())
            instances.save_cfg(self.sel, cfg)
        except Exception as e:
            self.log_message("Could not save OptiFine setting: " + str(e))

    def install_optifine(self):
        if not self.sel:
            messagebox.showinfo(
                "BlemmLauncher",
                "Select an instance first."
            )
            return

        loader = self.loader

        if loader not in ("forge", "neoforge"):
            msg = (
                "This instance uses " + (loader or "vanilla")
                + ". OptiFine only loads as a mod under Forge or "
                "NeoForge (for vanilla instances the launcher boots it "
                "through launchwrapper).\n\n"
                "Install it anyway into this instance?"
            )

            if not messagebox.askyesno("OptiFine", msg):
                return

        path = filedialog.askopenfilename(
            title="Select OptiFine installer or mod JAR",
            filetypes=[
                ("OptiFine JAR", "*.jar"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        name = self.sel

        try:
            mc_version = instances.load_cfg(name)["version"]
        except Exception as e:
            messagebox.showerror("OptiFine", str(e))
            return

        self.play_btn.config(state="disabled", text="Working…")
        self.status.config(text="Installing OptiFine…", foreground=FG)

        def worker():
            try:
                instances.use(name, core)

                installed = core.install_optifine(
                    path,
                    version_id=mc_version
                )

                cfg = instances.load_cfg(name)
                cfg["optifine"] = True
                instances.save_cfg(name, cfg)

                self.q.put(("optifine_installed", installed, None, None))

            except Exception as e:
                self.q.put(
                    (
                        "fatal",
                        "OptiFine installation failed:\n" + str(e),
                        None,
                        None
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    # ================================================================
    # Import hack client / custom JAR / version JSON
    # ================================================================

    def import_client_dialog(self):
        path = filedialog.askopenfilename(
            title="Select a hack client / mod JAR or a version JSON",
            filetypes=[
                ("Clients & mods", "*.jar *.json"),
                ("JAR files", "*.jar"),
                ("JSON files", "*.json"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        kind = None

        try:
            kind = instances.inspect_client_file(path)
        except Exception:
            kind = None

        if kind is None:
            messagebox.showerror(
                "BlemmLauncher",
                "Couldn't recognize that file.\n"
                "Use a .jar (client or mod) or a Minecraft version .json."
            )
            return

        d = tk.Toplevel(self.root)
        d.title("Import client")
        d.configure(bg=BG)
        d.geometry("440x330")
        d.grab_set()

        style_dark(d)

        f = ttk.Frame(d, style="Card.TFrame", padding=14)
        f.pack(fill="both", expand=True)

        kind_text = {
            "mod": (
                "Mod JAR (hack client mod / OptiFine).\n"
                "It will be placed in the instance's mods folder."
            ),
            "client_jar": (
                "Custom client JAR.\n"
                "A new version built on a vanilla Minecraft version "
                "will launch it instead of the normal client."
            ),
            "version_json": (
                "Minecraft version JSON.\n"
                "A full custom version will be imported (including its "
                "client JAR if it sits next to the JSON)."
            )
        }.get(kind, "")

        ttk.Label(f, kind_text, style="MutedP.TLabel", wraplength=390).pack(
            anchor="w", pady=(0, 8)
        )

        ttk.Label(f, "File:", style="MutedP.TLabel").pack(anchor="w")

        ttk.Label(
            f, os.path.basename(path), style="MutedP.TLabel", wraplength=390
        ).pack(anchor="w", pady=(0, 10))

        name = tk.StringVar(
            value=os.path.splitext(os.path.basename(path))[0]
        )

        needs_version = kind in ("mod", "client_jar")

        version = tk.StringVar(value="release")

        version_combo = ttk.Combobox(
            f,
            textvariable=version,
            values=["release"],
            state="readonly"
        )

        target = tk.StringVar(
            value=(
                "new instance"
                if (not self.sel or kind in ("client_jar", "version_json"))
                else "selected instance"
            )
        )

        target_combo = ttk.Combobox(
            f,
            textvariable=target,
            state="readonly",
            values=[
                "new instance",
                (
                    "selected instance (" + self.sel + ")"
                    if self.sel
                    else "selected instance (none)"
                )
            ]
        )

        rows = [
            ("Instance name:", ttk.Entry(f, textvariable=name))
        ]

        if self.sel and kind == "mod":
            rows.append(("Import into:", target_combo))

        if needs_version:
            rows.append(("Base Minecraft version:", version_combo))

        for r, (label, widget) in enumerate(rows):
            ttk.Label(f, text=label, style="MutedP.TLabel").grid(
                row=r, column=0, sticky="w", pady=3
            )
            widget.grid(row=r, column=1, sticky="we", pady=3, padx=(8, 0))

        f.columnconfigure(1, weight=1)

        info = ttk.Label(f, text="", style="MutedP.TLabel", wraplength=390)
        info.grid(
            row=len(rows),
            column=0,
            columnspan=2,
            sticky="w",
            pady=(8, 0)
        )

        def fill_versions():
            try:
                if self._all_versions:
                    chosen = self._all_versions
                else:
                    versions, _, _ = core.list_versions()

                    def sk(v):
                        try:
                            return [
                                int(x)
                                for x in v.split(".")
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
                        reverse=True
                    )[:60]

                def apply():
                    if d.winfo_exists() and needs_version:
                        version_combo.config(values=["release"] + chosen)
                        info.config(text="version list loaded")

                self.root.after(0, apply)

            except Exception as e:
                def apply_err():
                    if d.winfo_exists():
                        info.config(
                            text="version list failed: " + str(e)
                        )

                self.root.after(0, apply_err)

        if needs_version:
            threading.Thread(target=fill_versions, daemon=True).start()

        def go():
            base_name = name.get().strip() or "Client"
            mc = version.get() if needs_version else None

            into_selected = (
                target.get().startswith("selected instance")
                and self.sel
                and kind == "mod"
            )

            instance_name = self.sel if into_selected else None

            try:
                d.destroy()

                self.play_btn.config(state="disabled", text="Importing…")
                self.status.config(text="Importing client…", foreground=FG)

                src_path = path

                def worker():
                    try:
                        result_name, what = instances.import_client(
                            src_path,
                            instance_name=instance_name,
                            mc_version=mc,
                            loader=None,
                            ram="4G",
                            username=base_name
                        )

                        self.q.put(
                            ("client_imported", result_name, what, None)
                        )

                    except Exception as e:
                        self.q.put(
                            (
                                "fatal",
                                "client import failed:\n" + str(e),
                                None,
                                None
                            )
                        )

                threading.Thread(target=worker, daemon=True).start()

            except Exception as e:
                messagebox.showerror("Blemm", str(e), parent=d)

        ttk.Button(
            f,
            text="Import",
            style="Play.TButton",
            command=go
        ).grid(
            row=len(rows) + 1,
            column=0,
            columnspan=2,
            sticky="we",
            pady=(12, 0)
        )

    # ================================================================
    # New instance
    # ================================================================

    def new_inst(self):
        d = tk.Toplevel(self.root)
        d.title("New instance")
        d.configure(bg=BG)
        d.geometry("400x320")

        style_dark(d)

        f = ttk.Frame(d, style="Card.TFrame", padding=14)
        f.pack(fill="both", expand=True)

        name = tk.StringVar()
        version = tk.StringVar(value="release")
        loader = tk.StringVar(value="vanilla")
        ram = tk.StringVar(value="4G")
        uname = tk.StringVar(value="Blemm")

        version_combo = ttk.Combobox(
            f,
            textvariable=version,
            values=["release"]
        )

        rows = [
            ("Name:", ttk.Entry(f, textvariable=name)),
            ("Version:", version_combo),
            (
                "Loader:",
                ttk.Combobox(
                    f,
                    textvariable=loader,
                    state="readonly",
                    values=["vanilla", "forge", "fabric", "neoforge"]
                )
            ),
            (
                "RAM:",
                ttk.Combobox(
                    f,
                    textvariable=ram,
                    state="readonly",
                    values=["2G", "4G", "6G", "8G"]
                )
            ),
            ("Username:", ttk.Entry(f, textvariable=uname))
        ]

        for r, (label, widget) in enumerate(rows):
            ttk.Label(f, text=label, style="MutedP.TLabel").grid(
                row=r, column=0, sticky="w", pady=3
            )
            widget.grid(row=r, column=1, sticky="we", pady=3, padx=(8, 0))

        f.columnconfigure(1, weight=1)

        info = ttk.Label(f, text="", style="MutedP.TLabel", wraplength=330)
        info.grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(6, 0))

        def fill_versions():
            try:
                if self._all_versions:
                    chosen = self._all_versions
                else:
                    versions, _, _ = core.list_versions()

                    def sk(v):
                        try:
                            return [
                                int(x)
                                for x in v.split(".")
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
                        reverse=True
                    )[:60]

                def apply():
                    if d.winfo_exists():
                        version_combo.config(values=["release"] + chosen)
                        info.config(text="version list loaded")

                self.root.after(0, apply)

            except Exception as e:
                def apply_err():
                    if d.winfo_exists():
                        info.config(text="version list failed: " + str(e))

                self.root.after(0, apply_err)

        threading.Thread(target=fill_versions, daemon=True).start()

        def go():
            nm = name.get().strip() or "New Instance"

            v = version.get()

            if v == "release":
                try:
                    v = core.manifest()["latest"]["release"]
                except Exception:
                    messagebox.showerror(
                        "Blemm",
                        "couldn't resolve 'release' - type a specific version",
                        parent=d
                    )
                    return

            ld = loader.get()
            ld = None if ld == "vanilla" else ld

            try:
                instances.create(nm, v, ld, ram.get(), uname.get())
                d.destroy()
                self._refresh_list()
                self._select_instance(nm)
            except Exception as e:
                messagebox.showerror("Blemm", str(e), parent=d)

        ttk.Button(
            f,
            text="Create",
            style="Play.TButton",
            command=go
        ).grid(
            row=len(rows) + 1,
            column=0,
            columnspan=2,
            sticky="we",
            pady=(10, 0)
        )

    # ================================================================
    # Delete / export / import / shortcut
    # ================================================================

    def del_inst(self):
        if not self.sel:
            return

        if messagebox.askyesno(
            "Blemm",
            "Delete instance '" + self.sel + "'?\n(saves are deleted too!)"
        ):
            instances.delete(self.sel)
            self._refresh_list()

    def export_inst(self):
        if not self.sel:
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            initialfile=self.sel + ".zip"
        )

        if not path:
            return

        try:
            instances.export(self.sel, path)
            self.status.config(text="exported → " + path, foreground=ACCENT)
        except Exception as e:
            messagebox.showerror("Blemm", str(e))

    def import_inst(self):
        path = filedialog.askopenfilename(
            filetypes=[("Instance zip", "*.zip")]
        )

        if not path:
            return

        try:
            name = instances.import_from_zip(path)
            self._refresh_list()
            self._select_instance(name)
            self.status.config(text="imported " + name, foreground=ACCENT)
        except Exception as e:
            messagebox.showerror("Blemm", str(e))

    def make_shortcut(self):
        if not self.sel:
            return

        try:
            path = instances.shortcut(self.sel)
            self.status.config(text="shortcut → " + path, foreground=ACCENT)
        except Exception as e:
            messagebox.showerror("Blemm", str(e))

    # ================================================================
    # Add files manually
    # ================================================================

    def add_file(self):
        if not self.sel:
            return

        paths = filedialog.askopenfilenames(
            title="Pick mods / packs (Ctrl+click for several)",
            filetypes=[
                ("Minecraft files", "*.jar *.zip"),
                ("All files", "*.*")
            ]
        )

        if not paths:
            return

        try:
            instances.use(self.sel, core)

            added = core.add_content_auto(paths)

            self.status.config(text=", ".join(added), foreground=ACCENT)
            self._sel_ev()

        except Exception as e:
            messagebox.showerror("Blemm", str(e))

    # ================================================================
    # Modrinth browser
    # ================================================================

    def browse_mods(self):
        if not self.sel:
            return

        name = self.sel
        mc_version = self.version
        loader = self.loader

        d = tk.Toplevel(self.root)
        d.title("Modrinth — " + name)
        d.configure(bg=BG)
        d.geometry("640x500")

        style_dark(d)

        f = ttk.Frame(d, style="Card.TFrame", padding=10)
        f.pack(fill="both", expand=True)

        top = ttk.Frame(f, style="Card.TFrame")
        top.pack(fill="x")

        q = tk.StringVar()

        ttk.Entry(top, textvariable=q).pack(
            side="left", fill="x", expand=True
        )

        ptype = tk.StringVar(value="mod")

        ttk.Combobox(
            top,
            textvariable=ptype,
            width=12,
            state="readonly",
            values=["mod", "shader", "resourcepack"]
        ).pack(side="left", padx=6)

        results = tk.Listbox(
            f,
            bg=FIELD,
            fg=FG,
            relief="flat",
            highlightthickness=0,
            selectbackground=ACCENT,
            selectforeground="#10240f",
            selectmode="extended",
            exportselection=False
        )

        results.pack(fill="both", expand=True, pady=8)

        mid = ttk.Frame(f, style="Card.TFrame")
        mid.pack(fill="x")

        lbl = ttk.Label(
            f,
            text="type a name, Search, Ctrl/Shift+click to multi-select, Install",
            style="MutedP.TLabel",
            wraplength=560
        )

        lbl.pack(anchor="w", pady=(6, 0))

        d._hits = []
        d._searching = False

        def search():
            if d._searching:
                return

            query = q.get()
            pt = ptype.get()

            ld = loader if (loader and pt == "mod") else None

            d._searching = True
            lbl.config(text="searching…", foreground=FG)

            def worker():
                try:
                    hits = instances.modrinth_search(
                        query, mc_version, ld, pt
                    )

                    def apply():
                        if not d.winfo_exists():
                            return

                        d._hits = hits
                        d._searching = False

                        results.delete(0, "end")

                        for h in hits:
                            results.insert(
                                "end",
                                h["title"] + " — " + h["author"]
                                + " (" + str(h["downs"]) + "↓)"
                            )

                        lbl.config(
                            text=(
                                str(len(hits)) + " results for "
                                + str(mc_version) + " / " + pt
                                + ((" / " + ld) if ld else "")
                            ),
                            foreground=FG
                        )

                    self.root.after(0, apply)

                except Exception as e:
                    def apply_err():
                        if not d.winfo_exists():
                            return

                        d._searching = False
                        lbl.config(
                            text="search failed: " + str(e),
                            foreground=DANGER
                        )

                    self.root.after(0, apply_err)

            threading.Thread(target=worker, daemon=True).start()

        def install():
            selection = results.curselection()

            if not selection:
                return

            hits = d._hits
            pt = ptype.get()

            chosen = [hits[i] for i in selection if i < len(hits)]

            lbl.config(
                text="installing " + str(len(chosen)) + " item(s)…",
                foreground=FG
            )

            def worker():
                ok = []
                errs = []

                for h in chosen:
                    try:
                        ld = loader if (loader and pt == "mod") else None

                        filename = instances.modrinth_install(
                            h["id"], mc_version, ld, pt
                        )

                        ok.append(filename)

                    except Exception as e:
                        errs.append(h["title"] + ": " + str(e))

                def apply():
                    if not d.winfo_exists():
                        return

                    msg = ""

                    if ok:
                        msg = (
                            "installed " + str(len(ok)) + ": "
                            + ", ".join(ok)
                        )

                    if errs:
                        if msg:
                            msg += "\n"
                        msg += "failed: " + "; ".join(errs)

                    lbl.config(
                        text=msg,
                        foreground=(ACCENT if ok and not errs else DANGER)
                    )

                    self.log_message("Modrinth: " + msg)

                self.root.after(0, apply)

            threading.Thread(target=worker, daemon=True).start()

        ttk.Button(top, text="Search", command=search).pack(
            side="left", padx=6
        )

        ttk.Button(
            mid,
            text="⬇  Install selected",
            style="Play.TButton",
            command=install
        ).pack(side="left")

    # ================================================================
    # Play
    # ================================================================

    def play(self):
        if not self.sel:
            return

        name = self.sel

        try:
            cfg = instances.load_cfg(name)
        except Exception as e:
            messagebox.showerror("Blemm", str(e))
            return

        uname = self._uname.get() or "Blemm"
        ram = self._ram.get() or "4G"
        use_optifine = bool(self._optifine.get())

        self.play_btn.config(state="disabled", text="Working…")
        self.bar.config(mode="indeterminate")
        self.bar.start(20)
        self.status.config(text="Preparing…", foreground=FG)

        def worker():
            try:
                instances.use(name, core)

                cfg["username"] = uname
                cfg["ram"] = ram
                cfg["optifine"] = use_optifine

                instances.save_cfg(name, cfg)

                vid = cfg["version"]
                loader = cfg.get("loader")

                self.q.put(
                    ("stage", "Preparing instance…", None, None)
                )

                if loader == "forge":
                    vid = core.install_forge(
                        vid,
                        cfg.get("loader_build")
                    )

                elif loader == "neoforge":
                    vid = instances.install_neoforge(
                        vid,
                        cfg.get("loader_build")
                    )

                elif loader == "fabric":
                    vid = instances.install_fabric(vid)

                self.q.put(
                    ("msg", "launching " + name + ": " + vid, None, None)
                )

                core.launch(vid, uname, ram, optifine=use_optifine)

                self.q.put(("done", "played " + name + " ♥", None, None))

            except SystemExit as e:
                self.q.put(("error", "aborted: " + str(e), None, None))

            except Exception as e:
                self.q.put(("fatal", str(e), None, None))

        threading.Thread(target=worker, daemon=True).start()

    # ================================================================
    # Log helper (must be called on the main thread)
    # ================================================================

    def log_message(self, message):
        self.log.config(state="normal")
        self.log.insert("end", str(message) + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ================================================================
    # Queue drain - runs every 100ms on the Tk main thread.
    # Every message is a 4-tuple (kind, text, done, total). The
    # unpack is defensive so ONE bad message can never kill the
    # pump - which previously froze the GUI on "Preparing…" forever.
    # ================================================================

    def _drain(self):
        dialogs = []

        while True:
            item = None

            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break

            try:
                kind = item[0]
                text = item[1] if len(item) > 1 else ""
                done = item[2] if len(item) > 2 else None
                total = item[3] if len(item) > 3 else None

                if kind == "stage":
                    if total:
                        self.status.config(
                            text=text + " (" + format(done, ",") + " / "
                            + format(total, ",") + ")",
                            foreground=FG
                        )
                        self.bar.config(
                            mode="determinate",
                            value=done / total * 100
                        )
                    else:
                        self.status.config(text=text, foreground=FG)
                        self.bar.config(mode="indeterminate")

                elif kind == "log":
                    self.log_message(text)

                elif kind == "versions":
                    self._all_versions = text

                    self.status.config(
                        text=str(len(text)) + " versions loaded",
                        foreground=MUTED
                    )

                elif kind == "msg":
                    self.log_message(text)

                elif kind == "client_imported":
                    result_name = text
                    what = done

                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY"
                    )

                    self.status.config(
                        text="client imported: " + result_name,
                        foreground=ACCENT
                    )

                    self.log_message(
                        "Client imported into '" + result_name + "': "
                        + str(what)
                    )

                    self._refresh_list()
                    self._select_instance(result_name)

                elif kind == "optifine_installed":
                    self._optifine.set(True)

                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY"
                    )

                    self.status.config(
                        text="OptiFine installed: " + os.path.basename(text),
                        foreground=ACCENT
                    )

                    self.log_message("OptiFine installed: " + text)

                    if self.sel:
                        self._sel_ev()

                elif kind == "done":
                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY"
                    )

                    self.bar.stop()
                    self.bar.config(mode="determinate", value=100)
                    self.status.config(text=text, foreground=ACCENT)
                    self.log_message(text)

                elif kind in ("error", "fatal"):
                    self.play_btn.config(
                        state="normal",
                        text="▶   PLAY"
                    )

                    self.bar.stop()
                    self.bar.config(mode="determinate", value=0)

                    self.status.config(
                        text="Failed — see log",
                        foreground=DANGER
                    )

                    self.log_message("ERROR: " + text)

                    if kind == "fatal":
                        dialogs.append(text)

            except Exception as e:
                # One malformed message must never kill the queue pump.

                self.log_message(
                    "WARNING: dropped a malformed UI message (" + str(e) + ")"
                )

        for message_text in dialogs:
            messagebox.showerror("BlemmLauncher", message_text)

        self.root.after(100, self._drain)


def run():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    run()
