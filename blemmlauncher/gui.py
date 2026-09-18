import os
import threading
import queue

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

from . import core, instances

BG, PANEL, FIELD = "#1e1f24", "#272930", "#2f323b"
FG, MUTED, ACCENT, DANGER = "#e8e9ee", "#8b8fa3", "#4ade80", "#f87171"

def style_dark(root):
ttk.Style().theme_use("clam")

```
s = ttk.Style()

s.configure(
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

for n, bg in [
    ("TFrame", BG),
    ("Card.TFrame", PANEL),
]:
    s.configure(
        n,
        background=bg,
    )

s.configure(
    "TLabel",
    background=BG,
    foreground=FG,
)

s.configure(
    "Muted.TLabel",
    background=BG,
    foreground=MUTED,
)

s.configure(
    "MutedP.TLabel",
    background=PANEL,
    foreground=MUTED,
)

s.configure(
    "Title.TLabel",
    background=BG,
    foreground=ACCENT,
    font=("Segoe UI", 18, "bold"),
)

s.configure(
    "TEntry",
    foreground=FG,
    insertcolor=FG,
    padding=4,
)

s.configure(
    "TCombobox",
    foreground=FG,
    padding=4,
)

s.map(
    "TCombobox",
    fieldbackground=[
        ("readonly", FIELD)
    ],
)

s.configure(
    "Inst.TButton",
    background=FIELD,
    foreground=FG,
    padding=6,
    width=13,
)

s.map(
    "Inst.TButton",
    background=[
        ("active", "#3a3e49")
    ],
)

s.configure(
    "Play.TButton",
    background=ACCENT,
    foreground="#10240f",
    font=("Segoe UI", 12, "bold"),
    padding=(30, 10),
)

s.map(
    "Play.TButton",
    background=[
        ("active", "#6ce89a"),
        ("disabled", "#39543f"),
    ],
)

s.configure(
    "TButton",
    background=FIELD,
    foreground=FG,
    padding=6,
)

s.map(
    "TButton",
    background=[
        ("active", "#3a3e49")
    ],
)

s.configure(
    "TCheckbutton",
    background=PANEL,
    foreground=FG,
)

s.configure(
    "Horizontal.TProgressbar",
    background=ACCENT,
    troughcolor=FIELD,
    thickness=10,
)

root.configure(bg=BG)
```

class App:
def **init**(self, root):
self.root = root

```
    root.title("BlemmLauncher")
    root.geometry("860x600")
    root.minsize(760, 540)

    style_dark(root)

    self.q = queue.Queue()
    self.sel = None
    self.version_map = {}

    head = ttk.Frame(root)
    head.pack(
        fill="x",
        padx=14,
        pady=(10, 2),
    )

    ttk.Label(
        head,
        text="◈ BlemmLauncher",
        style="Title.TLabel",
    ).pack(side="left")

    ttk.Label(
        head,
        text="instances · loaders · modrinth · import/export",
        style="Muted.TLabel",
    ).pack(
        side="left",
        padx=10,
        pady=(10, 0),
    )

    body = ttk.Frame(root)
    body.pack(
        fill="both",
        expand=True,
        padx=14,
        pady=8,
    )

    body.columnconfigure(
        1,
        weight=1,
    )

    body.rowconfigure(
        0,
        weight=1,
    )

    # ---------- left: instance list ----------

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

    self.ilist.bind(
        "<<ListboxSelect>>",
        self._sel_ev,
    )

    bb = ttk.Frame(
        left,
        style="Card.TFrame",
    )

    bb.pack(
        fill="x",
        pady=(8, 0),
    )

    for i, (t, c) in enumerate(
        [
            ("＋ New", self.new_inst),
            ("⭳ Import", self.import_inst),
            ("⭱ Export", self.export_inst),
            ("✂ Shortcut", self.make_shortcut),
            ("🗑 Delete", self.del_inst),
        ]
    ):
        ttk.Button(
            bb,
            text=t,
            style="Inst.TButton",
            command=c,
        ).grid(
            row=i // 2,
            column=i % 2,
            sticky="we",
            pady=2,
            padx=2,
        )

    bb.columnconfigure(
        0,
        weight=1,
    )

    bb.columnconfigure(
        1,
        weight=1,
    )

    # ---------- right: selected instance ----------

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

    right.columnconfigure(
        1,
        weight=1,
    )

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

    self._uname = tk.StringVar(
        value="Blemm"
    )

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

    self._ram = tk.StringVar(
        value="4G"
    )

    ttk.Combobox(
        settings,
        textvariable=self._ram,
        values=[
            "2G",
            "4G",
            "6G",
            "8G",
        ],
        width=6,
        state="readonly",
    ).pack(
        side="left",
        padx=6,
    )

    # ---------- OptiFine ----------

    self._optifine = tk.BooleanVar(
        value=False
    )

    self.optifine_check = ttk.Checkbutton(
        settings,
        text="OptiFine",
        variable=self._optifine,
        command=self._save_optifine_setting,
    )

    self.optifine_check.pack(
        side="left",
        padx=(14, 0),
    )

    ttk.Button(
        right,
        text="⚙ Install OptiFine",
        command=self.install_optifine,
    ).grid(
        row=3,
        column=0,
        sticky="w",
        pady=(10, 0),
    )

    ttk.Button(
        right,
        text="📁 Install OptiFine manually",
        command=self.install_optifine_manual,
    ).grid(
        row=3,
        column=1,
        sticky="w",
        pady=(10, 0),
        padx=(8, 0),
    )

    self.optifine_status = ttk.Label(
        right,
        text="",
        style="MutedP.TLabel",
    )

    self.optifine_status.grid(
        row=4,
        column=0,
        columnspan=2,
        sticky="w",
        pady=(4, 0),
    )

    # ---------- play ----------

    self.play_btn = ttk.Button(
        right,
        text="▶   PLAY",
        style="Play.TButton",
        command=self.play,
        state="disabled",
    )

    self.play_btn.grid(
        row=5,
        column=0,
        columnspan=2,
        sticky="we",
        pady=(12, 6),
    )

    ttk.Button(
        right,
        text="🔎 Browse & install (Modrinth) — mods / shaders / packs",
        command=self.browse_mods,
    ).grid(
        row=6,
        column=0,
        columnspan=2,
        sticky="w",
    )

    ttk.Button(
        right,
        text="＋ add files… (Ctrl+click several: mods, packs, shaders)",
        command=self.add_file,
    ).grid(
        row=7,
        column=0,
        columnspan=2,
        sticky="w",
        pady=(6, 0),
    )

    # ---------- status + log ----------

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

    self.root.after(
        100,
        self._drain,
    )

    threading.Thread(
        target=self._load_versions,
        daemon=True,
    ).start()

    self._refresh_list()

# ---------- version list ----------

def _load_versions(self):
    try:
        versions, latest, _ = core.list_versions()

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
                and not v.startswith(
                    ("w", "pre", "rc")
                )
            ],
            key=sk,
            reverse=True,
        )

        self.q.put(
            ("versions", chosen)
        )

    except Exception as e:
        self.q.put(
            (
                "error",
                f"version list failed: {e}",
            )
        )

# ---------- instance list ----------

def _refresh_list(self):
    self.ilist.delete(
        0,
        "end",
    )

    for n in instances.list_instances():
        self.ilist.insert(
            "end",
            n,
        )

    self.sel = None

    self._optifine.set(False)

    self.play_btn.config(
        state="disabled"
    )

def _sel_ev(self, _=None):
    sel = self.ilist.curselection()

    if not sel:
        return

    name = self.ilist.get(
        sel[0]
    )

    cfg = instances.load_cfg(
        name
    )

    self.sel = name
    self.version = cfg["version"]
    self.loader = cfg.get("loader")

    self._uname.set(
        cfg.get(
            "username",
            "Blemm",
        )
    )

    self._ram.set(
        cfg.get(
            "ram",
            "4G",
        )
    )

    self._optifine.set(
        bool(
            cfg.get(
                "optifine",
                False,
            )
        )
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

    self._update_optifine_status()

def _count_mods(self, name):
    d = os.path.join(
        instances.instance_dir(name),
        "mods",
    )

    return (
        len(os.listdir(d))
        if os.path.isdir(d)
        else 0
    )

# ---------- OptiFine ----------

def _save_optifine_setting(self):
    if not self.sel:
        return

    try:
        cfg = instances.load_cfg(
            self.sel
        )

        cfg["optifine"] = bool(
            self._optifine.get()
        )

        instances.save_cfg(
            self.sel,
            cfg,
        )

        self._update_optifine_status()

    except Exception as e:
        self._log_message(
            f"OptiFine setting save failed: {e}"
        )

def _update_optifine_status(self):
    if not self.sel:
        self.optifine_status.config(
            text=""
        )
        return

    try:
        core.set_game_dir(
            instances.instance_dir(
                self.sel
            )
        )

        status = core.get_optifine_status()

        if status["installed"]:
            self.optifine_status.config(
                text=(
                    "OptiFine installed: "
                    + ", ".join(
                        status["filenames"]
                    )
                ),
                foreground=ACCENT,
            )
        else:
            self.optifine_status.config(
                text=(
                    "OptiFine not installed "
                    "(automatic or manual)"
                ),
                foreground=MUTED,
            )

    except Exception:
        self.optifine_status.config(
            text=""
        )

def install_optifine(self):
    if not self.sel:
        return

    version = self.version

    self.play_btn.config(
        state="disabled"
    )

    self.status.config(
        text=f"Installing OptiFine for Minecraft {version}...",
        foreground=FG,
    )

    self.bar.config(
        mode="indeterminate"
    )

    self.bar.start(20)

    def worker():
        try:
            core.set_game_dir(
                instances.instance_dir(
                    self.sel
                )
            )

            self.q.put(
                (
                    "msg",
                    f"Installing OptiFine for {version}..."
                )
            )

            out = core.install_optifine_for_version(
                version
            )

            cfg = instances.load_cfg(
                self.sel
            )

            cfg["optifine"] = True

            instances.save_cfg(
                self.sel,
                cfg,
            )

            self.q.put(
                (
                    "optifine_done",
                    f"OptiFine installed: "
                    f"{os.path.basename(out)}"
                )
            )

        except Exception as e:
            self.q.put(
                (
                    "optifine_failed",
                    str(e),
                )
            )

    threading.Thread(
        target=worker,
        daemon=True,
    ).start()

def install_optifine_manual(self):
    if not self.sel:
        return

    p = filedialog.askopenfilename(
        title="Select OptiFine installer",
        filetypes=[
            (
                "OptiFine installer",
                "*OptiFine*.jar",
            ),
            (
                "Java JAR",
                "*.jar",
            ),
            (
                "All files",
                "*.*",
            ),
        ],
    )

    if not p:
        return

    self.play_btn.config(
        state="disabled"
    )

    self.status.config(
        text="Installing manually selected OptiFine...",
        foreground=FG,
    )

    self.bar.config(
        mode="indeterminate"
    )

    self.bar.start(20)

    def worker():
        try:
            core.set_game_dir(
                instances.instance_dir(
                    self.sel
                )
            )

            out = core.install_optifine_from_file(
                p
            )

            cfg = instances.load_cfg(
                self.sel
            )

            cfg["optifine"] = True

            instances.save_cfg(
                self.sel,
                cfg,
            )

            self.q.put(
                (
                    "optifine_done",
                    f"Manual OptiFine installed: "
                    f"{os.path.basename(out)}"
                )
            )

        except Exception as e:
            self.q.put(
                (
                    "optifine_failed",
                    str(e),
                )
            )

    threading.Thread(
        target=worker,
        daemon=True,
    ).start()

# ---------- create / delete / io ----------

def new_inst(self):
    d = tk.Toplevel(
        self.root
    )

    d.title(
        "New instance"
    )

    d.configure(
        bg=BG
    )

    d.geometry(
        "380x260"
    )

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
    version = tk.StringVar(
        value="release"
    )

    loader = tk.StringVar(
        value="vanilla"
    )

    ram = tk.StringVar(
        value="4G"
    )

    uname = tk.StringVar(
        value="Blemm"
    )

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
        nm = (
            name.get().strip()
            or "New Instance"
        )

        v = version.get()

        if v == "release":
            try:
                v = core.manifest()[
                    "latest"
                ]["release"]

            except Exception:
                messagebox.showerror(
                    "Blemm",
                    "couldn't resolve 'release' - "
                    "type a specific version",
                    parent=d,
                )

                return

        ld = loader.get()

        ld = (
            None
            if ld == "vanilla"
            else ld
        )

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

def export_inst(self):
    if not self.sel:
        return

    p = filedialog.asksaveasfilename(
        defaultextension=".zip",
        initialfile=f"{self.sel}.zip",
    )

    if p:
        try:
            instances.export(
                self.sel,
                p,
            )

            self.status.config(
                text=f"exported → {p}",
                foreground=ACCENT,
            )

        except Exception as e:
            messagebox.showerror(
                "Blemm",
                str(e),
            )

def import_inst(self):
    p = filedialog.askopenfilename(
        filetypes=[
            (
                "Instance zip",
                "*.zip",
            )
        ],
    )

    if not p:
        return

    try:
        n = instances.import_from_zip(
            p
        )

        self._refresh_list()

        self.status.config(
            text=f"imported {n}",
            foreground=ACCENT,
        )

    except Exception as e:
        messagebox.showerror(
            "Blemm",
            str(e),
        )

def make_shortcut(self):
    if not self.sel:
        return

    try:
        p = instances.shortcut(
            self.sel
        )

        self.status.config(
            text=f"shortcut → {p}",
            foreground=ACCENT,
        )

    except Exception as e:
        messagebox.showerror(
            "Blemm",
            str(e),
        )

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

    core.set_game_dir(
        instances.instance_dir(
            self.sel
        )
    )

    try:
        added = core.add_content_auto(
            paths
        )

        self.status.config(
            text=", ".join(added),
            foreground=ACCENT,
        )

        self._sel_ev()
        self._update_optifine_status()

    except Exception as e:
        messagebox.showerror(
            "Blemm",
            str(e),
        )

# ---------- modrinth ----------

def browse_mods(self):
    if not self.sel:
        return

    d = tk.Toplevel(
        self.root
    )

    d.title(
        f"Modrinth — {self.sel}"
    )

    d.configure(
        bg=BG
    )

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

    ttk.Button(
        top,
        text="Search",
        command=lambda: search(),
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

    ttk.Button(
        mid,
        text="⬇  Install selected",
        style="Play.TButton",
        command=lambda: install(),
    ).pack(
        side="left"
    )

    lbl = ttk.Label(
        f,
        text="type a name, Search, Ctrl/Shift+click to multi-select, Install",
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
                    f'{h["title"]}  — '
                    f'{h["author"]}  '
                    f'({h["downs"]}↓)',
                )

            lbl.config(
                text=(
                    f"{len(hits)} results for "
                    f"{self.version} / "
                    f"{ptype.get()}"
                    + (
                        f" / {self.loader}"
                        if ld
                        else ""
                    )
                ),
                foreground=FG,
            )

        except Exception as e:
            lbl.config(
                text=f"search failed: {e}"
            )

    def install(_=None):
        sel = results.curselection()

        if not sel:
            return

        ok, errs = [], []

        for i in sel:
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

                fn = instances.modrinth_install(
                    h["id"],
                    self.version,
                    ld,
                    ptype.get(),
                )

                ok.append(fn)

            except Exception as e:
                errs.append(
                    f'{h["title"]}: {e}'
                )

        msg = (
            f"installed {len(ok)}: "
            f"{', '.join(ok)}"
            if ok
            else ""
        )

        if errs:
            msg += (
                "\nfailed: "
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

    results.bind(
        "<Double-Button-1>",
        lambda e: None,
    )

# ---------- play ----------

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
            (
                "stage",
                t,
                dn,
                tt,
            )
        )
    )

    name = self.sel

    # Capture these before starting the worker so the GUI variables
    # are not being read from another thread while the user changes them.
    username = self._uname.get() or "Blemm"
    ram = self._ram.get()
    use_optifine = bool(
        self._optifine.get()
    )

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
            ld = cfg.get("loader")

            if ld == "forge":
                vid = core.install_forge(
                    vid,
                    cfg.get(
                        "loader_build"
                    ),
                )

            elif ld == "neoforge":
                b = instances.install_neoforge(
                    vid,
                    cfg.get(
                        "loader_build"
                    ),
                )

                cfg["loader_build"] = b

                instances.save_cfg(
                    name,
                    cfg,
                )

            elif ld == "fabric":
                b = instances.install_fabric(
                    vid
                )

                cfg.setdefault(
                    "loader_build",
                    b,
                )

                instances.save_cfg(
                    name,
                    cfg,
                )

            # Make sure OptiFine is actually present when the user
            # has enabled it. We do NOT silently download it here:
            # the user can explicitly install it from the GUI or
            # manually. This is what allows manual fallback.
            if use_optifine:
                status = core.get_optifine_status()

                if not status["installed"]:
                    raise RuntimeError(
                        "OptiFine is enabled, but no OptiFine "
                        "mod was found in this instance.\n\n"
                        "Use 'Install OptiFine' or "
                        "'Install OptiFine manually' first."
                    )

                if not (
                    ld in (
                        "forge",
                        "neoforge",
                    )
                ):
                    self.q.put(
                        (
                            "msg",
                            "WARNING: OptiFine is installed, "
                            "but this instance is not using "
                            "Forge/NeoForge."
                        )
                    )

            self.q.put(
                (
                    "msg",
                    f"launching {name}: {vid}",
                )
            )

            core.launch(
                vid,
                username,
                ram,
                optifine=use_optifine,
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
            core.set_reporter(
                None
            )

            self.q.put(
                (
                    "error",
                    f"aborted: {e}",
                )
            )

        except Exception as e:
            core.set_reporter(
                None
            )

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

# ---------- queue ----------

def _log_message(self, message):
    self.log.config(
        state="normal"
    )

    self.log.insert(
        "end",
        message + "\n",
    )

    self.log.see(
        "end"
    )

    self.log.config(
        state="disabled"
    )

def _drain(self):
    try:
        while True:
            kind, *data = (
                self.q.get_nowait()
            )

            if kind == "stage":
                t, dn, tt = data

                if tt:
                    self.status.config(
                        text=(
                            f"{t}  "
                            f"({dn:,} / {tt:,})"
                        ),
                        foreground=FG,
                    )

                    self.bar.config(
                        mode="determinate",
                        value=(
                            dn / tt * 100
                        ),
                    )

                else:
                    self.status.config(
                        text=t,
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
                self._log_message(
                    data[0]
                )

            elif kind == "optifine_done":
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

                self._log_message(
                    data[0]
                )

                self._update_optifine_status()

            elif kind == "optifine_failed":
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
                    text="OptiFine installation failed",
                    foreground=DANGER,
                )

                self._log_message(
                    "OptiFine ERROR: "
                    + data[0]
                )

                # This is intentional: automatic installation
                # failure does NOT prevent manual installation.
                messagebox.showerror(
                    "OptiFine installation failed",
                    data[0]
                    + "\n\n"
                    "You can download the correct OptiFine "
                    "installer yourself and use "
                    "'Install OptiFine manually'.",
                    parent=self.root,
                )

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

                self._log_message(
                    "ERROR: " + data[0]
                )

    except queue.Empty:
        pass

    self.root.after(
        100,
        self._drain,
    )
```

def run():
root = tk.Tk()
App(root)
root.mainloop()
