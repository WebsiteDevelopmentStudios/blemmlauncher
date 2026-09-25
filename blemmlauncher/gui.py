"""BlemmLauncher GUI - tabbed desktop launcher UI."""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from . import core, instances


BG = "#15161b"
PANEL = "#202229"
CARD = "#262932"
FIELD = "#30333d"
FG = "#f1f3f7"
MUTED = "#9298a8"
ACCENT = "#e04bff"
ACCENT2 = "#7c5cff"
SUCCESS = "#4ade80"
DANGER = "#ff5c70"


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
        bordercolor=CARD,
        lightcolor=CARD,
        darkcolor=CARD,
        troughcolor=FIELD,
        arrowcolor=MUTED,
    )
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=CARD)
    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("Card.TLabel", background=CARD, foreground=FG)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("MutedCard.TLabel", background=CARD, foreground=MUTED)

    s.configure(
        "Title.TLabel",
        background=BG,
        foreground=FG,
        font=("Segoe UI", 20, "bold"),
    )
    s.configure(
        "Accent.TLabel",
        background=BG,
        foreground=ACCENT,
        font=("Segoe UI", 11, "bold"),
    )
    s.configure(
        "Big.TLabel",
        background=CARD,
        foreground=FG,
        font=("Segoe UI", 16, "bold"),
    )
    s.configure(
        "TNotebook",
        background=BG,
        borderwidth=0,
        tabmargins=[0, 0, 0, 0],
    )
    s.configure(
        "TNotebook.Tab",
        background=PANEL,
        foreground=MUTED,
        padding=(18, 9),
        font=("Segoe UI", 10, "bold"),
    )
    s.map(
        "TNotebook.Tab",
        background=[("selected", CARD), ("active", PANEL)],
        foreground=[("selected", FG), ("active", FG)],
    )
    s.configure("TButton", background=FIELD, foreground=FG, padding=(10, 7))
    s.map("TButton", background=[("active", "#3b3f4a")])
    s.configure(
        "Primary.TButton",
        background=ACCENT2,
        foreground="#ffffff",
        font=("Segoe UI", 10, "bold"),
        padding=(14, 9),
    )
    s.map("Primary.TButton", background=[("active", ACCENT)])
    s.configure(
        "Play.TButton",
        background=SUCCESS,
        foreground="#10240f",
        font=("Segoe UI", 13, "bold"),
        padding=(20, 11),
    )
    s.map("Play.TButton", background=[("active", "#6ce89a")])
    s.configure("TEntry", foreground=FG, insertcolor=FG, padding=7)
    s.configure("TCombobox", foreground=FG, padding=6)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD)])
    s.configure("TCheckbutton", background=CARD, foreground=FG)
    s.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=FIELD,
        thickness=9,
    )
    root.configure(bg=BG)


class App:
    def __init__(self, root):
        self.root = root
        root.title("BlemmLauncher")
        root.geometry("1050x720")
        root.minsize(900, 620)
        style_dark(root)

        self.q = queue.Queue()
        self.sel = None
        self.version = None
        self.loader = None
        self._all_versions = []
        self._modrinth_hits = []
        self._modrinth_searching = False

        self._uname = tk.StringVar(value="Blemm")
        self._ram = tk.StringVar(value="4G")
        self._optifine = tk.BooleanVar(value=False)

        self._build_header()
        self._build_tabs()
        self._build_status()

        core.set_reporter(self._on_report)
        root.after(100, self._drain)

        self._refresh_list()
        threading.Thread(target=self._load_versions, daemon=True).start()

    def _build_header(self):
        head = ttk.Frame(self.root)
        head.pack(fill="x", padx=18, pady=(14, 8))
        ttk.Label(head, text="◈ BlemmLauncher", style="Title.TLabel").pack(side="left")
        ttk.Label(
            head, text="  Minecraft, simplified.", style="Accent.TLabel"
        ).pack(side="left", pady=(7, 0))

    def _build_tabs(self):
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self.play_tab = ttk.Frame(self.tabs)
        self.loader_tab = ttk.Frame(self.tabs)
        self.modrinth_tab = ttk.Frame(self.tabs)
        self.server_tab = ttk.Frame(self.tabs)
        self.log_tab = ttk.Frame(self.tabs)

        self.tabs.add(self.play_tab, text="  Play  ")
        self.tabs.add(self.loader_tab, text="  Install  ")
        self.tabs.add(self.modrinth_tab, text="  Modrinth  ")
        self.tabs.add(self.server_tab, text="  Server  ")
        self.tabs.add(self.log_tab, text="  Logs  ")

        self._build_play_tab()
        self._build_loader_tab()
        self._build_modrinth_tab()
        self._build_server_tab()
        self._build_log_tab()

    def _build_status(self):
        box = ttk.Frame(self.root)
        box.pack(fill="x", padx=16, pady=(0, 10))
        self.status = ttk.Label(box, text="Loading Minecraft versions…", anchor="w")
        self.status.pack(fill="x")
        self.bar = ttk.Progressbar(box, mode="indeterminate")
        self.bar.pack(fill="x", pady=(4, 0))

    def _build_play_tab(self):
        tab = self.play_tab
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        left = ttk.Frame(tab, style="Card.TFrame", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        ttk.Label(left, text="Instances", style="Big.TLabel").pack(anchor="w")
        ttk.Label(
            left, text="Your isolated Minecraft setups", style="MutedCard.TLabel"
        ).pack(anchor="w", pady=(2, 10))

        self.ilist = tk.Listbox(
            left, width=29, height=18, bg=FIELD, fg=FG, relief="flat",
            highlightthickness=0, selectbackground=ACCENT2,
            selectforeground="#ffffff", font=("Segoe UI", 10)
        )
        self.ilist.pack(fill="both", expand=True)
        self.ilist.bind("<<ListboxSelect>>", self._sel_ev)

        actions = ttk.Frame(left, style="Card.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        for i, (label, cmd) in enumerate([
            ("＋ New", self.new_inst), ("Import", self.import_inst),
            ("Client…", self.import_client_dialog), ("Export", self.export_inst),
            ("Shortcut", self.make_shortcut), ("Delete", self.del_inst),
        ]):
            ttk.Button(actions, text=label, command=cmd).grid(
                row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2
            )
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        right = ttk.Frame(tab, style="Card.TFrame", padding=18)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        self.i_title = ttk.Label(right, text="Select an instance", style="Big.TLabel")
        self.i_title.grid(row=0, column=0, sticky="w")

        self.i_info = ttk.Label(
            right, text="Create or select an instance to get started.",
            style="MutedCard.TLabel", justify="left"
        )
        self.i_info.grid(row=1, column=0, sticky="w", pady=(4, 14))

        settings = ttk.Frame(right, style="Card.TFrame")
        settings.grid(row=2, column=0, sticky="ew")
        settings.columnconfigure(5, weight=1)

        ttk.Label(settings, text="Username", style="MutedCard.TLabel").grid(
            row=0, column=0, padx=(0, 5)
        )
        ttk.Entry(settings, textvariable=self._uname, width=13).grid(
            row=0, column=1, padx=(0, 14)
        )
        ttk.Label(settings, text="RAM", style="MutedCard.TLabel").grid(
            row=0, column=2, padx=(0, 5)
        )
        ttk.Combobox(
            settings, textvariable=self._ram,
            values=["2G", "4G", "6G", "8G", "12G", "16G"],
            width=6, state="readonly"
        ).grid(row=0, column=3, padx=(0, 14))
        ttk.Checkbutton(
            settings, text="Use OptiFine", variable=self._optifine,
            command=self._save_optifine_setting
        ).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(
            settings, text="Install OptiFine…", command=self.install_optifine
        ).grid(row=0, column=5, sticky="w")

        self.play_btn = ttk.Button(
            right, text="▶  PLAY", style="Play.TButton",
            command=self.play, state="disabled"
        )
        self.play_btn.grid(row=3, column=0, sticky="ew", pady=(20, 8))

        ttk.Label(
            right,
            text=(
                "Use the Install tab to add Fabric, NeoForge, or Forge to an "
                "instance. Use Modrinth to browse compatible mods, shaders, "
                "and resource packs."
            ),
            style="MutedCard.TLabel", wraplength=600
        ).grid(row=4, column=0, sticky="w", pady=(0, 10))

        ttk.Button(
            right, text="＋ Add mods / packs / shaders from files…",
            command=self.add_file
        ).grid(row=5, column=0, sticky="w")

    def _build_loader_tab(self):
        tab = self.loader_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        hero = ttk.Frame(tab, style="Card.TFrame", padding=18)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(hero, text="Loader Installer", style="Big.TLabel").pack(anchor="w")
        ttk.Label(
            hero,
            text=(
                "Install Fabric, NeoForge, or Forge automatically. "
                "BlemmLauncher downloads the correct installer and required Java."
            ),
            style="MutedCard.TLabel"
        ).pack(anchor="w", pady=(3, 0))

        card = ttk.Frame(tab, style="Card.TFrame", padding=18)
        card.grid(row=1, column=0, sticky="nsew")
        card.columnconfigure(1, weight=1)

        self.loader_instance = tk.StringVar(value="+ New instance")
        self.loader_version = tk.StringVar(value="release")
        self.loader_type = tk.StringVar(value="fabric")
        self.loader_name = tk.StringVar(value="")

        ttk.Label(card, text="Instance", style="MutedCard.TLabel").grid(
            row=0, column=0, sticky="w", pady=6
        )
        self.loader_instance_combo = ttk.Combobox(
            card, textvariable=self.loader_instance, state="readonly"
        )
        self.loader_instance_combo.grid(
            row=0, column=1, sticky="ew", padx=(12, 0), pady=6
        )

        ttk.Label(card, text="New instance name", style="MutedCard.TLabel").grid(
            row=1, column=0, sticky="w", pady=6
        )
        ttk.Entry(card, textvariable=self.loader_name).grid(
            row=1, column=1, sticky="ew", padx=(12, 0), pady=6
        )

        ttk.Label(card, text="Minecraft version", style="MutedCard.TLabel").grid(
            row=2, column=0, sticky="w", pady=6
        )
        self.loader_version_combo = ttk.Combobox(
            card, textvariable=self.loader_version,
            values=["release"], state="readonly"
        )
        self.loader_version_combo.grid(
            row=2, column=1, sticky="ew", padx=(12, 0), pady=6
        )

        ttk.Label(card, text="Loader", style="MutedCard.TLabel").grid(
            row=3, column=0, sticky="w", pady=6
        )
        ttk.Combobox(
            card, textvariable=self.loader_type,
            values=["fabric", "neoforge", "forge"], state="readonly"
        ).grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=6)

        self.loader_info = ttk.Label(
            card,
            text=(
                "Select an existing instance OR choose '+ New instance' "
                "to create one. Existing instances keep their Minecraft version."
            ),
            style="MutedCard.TLabel", wraplength=650, justify="left"
        )
        self.loader_info.grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(12, 10)
        )

        ttk.Button(
            card, text="Install Loader", style="Primary.TButton",
            command=self.install_loader
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        card.rowconfigure(6, weight=1)
        self._refresh_loader_instances()

    def _build_modrinth_tab(self):
        tab = self.modrinth_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        top = ttk.Frame(tab, style="Card.TFrame", padding=12)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(0, weight=1)

        self.modrinth_query = tk.StringVar()
        self.modrinth_type = tk.StringVar(value="mod")
        self.modrinth_target = tk.StringVar()

        ttk.Label(top, text="Modrinth Store", style="Big.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            top,
            text="A clean store-style browser for compatible Minecraft projects.",
            style="MutedCard.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(2, 9))

        searchbar = ttk.Frame(top, style="Card.TFrame")
        searchbar.grid(row=2, column=0, sticky="ew")
        searchbar.columnconfigure(0, weight=1)
        ttk.Entry(searchbar, textvariable=self.modrinth_query).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Combobox(
            searchbar, textvariable=self.modrinth_type,
            values=["mod", "shader", "resourcepack"], state="readonly", width=15
        ).grid(row=0, column=1, padx=7)
        ttk.Button(
            searchbar, text="Search", style="Primary.TButton",
            command=self.modrinth_search
        ).grid(row=0, column=2)

        ttk.Label(top, text="Install into", style="MutedCard.TLabel").grid(
            row=3, column=0, sticky="w", pady=(9, 2)
        )
        self.modrinth_target_combo = ttk.Combobox(
            top, textvariable=self.modrinth_target, state="readonly"
        )
        self.modrinth_target_combo.grid(row=4, column=0, sticky="ew")

        body = ttk.Frame(tab, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            body, bg=CARD, highlightthickness=0, borderwidth=0
        )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        self.modrinth_cards = ttk.Frame(canvas, style="Card.TFrame")
        self.modrinth_cards.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.modrinth_cards, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.modrinth_canvas = canvas

        self.modrinth_message = ttk.Label(
            self.modrinth_cards,
            text="Search Modrinth to see projects.",
            style="MutedCard.TLabel"
        )
        self.modrinth_message.pack(anchor="w", padx=18, pady=18)

    def _store_card(self, hit, target_name, mc_version, loader, ptype):
        card = ttk.Frame(self.modrinth_cards, style="Card.TFrame", padding=14)
        card.pack(fill="x", padx=10, pady=6)
        card.columnconfigure(0, weight=1)

        title = hit.get("title", "Unknown")
        author = hit.get("author", "Unknown")
        downloads = hit.get("downs", 0)
        desc = hit.get("desc", "") or "No description available."

        ttk.Label(card, text=title, style="Big.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            card,
            text="by " + author + "  •  " + f"{downloads:,}" + " downloads",
            style="MutedCard.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(1, 5))
        ttk.Label(
            card, text=desc, style="MutedCard.TLabel",
            wraplength=620, justify="left"
        ).grid(row=2, column=0, sticky="w")
        ttk.Button(
            card, text="Install", style="Primary.TButton",
            command=lambda h=hit: self._install_modrinth(
                h, target_name, mc_version, loader, ptype
            )
        ).grid(row=0, column=1, rowspan=3, padx=(16, 0))

    def modrinth_search(self):
        target = self.modrinth_target.get().strip()
        if not target:
            messagebox.showinfo(
                "Modrinth",
                "Select an instance in the Play tab first, or choose one in the Install into box."
            )
            return

        try:
            cfg = instances.load_cfg(target)
        except Exception as e:
            messagebox.showerror("Modrinth", str(e))
            return

        query = self.modrinth_query.get().strip()
        ptype = self.modrinth_type.get()
        mc_version = cfg.get("version")
        loader = cfg.get("loader")

        self._modrinth_searching = True
        self.modrinth_message.config(text="Searching Modrinth…")
        for child in self.modrinth_cards.winfo_children():
            child.destroy()

        def worker():
            try:
                hits = instances.modrinth_search(
                    query, mc_version,
                    loader if ptype == "mod" else None,
                    ptype
                )
                self.q.put(
                    ("modrinth_results", (hits, target, mc_version, loader, ptype), None, None)
                )
            except Exception as e:
                self.q.put(("modrinth_error", str(e), None, None))

        threading.Thread(target=worker, daemon=True).start()

    def _install_modrinth(self, hit, target, mc_version, loader, ptype):
        self.status.config(text="Installing " + hit["title"] + "…")
        self.bar.config(mode="indeterminate")
        self.bar.start(15)

        def worker():
            try:
                instances.use(target, core)
                filename = instances.modrinth_install(
                    hit["id"], mc_version,
                    loader if ptype == "mod" else None, ptype
                )
                self.q.put(
                    ("modrinth_installed", target + " • " + filename, None, None)
                )
            except Exception as e:
                self.q.put(
                    ("fatal", "Modrinth install failed:\n" + str(e), None, None)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _build_server_tab(self):
        tab = self.server_tab
        frame = ttk.Frame(tab, style="Card.TFrame", padding=30)
        frame.pack(fill="both", expand=True, padx=40, pady=40)
        ttk.Label(frame, text="Server", style="Big.TLabel").pack(pady=(80, 8))
        ttk.Label(
            frame, text="Coming soon…", style="Accent.TLabel",
            font=("Segoe UI", 16, "bold")
        ).pack()
        ttk.Label(
            frame,
            text="Server management will be added to a future BlemmLauncher update.",
            style="MutedCard.TLabel"
        ).pack(pady=8)

    def _build_log_tab(self):
        self.log = scrolledtext.ScrolledText(
            self.log_tab, state="disabled", font=("Consolas", 9),
            bg=FIELD, fg=FG, insertbackground=FG, relief="flat", borderwidth=0
        )
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    @staticmethod
    def _version_key(v):
        try:
            return [int(x) for x in v.split(".") if x.isdigit()]
        except Exception:
            return [-1]

    def _load_versions(self):
        try:
            versions, latest, _ = core.list_versions()
            chosen = sorted(
                [
                    v for v in versions
                    if self._version_key(v) >= [1, 12, 2]
                    and "-" not in v
                    and not v.startswith(("w", "pre", "rc"))
                ],
                key=self._version_key,
                reverse=True
            )
            self.q.put(("versions", chosen, latest, None))
        except Exception as e:
            self.q.put(("error", "Version list failed: " + str(e), None, None))

    def _refresh_loader_instances(self):
        if not hasattr(self, "loader_instance_combo"):
            return
        names = instances.list_instances()
        values = ["+ New instance"] + names
        self.loader_instance_combo.configure(values=values)
        if self.sel in names:
            self.loader_instance.set(self.sel)
        elif self.loader_instance.get() not in values:
            self.loader_instance.set("+ New instance")
        elif not names:
            self.loader_instance.set("+ New instance")

    def _refresh_modrinth_targets(self):
        if not hasattr(self, "modrinth_target_combo"):
            return
        names = instances.list_instances()
        self.modrinth_target_combo.configure(values=names)
        if self.sel in names:
            self.modrinth_target.set(self.sel)
        elif names and self.modrinth_target.get() not in names:
            self.modrinth_target.set(names[0])
        elif not names:
            self.modrinth_target.set("")

    def _refresh_list(self):
        self.ilist.delete(0, "end")
        for name in instances.list_instances():
            self.ilist.insert("end", name)
        self.sel = None
        self.version = None
        self.loader = None
        self._optifine.set(False)
        self.play_btn.config(state="disabled")
        self._refresh_loader_instances()
        self._refresh_modrinth_targets()

    def _select_instance(self, name):
        names = list(self.ilist.get(0, "end"))
        if name in names:
            idx = names.index(name)
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
            instances.use(name, core)
        except Exception as e:
            messagebox.showerror("BlemmLauncher", str(e))
            return

        self.sel = name
        self.version = cfg.get("version")
        self.loader = cfg.get("loader")
        self._uname.set(cfg.get("username", "Blemm"))
        self._ram.set(cfg.get("ram", "4G"))
        self._optifine.set(bool(cfg.get("optifine", False)))

        self.i_title.config(text=name)
        self.i_info.config(
            text=(
                "Minecraft " + str(self.version) + "  •  "
                + (self.loader or "vanilla") + "  •  "
                + str(cfg.get("ram", "4G")) + " RAM\n"
                + str(self._count_mods(name)) + " mods installed"
            )
        )
        self.play_btn.config(state="normal")
        self._refresh_loader_instances()
        self._refresh_modrinth_targets()

    def _count_mods(self, name):
        d = os.path.join(instances.instance_dir(name), "mods")
        if not os.path.isdir(d):
            return 0
        return len([f for f in os.listdir(d) if f.lower().endswith(".jar")])

    def install_loader(self):
        chosen_instance = self.loader_instance.get().strip()
        new_name = self.loader_name.get().strip()
        loader = self.loader_type.get().strip().lower()
        requested_version = self.loader_version.get().strip()

        try:
            if chosen_instance and chosen_instance != "+ New instance":
                name = chosen_instance
                cfg = instances.load_cfg(name)
                mc_version = cfg.get("version")
            else:
                name = new_name or "New Instance"
                mc_version = requested_version
                if mc_version == "release":
                    mc_version = core.manifest()["latest"]["release"]
                instances.create(
                    name, mc_version, None,
                    self._ram.get(), self._uname.get() or "Blemm"
                )
                cfg = instances.load_cfg(name)

            if not mc_version:
                raise RuntimeError("No Minecraft version selected.")

            instances.use(name, core)
            self.play_btn.config(state="disabled")
            self.status.config(
                text="Installing " + loader.title()
                + " for Minecraft " + str(mc_version) + "…"
            )
            self.bar.config(mode="indeterminate")
            self.bar.start(15)

            def worker():
                try:
                    vid = instances.install_loader(loader, mc_version, None)
                    cfg = instances.load_cfg(name)
                    cfg["loader"] = loader
                    if loader == "neoforge":
                        cfg["loader_build"] = vid[len("neoforge-"):]
                    else:
                        cfg["loader_build"] = None
                    cfg["version"] = mc_version
                    instances.save_cfg(name, cfg)
                    self.q.put(
                        ("loader_installed", (name, loader, vid), None, None)
                    )
                except Exception as e:
                    self.q.put(
                        (
                            "fatal",
                            loader.title() + " installation failed:\n" + str(e),
                            None, None
                        )
                    )

            threading.Thread(target=worker, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Install", str(e))

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
            messagebox.showinfo("OptiFine", "Select an instance first.")
            return

        path = filedialog.askopenfilename(
            title="Select OptiFine JAR",
            filetypes=[("JAR files", "*.jar"), ("All files", "*.*")]
        )
        if not path:
            return

        name = self.sel
        self.play_btn.config(state="disabled", text="Working…")
        self.bar.config(mode="indeterminate")
        self.bar.start(15)

        def worker():
            try:
                instances.use(name, core)
                installed = core.install_optifine(
                    path, version_id=instances.load_cfg(name).get("version")
                )
                cfg = instances.load_cfg(name)
                cfg["optifine"] = True
                instances.save_cfg(name, cfg)
                self.q.put(("optifine_installed", installed, None, None))
            except Exception as e:
                self.q.put(
                    ("fatal", "OptiFine installation failed:\n" + str(e), None, None)
                )

        threading.Thread(target=worker, daemon=True).start()

    def new_inst(self):
        d = tk.Toplevel(self.root)
        d.title("New Minecraft Instance")
        d.geometry("460x330")
        d.configure(bg=BG)
        style_dark(d)
        d.grab_set()

        f = ttk.Frame(d, style="Card.TFrame", padding=16)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        name = tk.StringVar(value="My Minecraft")
        version = tk.StringVar(value="release")
        loader = tk.StringVar(value="vanilla")
        ram = tk.StringVar(value="4G")
        uname = tk.StringVar(value=self._uname.get() or "Blemm")

        rows = [
            ("Name", ttk.Entry(f, textvariable=name)),
            (
                "Minecraft",
                ttk.Combobox(
                    f, textvariable=version,
                    values=["release"], state="readonly"
                )
            ),
            (
                "Loader",
                ttk.Combobox(
                    f, textvariable=loader,
                    values=["vanilla", "fabric", "neoforge", "forge"],
                    state="readonly"
                )
            ),
            (
                "RAM",
                ttk.Combobox(
                    f, textvariable=ram,
                    values=["2G", "4G", "6G", "8G", "12G"],
                    state="readonly"
                )
            ),
            ("Username", ttk.Entry(f, textvariable=uname)),
        ]
        for r, (label, widget) in enumerate(rows):
            ttk.Label(f, text=label, style="MutedCard.TLabel").grid(
                row=r, column=0, sticky="w", pady=5
            )
            widget.grid(row=r, column=1, sticky="ew", padx=(12, 0), pady=5)

        def apply_versions():
            try:
                vals = self._all_versions or core.list_versions()[0]
                self.root.after(
                    0,
                    lambda: rows[1][1].configure(values=["release"] + vals)
                    if d.winfo_exists() else None
                )
            except Exception:
                pass

        threading.Thread(target=apply_versions, daemon=True).start()

        def create_now():
            try:
                v = version.get()
                if v == "release":
                    v = core.manifest()["latest"]["release"]
                ld = None if loader.get() == "vanilla" else loader.get()
                instance_name = name.get().strip() or "My Minecraft"
                instances.create(
                    instance_name, v, ld, ram.get(), uname.get() or "Blemm"
                )
                d.destroy()
                self._refresh_list()
                self._select_instance(instance_name)
            except Exception as e:
                messagebox.showerror("New Instance", str(e), parent=d)

        ttk.Button(
            f, text="Create Instance", style="Primary.TButton", command=create_now
        ).grid(row=len(rows), column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def del_inst(self):
        if not self.sel:
            return
        if messagebox.askyesno(
            "Delete instance",
            "Delete '" + self.sel
            + "'? Saves inside the instance will also be deleted."
        ):
            instances.delete(self.sel)
            self._refresh_list()

    def export_inst(self):
        if not self.sel:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".zip", initialfile=self.sel + ".zip"
        )
        if not path:
            return
        try:
            instances.export(self.sel, path)
            self.status.config(
                text="Exported → " + path, foreground=SUCCESS
            )
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def import_inst(self):
        path = filedialog.askopenfilename(
            filetypes=[("Instance ZIP", "*.zip")]
        )
        if not path:
            return
        try:
            name = instances.import_from_zip(path)
            self._refresh_list()
            self._select_instance(name)
            self.status.config(
                text="Imported " + name, foreground=SUCCESS
            )
        except Exception as e:
            messagebox.showerror("Import", str(e))

    def make_shortcut(self):
        if not self.sel:
            return
        try:
            path = instances.shortcut(self.sel)
            self.status.config(
                text="Shortcut created → " + path, foreground=SUCCESS
            )
        except Exception as e:
            messagebox.showerror("Shortcut", str(e))

    def add_file(self):
        if not self.sel:
            messagebox.showinfo("Files", "Select an instance first.")
            return
        paths = filedialog.askopenfilenames(
            title="Add Minecraft files",
            filetypes=[("Minecraft files", "*.jar *.zip"), ("All files", "*.*")]
        )
        if not paths:
            return
        try:
            instances.use(self.sel, core)
            added = core.add_content_auto(paths)
            self.status.config(
                text="Added: " + ", ".join(added), foreground=SUCCESS
            )
            self._sel_ev()
        except Exception as e:
            messagebox.showerror("Files", str(e))

    def import_client_dialog(self):
        path = filedialog.askopenfilename(
            title="Select a client/mod/version JSON",
            filetypes=[
                ("Minecraft files", "*.jar *.json"),
                ("JAR files", "*.jar"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ]
        )
        if not path:
            return

        try:
            kind = instances.inspect_client_file(path)
            if kind is None:
                raise RuntimeError(
                    "That file is not a recognized Minecraft client, mod, "
                    "or version JSON."
                )
            if self._all_versions:
                mc_version = self._all_versions[0]
            else:
                mc_version = core.manifest()["latest"]["release"]

            target = self.sel
            name, result = instances.import_client(
                path,
                instance_name=target,
                mc_version=mc_version,
                loader=self.loader,
                ram=self._ram.get(),
                username=self._uname.get() or "Blemm",
            )
            self._refresh_list()
            self._select_instance(name)
            self.status.config(text=result, foreground=SUCCESS)
        except Exception as e:
            messagebox.showerror("Client Import", str(e))

    def play(self):
        if not self.sel:
            return

        name = self.sel
        try:
            cfg = instances.load_cfg(name)
        except Exception as e:
            messagebox.showerror("Play", str(e))
            return

        uname = self._uname.get() or "Blemm"
        ram = self._ram.get() or "4G"
        optifine = bool(self._optifine.get())

        self.play_btn.config(state="disabled", text="Preparing…")
        self.bar.config(mode="indeterminate")
        self.bar.start(15)

        def worker():
            try:
                instances.use(name, core)
                cfg["username"] = uname
                cfg["ram"] = ram
                cfg["optifine"] = optifine
                instances.save_cfg(name, cfg)

                vid = cfg["version"]
                loader = cfg.get("loader")

                if loader == "forge":
                    vid = core.install_forge(vid, cfg.get("loader_build"))
                elif loader == "neoforge":
                    vid = instances.install_neoforge(
                        vid, cfg.get("loader_build")
                    )
                elif loader == "fabric":
                    vid = instances.install_fabric(vid)

                self.q.put(
                    ("msg", "Launching " + name + " → " + vid, None, None)
                )
                core.launch(vid, uname, ram, optifine=optifine)
                self.q.put(("done", "Minecraft closed.", None, None))
            except SystemExit as e:
                self.q.put(("error", "Launch aborted: " + str(e), None, None))
            except Exception as e:
                self.q.put(("fatal", str(e), None, None))

        threading.Thread(target=worker, daemon=True).start()

    def _on_report(self, kind, text, done=None, total=None):
        self.q.put(("stage", text, done, total))

    def log_message(self, message):
        self.log.config(state="normal")
        self.log.insert("end", str(message) + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _drain(self):
        dialogs = []
        while True:
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
                    self.status.config(text=text, foreground=FG)
                    if total:
                        self.bar.stop()
                        self.bar.config(
                            mode="determinate",
                            value=(done or 0) / total * 100
                        )
                    else:
                        self.bar.config(mode="indeterminate")
                        self.bar.start(15)

                elif kind == "versions":
                    self._all_versions = text
                    self.status.config(
                        text=str(len(text)) + " Minecraft versions loaded",
                        foreground=MUTED
                    )
                    self.loader_version_combo.configure(
                        values=["release"] + text
                    )

                elif kind == "loader_installed":
                    name, loader, vid = text
                    self.bar.stop()
                    self.bar.config(mode="determinate", value=100)
                    self.status.config(
                        text=loader.title() + " installed for "
                        + name + " → " + vid,
                        foreground=SUCCESS
                    )
                    self.log_message(
                        loader.title() + " installed in '"
                        + name + "': " + vid
                    )
                    self._refresh_list()
                    self._select_instance(name)

                elif kind == "modrinth_results":
                    hits, target, mc_version, loader, ptype = text
                    self._modrinth_hits = hits
                    self._modrinth_searching = False
                    for child in self.modrinth_cards.winfo_children():
                        child.destroy()

                    if not hits:
                        ttk.Label(
                            self.modrinth_cards,
                            text="No compatible projects found.",
                            style="MutedCard.TLabel"
                        ).pack(anchor="w", padx=18, pady=18)
                    else:
                        for hit in hits:
                            self._store_card(
                                hit, target, mc_version, loader, ptype
                            )

                    self.status.config(
                        text=str(len(hits)) + " Modrinth projects found",
                        foreground=FG
                    )

                elif kind == "modrinth_error":
                    self._modrinth_searching = False
                    for child in self.modrinth_cards.winfo_children():
                        child.destroy()
                    ttk.Label(
                        self.modrinth_cards,
                        text="Search failed: " + str(text),
                        style="MutedCard.TLabel"
                    ).pack(anchor="w", padx=18, pady=18)
                    self.status.config(
                        text="Modrinth search failed", foreground=DANGER
                    )

                elif kind == "modrinth_installed":
                    self.bar.stop()
                    self.status.config(
                        text="Installed → " + str(text), foreground=SUCCESS
                    )
                    self.log_message(
                        "Modrinth installed: " + str(text)
                    )
                    self._refresh_list()
                    if self.sel:
                        self._select_instance(self.sel)

                elif kind == "optifine_installed":
                    self.bar.stop()
                    self._optifine.set(True)
                    self.status.config(
                        text="OptiFine installed: "
                        + os.path.basename(str(text)),
                        foreground=SUCCESS
                    )
                    self.log_message("OptiFine installed: " + str(text))
                    if self.sel:
                        self._sel_ev()

                elif kind == "msg":
                    self.log_message(text)

                elif kind == "done":
                    self.bar.stop()
                    self.bar.config(mode="determinate", value=100)
                    self.play_btn.config(state="normal", text="▶  PLAY")
                    self.status.config(text=text, foreground=SUCCESS)
                    self.log_message(text)

                elif kind in ("error", "fatal"):
                    self.bar.stop()
                    self.bar.config(mode="determinate", value=0)
                    self.play_btn.config(state="normal", text="▶  PLAY")
                    self.status.config(
                        text="Failed — see Logs", foreground=DANGER
                    )
                    self.log_message("ERROR: " + str(text))
                    if kind == "fatal":
                        dialogs.append(str(text))
            except Exception as e:
                self.log_message("UI warning: " + str(e))

        for msg in dialogs:
            messagebox.showerror("BlemmLauncher", msg)

        self.root.after(100, self._drain)


def run():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    run()
