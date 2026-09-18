import os, threading, queue, subprocess
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from . import core, instances

BG, PANEL, FIELD = "#1e1f24", "#272930", "#2f323b"
FG, MUTED, ACCENT, DANGER = "#e8e9ee", "#8b8fa3", "#4ade80", "#f87171"

def style_dark(root):
    ttk.Style().theme_use("clam")
    s = ttk.Style()
    s.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL,
                troughcolor=FIELD, arrowcolor=MUTED)
    for n, bg in [("TFrame", BG), ("Card.TFrame", PANEL)]:
        s.configure(n, background=bg)
    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("MutedP.TLabel", background=PANEL, foreground=MUTED)
    s.configure("Title.TLabel", background=BG, foreground=ACCENT, font=("Segoe UI", 18, "bold"))
    s.configure("TEntry", foreground=FG, insertcolor=FG, padding=4)
    s.configure("TCombobox", foreground=FG, padding=4)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD)])
    s.configure("Inst.TButton", background=FIELD, foreground=FG, padding=6, width=13)
    s.map("Inst.TButton", background=[("active", "#3a3e49")])
    s.configure("Play.TButton", background=ACCENT, foreground="#10240f",
                font=("Segoe UI", 12, "bold"), padding=(30, 10))
    s.map("Play.TButton", background=[("active", "#6ce89a"), ("disabled", "#39543f")])
    s.configure("TButton", background=FIELD, foreground=FG, padding=6)
    s.map("TButton", background=[("active", "#3a3e49")])
    s.configure("TCheckbutton", background=PANEL, foreground=FG)
    s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD, thickness=10)
    root.configure(bg=BG)

class App:
    def __init__(self, root):
        self.root = root
        root.title("BlemmLauncher"); root.geometry("860x600"); root.minsize(760, 540)
        style_dark(root)
        self.q = queue.Queue(); self.sel = None; self.version_map = {}

        head = ttk.Frame(root); head.pack(fill="x", padx=14, pady=(10, 2))
        ttk.Label(head, text="◈ BlemmLauncher", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="instances · loaders · modrinth · import/export",
                  style="Muted.TLabel").pack(side="left", padx=10, pady=(10, 0))

        body = ttk.Frame(root); body.pack(fill="both", expand=True, padx=14, pady=8)
        body.columnconfigure(0, weight=0); body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ---- left: instance list ----
        left = ttk.Frame(body, style="Card.TFrame", padding=8)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.ilist = tk.Listbox(left, width=26, bg=FIELD, fg=FG, relief="flat",
                               highlightthickness=0, selectbackground=ACCENT,
                               selectforeground="#10240f", font=("Segoe UI", 11))
        self.ilist.pack(fill="y"); self.ilist.bind("<<ListboxSelect>>", self._sel_ev)
        bb = ttk.Frame(left, style="Card.TFrame"); bb.pack(fill="x", pady=(8, 0))
        for i, (t, c) in enumerate([("＋ New", self.new_inst), ("⭳ Import", self.import_inst),
                                    ("⭱ Export", self.export_inst), ("✂ Shortcut", self.make_shortcut),
                                    ("🗑 Delete", self.del_inst)]):
            ttk.Button(bb, text=t, style="Inst.TButton", command=c).grid(
                row=i // 2, column=i % 2, sticky="we", pady=2, padx=2)
        bb.columnconfigure(0, weight=1); bb.columnconfigure(1, weight=1)

        # ---- right: selected instance ----
        right = ttk.Frame(body, style="Card.TFrame", padding=16)
        right.grid(row=0, column=1, sticky="nsew"); right.columnconfigure(1, weight=1)
        self.i_title = ttk.Label(right, text="pick or create an instance →", style="Title.TLabel")
        self.i_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.i_info = ttk.Label(right, text="", style="MutedP.TLabel", justify="left", anchor="w")
        self.i_info.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        form = [
            ("Username", lambda r: self._mk_entry(right, r, "username")),
            ("RAM",      lambda r: self._mk_ram(right, r)),
            ("Version dropdown", lambda r: self._mk_editbox(right, r)),
        ]
        rf = ttk.Frame(right, style="Card.TFrame"); rf.grid(row=2, column=0, columnspan=2, sticky="w")
        self.play_btn = ttk.Button(right, text="▶   PLAY", style="Play.TButton",
                                   command=self.play, state="disabled")
        self.play_btn.grid(row=3, column=0, columnspan=2, sticky="we", pady=(12, 6))
        ttk.Button(right, text="🔎 Browse mods (Modrinth)", command=self.browse_mods).grid(
            row=4, column=0, columnspan=2, sticky="w")
        ttk.Button(right, text="＋ add mod / pack file…", command=self.add_file).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # status + log
        self.status = ttk.Label(root, text="Loading version list…", anchor="w")
        self.status.pack(fill="x", padx=14)
        self.bar = ttk.Progressbar(root, mode="indeterminate")
        self.bar.pack(fill="x", padx=14, pady=(2, 6))
        logcard = ttk.Frame(root, style="Card.TFrame", padding=6)
        logcard.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.log = scrolledtext.ScrolledText(logcard, height=6, state="disabled",
                                             font=("Consolas", 9), bg=FIELD, fg=FG,
                                             insertbackground=FG, relief="flat")
        self.log.pack(fill="both", expand=True)

        self.root.after(100, self._drain)
        threading.Thread(target=self._load_versions, daemon=True).start()
        self._refresh_list()

    # ---------- small builders ----------
    def _mk_entry(self, parent, r, key):
        self._uname = tk.StringVar()
        e = ttk.Entry(parent, textvariable=self._uname, width=22); e.grid(
            row=r, column=1, sticky="w", padx=10, pady=3)
        ttk.Label(parent, text="Username:", style="MutedP.TLabel").grid(row=r, column=0, sticky="w")
        return e

    def _mk_ram(self, parent, r):
        self._ram = tk.StringVar(value="4G"); parent.grid()  # no-op keep signature
        cb = ttk.Combobox(parent, textvariable=self._ram, values=["2G", "4G", "6G", "8G"],
                          width=8, state="readonly"); cb.grid(row=r, column=2, sticky="w", padx=(10, 2))
        ttk.Label(parent, text="RAM:", style="MutedP.TLabel").grid(row=r, column=3, sticky="w")
        return cb

    def _mk_editbox(self, parent, r): return None

    # ---------- version list ----------
    def _load_versions(self):
        try:
            from .versions_meta import pretty
            versions, latest, _ = core.list_versions()
            def sk(v):
                try: return [int(x) for x in v.split(".") if x.isdigit()]
                except Exception: return [-1]
            chosen = sorted([v for v in versions if sk(v) >= [1, 12, 2] and "-" not in v
                             and not v.startswith(("w", "pre", "rc"))], key=sk, reverse=True)
            labels = [pretty(v) for v in chosen]
            self.version_map.update(zip(labels, chosen))
            self.q.put(("versions", chosen))
        except Exception as e: self.q.put(("error", f"version list failed: {e}"))

    # ---------- instance list ops ----------
    def _refresh_list(self):
        self.ilist.delete(0, "end")
        for n in instances.list_instances(): self.ilist.insert("end", n)
        self.sel = None; self.play_btn.config(state="disabled")

    def _sel_ev(self, _=None):
        if not self.ilist.cur selection if False else self.ilist.curselection(): return
        i = self.ilist.curselection()[0]
        name = self.ilist.get(i)
        cfg = instances.load_cfg(name); self.sel = name
        self.version = cfg["version"]; self._uname.set(cfg.get("username", "Blemm"))
        self._ram.set(cfg.get("ram", "4G")); self.loader = cfg.get("loader")
        self.loader_build = cfg.get("loader_build")
        self.i_title.config(text=name)
        self.i_info.config(text=(f"version: {cfg['version']}    loader: {cfg.get('loader') or 'vanilla'}\n"
                                 f"ram: {cfg.get('ram')}    mods: {self._count_mods(name)}"))
        self.play_btn.config(state="normal")

    def _count_mods(self, name):
        d = os.path.join(instances.instance_dir(name), "mods")
        return len(os.listdir(d)) if os.path.isdir(d) else 0

    # ---------- create / delete / io ----------
    def new_inst(self):
        d = tk.Toplevel(self.root); d.title("New instance"); d.configure(bg=BG); d.geometry("380x240")
        style_dark(d)
        f = ttk.Frame(d, style="Card.TFrame", padding=14); f.pack(fill="both", expand=True)
        def row(r, t, w, cs=1):
            ttk.Label(f, text=t, style="MutedP.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            w.grid(row=r, column=1, columnspan=cs, sticky="we", pady=3, padx=(8, 0))
        name = tk.StringVar(); version = tk.StringVar(value="release")
        loader = tk.StringVar(value="vanilla"); ram = tk.StringVar(value="4G")
        row(0, "Name:", ttk.Entry(f, textvariable=name))
        opts = ["release"] + list(self.version_map.values()) if self.version_map else ["release"]
        row(1, "Version:", ttk.Combobox(f, textvariable=version, values=opts[:60]))
        row(2, "Loader:", ttk.Combobox(f, textvariable=loader,
                                       values=["vanilla", "forge", "fabric", "neoforge"], state="readonly"))
        row(3, "RAM:", ttk.Combobox(f, textvariable=ram, values=["2G", "4G", "6G", "8G"], state="readonly"))
        row(4, "Username:", ttk.Entry(f, textvariable=""))
        uname_w = f.grid_slaves(row=4, column=1)[0]; uvar = tk.StringVar(value="Blemm")
        uname_w.config(textvariable=uvar)

        def go():
            try:
                v = version.get()
                v = self.version_map.get(v, v)
                ld = loader.get(); ld = None if ld == "vanilla" else ld
                instances.create(name.get().strip() or "New Instance", v, ld,
                                 ram.get(), uvar.get() or "Blemm")
                d.destroy(); self._refresh_list()
            except Exception as e: messagebox.showerror("Blemm", str(e), parent=d)
        ttk.Button(f, text="Create", style="Play.TButton", command=go).grid(
            row=5, column=0, columnspan=2, sticky="we", pady=(10, 0))

    def del_inst(self):
        if not self.sel: return
        if messagebox.askyesno("Blemm", f"Delete instance '{self.sel}'?\n(saves are deleted too!)"):
            instances.delete(self.sel); self._refresh_list()

    def export_inst(self):
        if not self.sel: return
        p = filedialog.asksaveasfilename(defaultextension=".zip",
                                         initialfile=f"{self.sel}.zip")
        if p:
            instances.export(self.sel, p); self.status.config(text=f"exported → {p}", foreground=ACCENT)

    def import_inst(self):
        p = filedialog.askopenfilename(filetypes=[("Instance zip", "*.zip")])
        if not p: return
        try:
            n = instances.import_from_zip(p); self._refresh_list()
            self.status.config(text=f"imported {n}", foreground=ACCENT)
        except Exception as e: messagebox.showerror("Blemm", str(e))

    def make_shortcut(self):
        if not self.sel: return
        p = instances.shortcut(self.sel)
        self.status.config(text=f"shortcut → {p}", foreground=ACCENT)

    def add_file(self):
        if not self.sel: return
        paths = filedialog.askopenfilenames(
            filetypes=[("Minecraft files", "*.jar *.zip"), ("All files", "*.*")])
        if paths:
            core.GAME_DIR = instances.instance_dir(self.sel)
            self.status.config(text=", ".join(core.add_content_auto(paths)), foreground=ACCENT)

    # ---------- modrinth ----------
    def browse_mods(self):
        if not self.sel: return
        d = tk.Toplevel(self.root); d.title(f"Modrinth mods — {self.sel}"); d.configure(bg=BG)
        style_dark(d); d.geometry("560x420")
        f = ttk.Frame(d, style="Card.TFrame", padding=10); f.pack(fill="both", expand=True)
        top = ttk.Frame(f, style="Card.TFrame"); top.pack(fill="x")
        q = tk.StringVar()
        ttk.Entry(top, textvariable=q).pack(side="left", fill="x", expand=True)
        results = tk.Listbox(f, bg=FIELD, fg=FG, relief="flat", highlightthickness=0,
                            selectbackground=ACCENT, selectforeground="#10240f")
        results.pack(fill="both", expand=True, pady=8)
        lbl = ttk.Label(f, text="", style="MutedP.TLabel"); lbl.pack()
        hits = []

        def search(_=None):
            nonlocal hits
            try:
                hits = instances.modrinth_search(q.get(), self.version,
                                                 self.loader if self.loader != "vanilla" else None)
                results.delete(0, "end")
                for h in hits: results.insert("end", f'{h["title"]}  —  {h["author"]}  ({h["downs"]}↓)')
                lbl.config(text=f"{len(hits)} results for {self.version}"
                          + (f" / {self.loader}" if self.loader else ""))
            except Exception as e: lbl.config(text=f"search failed: {e}")
        ttk.Button(top, text="Search", command=search).pack(side="left", padx=6)

        def install(_=None):
            if not results.curselection(): return
            h = hits[results.curselection()[0]]
            try:
                fn = instances.modrinth_install(h["id"], self.version,
                                               self.loader if self.loader != "vanilla" else None)
                lbl.config(text=f"installed ✓ {fn}", foreground=ACCENT)
                self._sel_ev()
            except Exception as e: lbl.config(text=f"install failed: {e}")
        results.bind("<Double-Button-1>", install)
        q.set(""); results.focus()

    # ---------- play ----------
    def play(self):
        if not self.sel: return
        self.play_btn.config(state="disabled", text="Working…")
        self.bar.config(mode="indeterminate"); self.bar.start(20)
        self.status.config(text="Preparing…", foreground=FG)
        core.set_reporter(lambda t, d=None, o=None: self.q.put(("stage", t, d, o)))
        name = self.sel
        def worker():
            try:
                cfg = instances.load_cfg(name); instances.use(name, core)
                self.q.put(("stage", "Preparing instance…", None, None))
                vid = cfg["version"]
                ld = cfg.get("loader")
                if ld == "forge":
                    vid = core.install_forge(vid, cfg.get("loader_build"))
                elif ld == "neoforge":
                    b = instances.install_neoforge(vid, cfg.get("loader_build"))
                    save = dict(cfg); save["loader_build"] = b; instances.save_cfg(name, save)
                elif ld == "fabric":
                    if not os.path.exists(os.path.join(core.GAME_DIR, "versions")) or True:
                        b = instances.install_fabric(vid)
                        save = dict(cfg); save.setdefault("loader_build", b); instances.save_cfg(name, save)
                self.q.put(("msg", f"launching {name}: {vid}"))
                core.launch(vid, self._uname.get() or "Blemm", self._ram.get())
                core.set_reporter(None); self.q.put(("done", f"played {name} ♥"))
            except SystemExit as e:
                core.set_reporter(None); self.q.put(("error", f"aborted: {e}"))
            except Exception as e:
                core.set_reporter(None); self.q.put(("error", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    # ---------- queue ----------
    def _drain(self):
        try:
            while True:
                kind, *data = self.q.get_nowait()
                if kind == "stage":
                    t, dn, tt = data
                    self.status.config(text=t, foreground=FG)
                    if tt: self.bar.config(mode="determinate", value=dn / tt * 100)
                    else: self.bar.config(mode="indeterminate")
                elif kind == "versions":
                    self.status.config(text=f"{len(data[0])} versions loaded", foreground=MUTED)
                elif kind == "msg":
                    self.log.config(state="normal"); self.log.insert("end", data[0] + "\n")
                    self.log.see("end"); self.log.config(state="disabled")
                elif kind == "done":
                    self.play_btn.config(state="normal", text="▶   PLAY"); self.bar.stop()
                    self.bar.config(mode="determinate", value=100)
                    self.status.config(text=data[0], foreground=ACCENT)
                elif kind == "error":
                    self.play_btn.config(state="normal", text="▶   PLAY"); self.bar.stop()
                    self.bar.config(mode="determinate", value=0)
                    self.status.config(text="Failed — see log", foreground=DANGER)
                    self.log.config(state="normal"); self.log.insert("end", f"ERROR: {data[0]}\n")
                    self.log.see("end"); self.log.config(state="disabled")
        except queue.Empty: pass
        self.root.after(100, self._drain)

def run():
    root = tk.Tk(); App(root); root.mainloop()
