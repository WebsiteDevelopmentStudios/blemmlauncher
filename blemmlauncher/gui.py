import os, threading, queue
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from . import core
from .versions_meta import pretty

BG, PANEL, FIELD = "#1e1f24", "#272930", "#2f323b"
FG, MUTED, ACCENT, DANGER = "#e8e9ee", "#8b8fa3", "#4ade80", "#f87171"

def style_dark(root):
    ttk.Style().theme_use("clam")
    s = ttk.Style()
    s.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL,
                troughcolor=FIELD, arrowcolor=MUTED)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=PANEL)
    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("Title.TLabel", background=BG, foreground=ACCENT, font=("Segoe UI", 22, "bold"))
    s.configure("TEntry", foreground=FG, insertcolor=FG, padding=4)
    s.configure("TCombobox", foreground=FG, padding=4)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD)])
    s.configure("Play.TButton", background=ACCENT, foreground="#10240f",
                font=("Segoe UI", 12, "bold"), padding=(30, 10))
    s.map("Play.TButton", background=[("active", "#6ce89a"), ("disabled", "#39543f")])
    s.configure("TButton", background=FIELD, foreground=FG, padding=6)
    s.map("TButton", background=[("active", "#3a3e49")])
    s.configure("TCheckbutton", background=BG, foreground=FG)
    s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD, thickness=10)

class App:
    def __init__(self, root):
        self.root = root
        root.title("BlemmLauncher")
        root.geometry("520x700"); root.minsize(520, 640)
        root.configure(bg=BG)
        style_dark(root)
        self.version_map = {"Latest release": "release"}
        self.optifine_path = None

        ttk.Label(root, text="◈ BlemmLauncher", style="Title.TLabel").pack(pady=(16, 2))
        ttk.Label(root, text="vanilla · forge · optifine · mods · textures · shaders",
                  style="Muted.TLabel").pack(pady=(0, 12))

        card = ttk.Frame(root, style="Card.TFrame", padding=16)
        card.pack(fill="x", padx=18)
        card.columnconfigure(1, weight=1)

        def row(r, text, widget):
            ttk.Label(card, text=text, style="Muted.TLabel").grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            widget.grid(row=r, column=1, sticky="we", pady=4)

        self.version_var = tk.StringVar(value="Latest release")
        self.version_box = ttk.Combobox(card, textvariable=self.version_var, state="readonly")
        row(0, "Version", self.version_box)

        self.name = ttk.Entry(card); self.name.insert(0, "Blemm")
        row(1, "Username", self.name)

        self.ram = ttk.Combobox(card, values=["2G", "4G", "6G", "8G"], state="readonly")
        self.ram.set("4G")
        row(2, "RAM", self.ram)

        # ---- forge + optifine row ----
        forge_row = ttk.Frame(card, style="Card.TFrame")
        forge_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        self.forge_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(forge_row, text="Use Forge", variable=self.forge_on,
                        command=self._toggle_forge).pack(side="left")
        self.optifine_on = tk.BooleanVar(value=False)
        self.optifine_ck = ttk.Checkbutton(forge_row, text="  Use OptiFine (Forge only)",
                                           variable=self.optifine_on, state="disabled",
                                           command=self._pick_optifine)
        self.optifine_ck.pack(side="left")
        ttk.Button(forge_row, text="pick jar…", command=self._pick_optifine).pack(side="left", padx=6)

        self.forge = ttk.Entry(card, width=14); self.forge.insert(0, "auto")
        self.forge.configure(state="disabled")
        row(4, "Forge build", self.forge)
        self.of_label = ttk.Label(card, text="OptiFine: off — tick Forge to enable",
                                  style="Muted.TLabel")
        self.of_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 2))

        # ---- imports ----
        imp = ttk.Frame(root, style="Card.TFrame", padding=14)
        imp.pack(fill="x", padx=18, pady=(10, 0))
        ttk.Label(imp, text="imports — Blemm sniffs the file and puts it in the right folder:",
                  style="Muted.TLabel").pack(anchor="w")
        btns = ttk.Frame(imp, style="Card.TFrame"); btns.pack(fill="x", pady=(8, 4))
        for text, cmd in [("＋ Mod", self.import_mod), ("＋ Texture pack", self.import_texture),
                          ("＋ Shader pack", self.import_shader), ("✦ Any (auto)", self.import_auto)]:
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 8))
        self.imp_label = ttk.Label(imp, text="", style="Muted.TLabel", wraplength=440)
        self.imp_label.pack(anchor="w")

        self.play_btn = ttk.Button(root, text="▶   PLAY", style="Play.TButton", command=self.play)
        self.play_btn.pack(fill="x", padx=18, pady=14)

        self.status = ttk.Label(root, text="Loading version list…", anchor="w")
        self.status.pack(fill="x", padx=18)
        self.bar = ttk.Progressbar(root, mode="indeterminate", maximum=100)
        self.bar.pack(fill="x", padx=18, pady=(2, 8))

        logcard = ttk.Frame(root, style="Card.TFrame", padding=8)
        logcard.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self.log = scrolledtext.ScrolledText(logcard, height=7, state="disabled",
                                             font=("Consolas", 9), bg=FIELD, fg=FG,
                                             insertbackground=FG, relief="flat")
        self.log.pack(fill="both", expand=True)

        self.q = queue.Queue()
        root.after(100, self._drain)
        threading.Thread(target=self._load_versions, daemon=True).start()

    # ---------- version dropdown ----------
    def _load_versions(self):
        try:
            versions, latest, snapshot = core.list_versions()
            def sort_key(v):
                try: return [int(x) for x in v.split(".") if x.isdigit()]
                except Exception: return [-1]
            chosen = [v for v in versions
                      if sort_key(v) >= [1, 12, 2] and "-" not in v
                      and not v.startswith(("w", "pre", "rc"))]
            chosen.sort(key=sort_key, reverse=True)
            labels = [pretty(v) for v in chosen]
            self.version_map.update(zip(labels, chosen))
            self.q.put(("versions", labels))
        except Exception as e:
            self.q.put(("stage", f"Couldn't load version list: {e}", None, None))

    # ---------- forge / optifine logic ----------
    def _toggle_forge(self):
        if self.forge_on.get():
            self.forge.configure(state="normal")
            self.optifine_ck.configure(state="normal")
            if not self.optifine_path:
                self.of_label.config(text="OptiFine: on (no jar picked yet)", foreground=MUTED)
        else:
            self.forge.configure(state="disabled")
            self.optifine_on.set(False)                    # forge off => optifine off
            self.optifine_ck.configure(state="disabled")
            self.of_label.config(text="OptiFine: off — tick Forge to enable", foreground=MUTED)

    def _pick_optifine(self):
        if not self.optifine_on.get() and not self.forge_on.get():
            # 'pick jar…' button pressed while unticked - just check the box if forge is on
            if self.forge_on.get(): self.optifine_on.set(True)
        if self.optifine_on.get():
            p = filedialog.askopenfilename(title="Pick OptiFine installer jar",
                                          filetypes=[("OptiFine installer", "*.jar")])
            if p:
                self.optifine_path = p
                self.of_label.config(text=f"OptiFine: {os.path.basename(p)} (as Forge mod)",
                                     foreground=ACCENT)
                return
            self.optifine_on.set(False)
        self.optifine_path = None
        self.of_label.config(text="OptiFine: off", foreground=MUTED)

    # ---------- imports ----------
    def _import_files(self, kind):
        paths = filedialog.askopenfilenames(title=f"Import {kind}s",
                                           filetypes=[("Minecraft files", "*.jar *.zip"), ("All files", "*.*")])
        if not paths: return
        try:
            moved = core.add_content_auto(paths, None if kind == "auto" else kind)
            self.imp_label.config(text="Added: " + ", ".join(moved), foreground=ACCENT)
        except Exception as e:
            self.imp_label.config(text=f"Import failed: {e}", foreground=DANGER)

    def import_mod(self):     self._import_files("mod")
    def import_texture(self): self._import_files("resourcepack")
    def import_shader(self): self._import_files("shaderpack")
    def import_auto(self):   self._import_files("auto")

    # ---------- worker -> GUI ----------
    def _drain(self):
        try:
            while True:
                kind, *data = self.q.get_nowait()
                if kind == "stage":
                    text, done, total = data
                    self.status.config(text=text, foreground=FG)
                    if total:
                        self.bar.config(mode="determinate", value=done / total * 100)
                    else:
                        self.bar.config(mode="indeterminate")
                elif kind == "versions":
                    lst, = data
                    self.version_box.config(values=["Latest release"] + lst)
                    self.version_var.set("Latest release")
                    self.status.config(text=f"{len(lst)} versions — newest: {lst[0]}", foreground=MUTED)
                elif kind == "msg":
                    self.log.config(state="normal"); self.log.insert("end", data[0] + "\n")
                    self.log.see("end"); self.log.config(state="disabled")
                elif kind == "done":
                    self.play_btn.config(state="normal", text="▶   PLAY")
                    self.bar.config(mode="determinate", value=100)
                    self.status.config(text=data[0], foreground=ACCENT)
                elif kind == "error":
                    self.play_btn.config(state="normal", text="▶   PLAY")
                    self.bar.stop(); self.bar.config(mode="determinate", value=0)
                    self.status.config(text="Failed — see log", foreground=DANGER)
                    self.log.config(state="normal")
                    self.log.insert("end", f"ERROR: {data[0]}\n"); self.log.see("end")
                    self.log.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    # ---------- play ----------
    def play(self):
        vid = self.version_map.get(self.version_var.get(), self.version_var.get())
        if vid == "Latest release": vid = "release"
        self.play_btn.config(state="disabled", text="Working…")
        self.bar.config(mode="indeterminate"); self.bar.start(20)
        self.status.config(text="Fetching version list…", foreground=FG)
        core.set_reporter(lambda text, done=None, total=None:
                          self.q.put(("stage", text, done, total)))
        # optifine only rides along when forge is ticked AND a jar is picked
        use_optifine = self.optifine_path if (self.forge_on.get() and self.optifine_on.get()) else None
        threading.Thread(target=self._play, args=(vid, use_optifine), daemon=True).start()

    def _play(self, vid, optifine):
        try:
            if self.forge_on.get():
                build = self.forge.get().strip()
                vid = core.install_forge(vid, build if build not in ("", "auto") else None)
            self.q.put(("msg", f"Launching: {vid}" + (" + OptiFine" if optifine else "")))
            core.launch(vid, self.name.get() or "Blemm", self.ram.get(), optifine)
            core.set_reporter(None)
            self.q.put(("done", f"Played {vid} ♥"))
        except Exception as e:
            core.set_reporter(None)
            self.q.put(("error", str(e)))

def run():
    root = tk.Tk(); App(root); root.mainloop()
