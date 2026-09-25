"""BlemmLauncher GUI - tabbed desktop launcher UI."""

import os
import shutil
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from . import core, instances, server


BG = "#07110b"
PANEL = "#0b1911"
CARD = "#102218"
FIELD = "#142b1d"
FG = "#edfff2"
MUTED = "#82a995"
ACCENT = "#38ed7c"
ACCENT2 = "#19b95b"
SUCCESS = "#55f58b"
DANGER = "#ff687a"
GREEN_DARK = "#0a3a20"
GREEN_MID = "#18b85b"
GREEN_SOFT = "#2de574"


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
        troughcolor=GREEN_DARK,
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
        background=[("selected", GREEN_DARK), ("active", "#12351f")],
        foreground=[("selected", ACCENT), ("active", FG)],
    )
    s.configure("TButton", background=FIELD, foreground=FG, padding=(10, 7), font=("Segoe UI", 9, "bold"))
    s.map("TButton", background=[("active", GREEN_DARK), ("pressed", GREEN_MID)])
    s.configure(
        "Primary.TButton",
        background=ACCENT2,
        foreground="#04130a",
        font=("Segoe UI", 10, "bold"),
        padding=(14, 9),
    )
    s.map("Primary.TButton", background=[("active", GREEN_SOFT)])
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
        troughcolor=GREEN_DARK,
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
        self._server_name = None
        self._server_path = ""
        self._server_edit_path = None
        self._server_editor_dirty = False

        self._uname = tk.StringVar(value="Blemm")
        self._ram = tk.StringVar(value="4G")
        self._optifine = tk.BooleanVar(value=False)

        self._build_header()
        self._build_tabs()
        self._build_status()

        core.set_reporter(self._on_report)
        root.after(100, self._drain)

        self._refresh_list()
        self._animate_status()
        threading.Thread(target=self._load_versions, daemon=True).start()

    def _build_header(self):
        head = tk.Frame(self.root, bg=BG, height=58)
        head.pack(fill="x", padx=12, pady=(10, 4))
        head.pack_propagate(False)

        self.menu_button = tk.Button(
            head, text="☰", bg=BG, fg=FG,
            activebackground=BG, activeforeground=ACCENT,
            relief="flat", bd=0, highlightthickness=0,
            font=("Segoe UI Symbol", 19), cursor="hand2",
            command=self.toggle_navigation
        )
        self.menu_button.pack(side="left", padx=(2, 10))

        title_box = tk.Frame(head, bg=BG)
        title_box.pack(side="left", fill="y")
        tk.Label(
            title_box, text="BlemmLauncher", bg=BG, fg=FG,
            font=("Segoe UI", 19, "bold")
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            title_box, text="Minecraft, simplified.", bg=BG, fg=ACCENT,
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")

        self.current_page = tk.Label(
            head, text="Play", bg=BG, fg=MUTED,
            font=("Segoe UI", 9)
        )
        self.current_page.pack(side="right", padx=8, pady=(8, 0))

    def _build_tabs(self):
        # The old top Notebook is intentionally gone. Navigation lives in a
        # hidden slide-out drawer opened by the three-line menu button.
        self.content_area = tk.Frame(self.root, bg=BG)
        self.content_area.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self.play_tab = tk.Frame(self.content_area, bg=BG)
        self.loader_tab = tk.Frame(self.content_area, bg=BG)
        self.modrinth_tab = tk.Frame(self.content_area, bg=BG)
        self.server_tab = tk.Frame(self.content_area, bg=BG)
        self.log_tab = tk.Frame(self.content_area, bg=BG)

        self.pages = {
            "Play": self.play_tab,
            "Install": self.loader_tab,
            "Modrinth": self.modrinth_tab,
            "Server": self.server_tab,
            "Logs": self.log_tab,
        }

        for page in self.pages.values():
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_play_tab()
        self._build_loader_tab()
        self._build_modrinth_tab()
        self._build_server_tab()
        self._build_log_tab()

        self._build_navigation()
        self.show_page("Play")

    def _build_navigation(self):
        self.drawer_width = 245
        self.drawer_open = False

        self.drawer = tk.Frame(
            self.root, bg="#0a1510",
            highlightthickness=1, highlightbackground="#173522"
        )
        self.drawer.place(
            x=-self.drawer_width, y=0,
            width=self.drawer_width, relheight=1
        )

        top = tk.Frame(self.drawer, bg="#0a1510")
        top.pack(fill="x", padx=16, pady=(18, 12))

        tk.Label(
            top, text="MENU", bg="#0a1510", fg=ACCENT,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left")

        tk.Button(
            top, text="×", bg="#0a1510", fg=MUTED,
            activebackground="#0a1510", activeforeground=FG,
            relief="flat", bd=0, font=("Segoe UI", 17),
            cursor="hand2", command=self.close_navigation
        ).pack(side="right")

        tk.Label(
            self.drawer, text="Navigate", bg="#0a1510", fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=18, pady=(2, 10))

        for name, icon in [
            ("Play", "⌂"),
            ("Install", "+"),
            ("Modrinth", "◇"),
            ("Server", "▣"),
            ("Logs", "≡"),
        ]:
            self._nav_button(name, icon)

        tk.Frame(self.drawer, bg="#173522", height=1).pack(
            fill="x", padx=18, pady=(18, 12)
        )
        tk.Label(
            self.drawer, text="BlemmLauncher",
            bg="#0a1510", fg="#507360",
            font=("Segoe UI", 8)
        ).pack(anchor="w", padx=18)

    def _nav_button(self, name, icon):
        wrap = tk.Frame(self.drawer, bg="#0a1510")
        wrap.pack(fill="x", padx=12, pady=3)

        canvas = tk.Canvas(
            wrap, width=215, height=44,
            bg="#0a1510", highlightthickness=0, bd=0
        )
        canvas.pack(fill="x")

        def draw(active=False, hover=False):
            canvas.delete("all")
            if active:
                fill = GREEN_DARK
                outline = GREEN_MID
            elif hover:
                fill = "#112c1c"
                outline = "#1c5a35"
            else:
                fill = "#0d1e14"
                outline = "#142a1d"

            canvas.create_rounded_rectangle if False else None
            # Rounded pill using overlapping rectangles + circles.
            x1, y1, x2, y2, r = 2, 2, 213, 42, 14
            canvas.create_rectangle(x1+r, y1, x2-r, y2, fill=fill, outline="")
            canvas.create_rectangle(x1, y1+r, x2, y2-r, fill=fill, outline="")
            canvas.create_oval(x1, y1, x1+2*r, y1+2*r, fill=fill, outline="")
            canvas.create_oval(x2-2*r, y1, x2, y1+2*r, fill=fill, outline="")
            canvas.create_oval(x1, y2-2*r, x1+2*r, y2, fill=fill, outline="")
            canvas.create_oval(x2-2*r, y2-2*r, x2, y2, fill=fill, outline="")
            if active:
                canvas.create_rectangle(2, 11, 5, 33, fill=ACCENT, outline="")
            canvas.create_text(
                27, 22, text=icon, fill=ACCENT if active else MUTED,
                font=("Segoe UI Symbol", 12, "bold")
            )
            canvas.create_text(
                51, 22, text=name, anchor="w",
                fill=FG if active else "#b5c6bb",
                font=("Segoe UI", 10, "bold")
            )

        draw(False, False)

        canvas.bind("<Enter>", lambda _e: draw(name == getattr(self, "_page_name", ""), True))
        canvas.bind("<Leave>", lambda _e: draw(name == getattr(self, "_page_name", ""), False))
        canvas.bind("<Button-1>", lambda _e, n=name: self.show_page(n))

        setattr(self, "_nav_" + name.lower(), canvas)

    def show_page(self, name):
        page = self.pages.get(name)
        if page is None:
            return
        page.lift()
        self._page_name = name
        self.current_page.config(text=name)
        self._refresh_nav_buttons()
        self.close_navigation()

    def _refresh_nav_buttons(self):
        for name in self.pages:
            canvas = getattr(self, "_nav_" + name.lower(), None)
            if canvas is None:
                continue
            active = name == getattr(self, "_page_name", "")
            canvas.event_generate("<Leave>")
            # Redraw through the same event path by invoking a lightweight
            # click/hover-neutral repaint.
            canvas.delete("all")
            fill = GREEN_DARK if active else "#0d1e14"
            x1, y1, x2, y2, r = 2, 2, 213, 42, 14
            for args in [
                (x1+r, y1, x2-r, y2),
                (x1, y1+r, x2, y2-r),
            ]:
                canvas.create_rectangle(*args, fill=fill, outline="")
            canvas.create_oval(x1, y1, x1+2*r, y1+2*r, fill=fill, outline="")
            canvas.create_oval(x2-2*r, y1, x2, y1+2*r, fill=fill, outline="")
            canvas.create_oval(x1, y2-2*r, x1+2*r, y2, fill=fill, outline="")
            canvas.create_oval(x2-2*r, y2-2*r, x2, y2, fill=fill, outline="")
            if active:
                canvas.create_rectangle(2, 11, 5, 33, fill=ACCENT, outline="")
            icons = {"Play": "⌂", "Install": "+", "Modrinth": "◇", "Server": "▣", "Logs": "≡"}
            canvas.create_text(
                27, 22, text=icons[name],
                fill=ACCENT if active else MUTED,
                font=("Segoe UI Symbol", 12, "bold")
            )
            canvas.create_text(
                51, 22, text=name, anchor="w",
                fill=FG if active else "#b5c6bb",
                font=("Segoe UI", 10, "bold")
            )

    def toggle_navigation(self):
        if self.drawer_open:
            self.close_navigation()
        else:
            self.open_navigation()

    def open_navigation(self):
        if self.drawer_open:
            return
        self.drawer_open = True
        self._animate_drawer(-self.drawer_width, 0)

    def close_navigation(self):
        if not getattr(self, "drawer_open", False):
            return
        self.drawer_open = False
        self._animate_drawer(0, -self.drawer_width)

    def _animate_drawer(self, start, end, step=0):
        distance = end - start
        steps = 10
        if step >= steps:
            self.drawer.place_configure(x=end)
            return
        x = start + int(distance * ((step + 1) / steps))
        self.drawer.place_configure(x=x)
        self.root.after(12, lambda: self._animate_drawer(start, end, step + 1))

    def _build_status(self):
        box = ttk.Frame(self.root)
        box.pack(fill="x", padx=16, pady=(0, 10))
        self.status = ttk.Label(box, text="Loading Minecraft versions…", anchor="w")
        self.status.pack(fill="x")
        self.bar = ttk.Progressbar(box, mode="indeterminate")
        self.bar.pack(fill="x", pady=(4, 0))

    def _build_play_tab(self):
        """Clean instance dashboard inspired by modern Minecraft launchers."""
        tab = self.play_tab
        tab.configure(padx=0, pady=0)  # Fixed: Changed padding to padx and pady
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        top = tk.Frame(tab, bg=BG)
        top.grid(row=0, column=0, sticky="ew", pady=(4, 12))
        top.columnconfigure(1, weight=1)

        greeting = tk.Frame(top, bg=BG)
        greeting.grid(row=0, column=0, sticky="w")
        tk.Label(
            greeting, text="Greetings!", bg=BG, fg=FG,
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        tk.Label(
            greeting, text="Choose a Minecraft instance to play.",
            bg=BG, fg=MUTED, font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(2, 0))

        controls = tk.Frame(top, bg=BG)
        controls.grid(row=0, column=1, sticky="e")
        ttk.Button(controls, text="Import", command=self.import_inst).pack(side="left", padx=3)
        ttk.Button(controls, text="Import Client", command=self.import_client_dialog).pack(side="left", padx=3)
        ttk.Button(controls, text="Export", command=self.export_inst).pack(side="left", padx=3)
        ttk.Button(controls, text="Delete", command=self.del_inst).pack(side="left", padx=3)

        body = tk.Frame(tab, bg=BG)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.instance_canvas = tk.Canvas(
            body, bg=BG, highlightthickness=0, bd=0
        )
        self.instance_scroll = ttk.Scrollbar(
            body, orient="vertical", command=self.instance_canvas.yview
        )
        self.instance_grid = tk.Frame(self.instance_canvas, bg=BG)

        self.instance_grid.bind(
            "<Configure>",
            lambda _e: self.instance_canvas.configure(
                scrollregion=self.instance_canvas.bbox("all")
            )
        )
        self.instance_canvas.create_window(
            (0, 0), window=self.instance_grid, anchor="nw", width=1
        )
        self.instance_canvas.configure(yscrollcommand=self.instance_scroll.set)
        self.instance_canvas.grid(row=0, column=0, sticky="nsew")
        self.instance_scroll.grid(row=0, column=1, sticky="ns")

        self.instance_canvas.bind(
            "<Configure>",
            lambda e: self.instance_canvas.itemconfigure(
                self.instance_canvas.find_withtag("all")[0], width=e.width
            )
        )

        bottom = tk.Frame(tab, bg=BG)
        bottom.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)

        self.i_title = tk.Label(
            bottom, text="Select an instance", bg=BG, fg=FG,
            font=("Segoe UI", 12, "bold"), anchor="w"
        )
        self.i_title.grid(row=0, column=0, sticky="w")
        self.i_info = tk.Label(
            bottom, text="Your Minecraft instances will appear above.",
            bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w"
        )
        self.i_info.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.play_btn = ttk.Button(
            bottom, text="▶  PLAY", style="Play.TButton",
            command=self.play, state="disabled"
        )
        self.play_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=(15, 0))

        options = ttk.Frame(bottom)
        options.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(options, text="Username", style="Muted.TLabel").pack(side="left")
        ttk.Entry(options, textvariable=self._uname, width=12).pack(side="left", padx=(6, 14))
        ttk.Label(options, text="RAM", style="Muted.TLabel").pack(side="left")
        ttk.Combobox(
            options, textvariable=self._ram,
            values=["2G", "4G", "6G", "8G", "12G", "16G"],
            width=5, state="readonly"
        ).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(
            options, text="OptiFine", variable=self._optifine,
            command=self._save_optifine_setting
        ).pack(side="left")
        ttk.Button(
            options, text="Install OptiFine…",
            command=self.install_optifine
        ).pack(side="left", padx=(8, 0))

        self._empty_instances = tk.Label(
            self.instance_grid,
            text="No instances yet.\nCreate one from the Install tab.",
            bg=BG, fg=MUTED, font=("Segoe UI", 11),
            justify="center"
        )

    def _instance_palette(self, name):
        palettes = [
            ("#173f2b", "#2de574", "#0c2418"),
            ("#253d54", "#63b3ed", "#111d2b"),
            ("#463221", "#f0b35a", "#24180e"),
            ("#3d2449", "#d88cff", "#21142a"),
            ("#263e39", "#6ee7c8", "#101e1b"),
            ("#3e2b38", "#f08ba9", "#21151c"),
        ]
        return palettes[abs(hash(name)) % len(palettes)]

    def _instance_card(self, name, index):
        cfg = instances.load_cfg(name)
        version = str(cfg.get("version", "?"))
        loader = str(cfg.get("loader") or "vanilla").title()
        mods = self._count_mods(name)
        c1, c2, c3 = self._instance_palette(name)

        card = tk.Frame(
            self.instance_grid, bg="#0e1712",
            highlightthickness=1, highlightbackground="#17261d",
            width=205, height=285
        )
        card.grid(
            row=index // 4, column=index % 4,
            padx=8, pady=8, sticky="nsew"
        )
        card.grid_propagate(False)

        art = tk.Canvas(card, width=203, height=185, bg=c1, highlightthickness=0, bd=0)
        art.pack(fill="x")

        # Lightweight generated artwork: sky, horizon, sun and terrain.
        art.create_rectangle(0, 0, 203, 120, fill=c1, outline="")
        art.create_oval(145, 18, 181, 54, fill=c2, outline="")
        art.create_polygon(
            0, 120, 45, 76, 78, 118, 112, 70, 165, 120,
            203, 82, 203, 185, 0, 185, fill=c3, outline=""
        )
        art.create_rectangle(0, 145, 203, 185, fill="#0a130e", outline="")
        art.create_text(
            12, 15, text=loader.upper(), anchor="nw",
            fill="#d9ffe5", font=("Segoe UI", 8, "bold")
        )

        info = tk.Frame(card, bg="#0e1712")
        info.pack(fill="both", expand=True, padx=12, pady=(8, 5))

        tk.Label(
            info, text=name, bg="#0e1712", fg=FG,
            font=("Segoe UI", 11, "bold"), anchor="w"
        ).pack(fill="x")

        tk.Label(
            info,
            text="◈ " + version + "    ◇ " + loader,
            bg="#0e1712", fg=MUTED,
            font=("Segoe UI", 8), anchor="w"
        ).pack(fill="x", pady=(2, 1))

        tk.Label(
            info,
            text=str(mods) + " mods",
            bg="#0e1712", fg=MUTED,
            font=("Segoe UI", 8), anchor="w"
        ).pack(fill="x")

        btn = tk.Button(
            info, text="PLAY",
            bg=GREEN_DARK, fg=ACCENT, activebackground=GREEN_MID,
            activeforeground="#ffffff", relief="flat", bd=0,
            font=("Segoe UI", 8, "bold"), cursor="hand2",
            command=lambda n=name: self._quick_play(n)
        )
        btn.pack(fill="x", pady=(5, 0), ipady=4)

        def select(_event=None, n=name):
            self._select_instance(n)

        def enter(_event=None):
            card.configure(highlightbackground=GREEN_MID)
            btn.configure(bg="#14552e")

        def leave(_event=None):
            card.configure(highlightbackground="#17261d")
            btn.configure(bg=GREEN_DARK)

        for widget in (card, art, info):
            widget.bind("<Button-1>", select)
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
        for widget in info.winfo_children():
            widget.bind("<Button-1>", select)
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)

    def _quick_play(self, name):
        self._select_instance(name)
        self.play()

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
                "Install Vanilla, Fabric, NeoForge, or Forge automatically. "
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
        self.loader_type_combo = ttk.Combobox(
            card, textvariable=self.loader_type,
            values=["vanilla", "fabric", "neoforge", "forge"], state="readonly"
        )
        self.loader_type_combo.grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=6)
        self.loader_type_combo.bind("<<ComboboxSelected>>", self._loader_changed)

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
            card, text="Install / Create", style="Primary.TButton",
            command=self.install_loader
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        card.rowconfigure(6, weight=1)
        self._refresh_loader_instances()

    def _loader_changed(self, _event=None):
        if self.loader_type.get().lower() == "vanilla":
            self.loader_info.config(
                text="Vanilla installs the selected Minecraft version with no mod loader."
            )
        else:
            self.loader_info.config(
                text="BlemmLauncher will download and install the correct "
                + self.loader_type.get().title() + " build automatically."
            )

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
            text="Browse compatible projects like a real in-launcher marketplace.",
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
            values=["mod", "modpack", "shader", "resourcepack", "datapack", "world"], state="readonly", width=18
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
        card = tk.Frame(
            self.modrinth_cards, bg=CARD, highlightthickness=1,
            highlightbackground=GREEN_DARK, bd=0
        )
        card.pack(fill="x", padx=12, pady=7, ipady=3)
        card.columnconfigure(1, weight=1)

        title = hit.get("title", "Unknown")
        author = hit.get("author", "Unknown")
        downloads = hit.get("downs", 0)
        desc = hit.get("desc", "") or "No description available."

        badge = tk.Label(
            card, text=ptype.upper(), bg=GREEN_DARK, fg=ACCENT,
            font=("Segoe UI", 8, "bold"), width=10, pady=12
        )
        badge.grid(row=0, column=0, rowspan=3, padx=(12, 14), pady=8)

        tk.Label(
            card, text=title, bg=CARD, fg=FG,
            font=("Segoe UI", 13, "bold"), anchor="w"
        ).grid(row=0, column=1, sticky="ew", pady=(9, 1))
        ttk.Label(
            card,
            text="by " + author + "  •  " + f"{downloads:,}" + " downloads  •  " + ptype,
            style="MutedCard.TLabel"
        ).grid(row=1, column=1, sticky="w", pady=(1, 5))
        ttk.Label(
            card, text=desc, style="MutedCard.TLabel",
            wraplength=600, justify="left"
        ).grid(row=2, column=1, sticky="w")
        ttk.Button(
            card, text="INSTALL", style="Primary.TButton",
            command=lambda h=hit: self._install_modrinth(
                h, target_name, mc_version, loader, ptype
            )
        ).grid(row=0, column=2, rowspan=3, padx=(12, 14))

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
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        header = tk.Frame(tab, bg=BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        header.columnconfigure(1, weight=1)
        tk.Label(header, text="Server Panel", bg=BG, fg=FG,
                 font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(header, text="Create, run, configure and manage your local Minecraft servers.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w")
        ttk.Button(header, text="+ New Server", style="Primary.TButton",
                   command=self._new_server_dialog).grid(row=0, column=2, rowspan=2, sticky="e")

        left = ttk.Frame(tab, style="Card.TFrame", padding=10)
        left.grid(row=1, column=0, sticky="nsw", padx=(0, 10))
        tk.Label(left, text="YOUR SERVERS", bg=CARD, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=(2, 8))
        self.server_list = tk.Listbox(
            left, width=25, height=26, bg=FIELD, fg=FG,
            selectbackground=GREEN_DARK, selectforeground=ACCENT,
            relief="flat", borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 10)
        )
        self.server_list.pack(fill="y", expand=True)
        self.server_list.bind("<<ListboxSelect>>", self._server_selected)
        ttk.Button(left, text="Delete Server", command=self._delete_server).pack(fill="x", pady=(8, 0))

        right = tk.Frame(tab, bg=BG)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        info = ttk.Frame(right, style="Card.TFrame", padding=12)
        info.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        info.columnconfigure(1, weight=1)
        self.server_title = tk.Label(info, text="No server selected", bg=CARD, fg=FG,
                                     font=("Segoe UI", 15, "bold"))
        self.server_title.grid(row=0, column=0, sticky="w")
        self.server_meta = tk.Label(info, text="Create a server to get started.",
                                    bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.server_meta.grid(row=1, column=0, sticky="w", pady=(2, 0))
        controls = tk.Frame(info, bg=CARD)
        controls.grid(row=0, column=2, rowspan=2, sticky="e")
        self.server_start_btn = ttk.Button(controls, text="▶ Start", style="Primary.TButton",
                                           command=self._start_server, state="disabled")
        self.server_start_btn.pack(side="left", padx=3)
        self.server_stop_btn = ttk.Button(controls, text="■ Stop",
                                          command=self._stop_server, state="disabled")
        self.server_stop_btn.pack(side="left", padx=3)
        ttk.Button(controls, text="Refresh Files", command=self._refresh_server_files).pack(side="left", padx=3)

        notebook = ttk.Notebook(right)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.server_console_tab = ttk.Frame(notebook, style="Card.TFrame")
        self.server_files_tab = ttk.Frame(notebook, style="Card.TFrame")
        notebook.add(self.server_console_tab, text="  Console  ")
        notebook.add(self.server_files_tab, text="  File Manager  ")

        console_wrap = tk.Frame(self.server_console_tab, bg=CARD)
        console_wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.server_console = scrolledtext.ScrolledText(
            console_wrap, height=9, bg="#06100a", fg=FG,
            insertbackground=FG, relief="flat", borderwidth=0,
            font=("Consolas", 9)
        )
        self.server_console.pack(fill="both", expand=True)
        command_bar = tk.Frame(console_wrap, bg=CARD)
        command_bar.pack(fill="x", pady=(7, 0))
        self.server_command = ttk.Entry(command_bar)
        self.server_command.pack(side="left", fill="x", expand=True)
        self.server_command.bind("<Return>", lambda _e: self._send_server_command())
        ttk.Button(command_bar, text="Send", command=self._send_server_command).pack(side="left", padx=(7, 0))

        files = self.server_files_tab
        files.columnconfigure(0, weight=0)
        files.columnconfigure(1, weight=1)
        files.rowconfigure(1, weight=1)
        filebar = tk.Frame(files, bg=CARD)
        filebar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 5))
        self.server_path_label = tk.Label(filebar, text="/", bg=CARD, fg=ACCENT,
                                          font=("Segoe UI", 9, "bold"))
        self.server_path_label.pack(side="left")
        for label, command in [
            ("Up", self._server_up),
            ("New File", self._server_new_file),
            ("New Folder", self._server_new_folder),
            ("Rename", self._server_rename),
            ("Delete", self._server_remove),
            ("Upload", self._server_upload),
        ]:
            ttk.Button(filebar, text=label, command=command).pack(side="right", padx=2)

        tree_frame = tk.Frame(files, bg=CARD)
        tree_frame.grid(row=1, column=0, sticky="nsw", padx=(8, 5), pady=(0, 8))
        self.server_tree = ttk.Treeview(tree_frame, columns=("type", "size"), show="tree headings", height=17)
        self.server_tree.heading("#0", text="Name")
        self.server_tree.heading("type", text="Type")
        self.server_tree.heading("size", text="Size")
        self.server_tree.column("#0", width=210)
        self.server_tree.column("type", width=70)
        self.server_tree.column("size", width=80)
        self.server_tree.pack(side="left", fill="y")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.server_tree.yview)
        sb.pack(side="right", fill="y")
        self.server_tree.configure(yscrollcommand=sb.set)
        self.server_tree.bind("<Double-1>", self._server_open_item)

        editor_frame = tk.Frame(files, bg=CARD)
        editor_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 8), pady=(0, 8))
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(1, weight=1)
        self.server_edit_label = tk.Label(editor_frame, text="Select a text file to edit",
                                           bg=CARD, fg=MUTED, anchor="w",
                                           font=("Segoe UI", 9, "bold"))
        self.server_edit_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.server_editor = scrolledtext.ScrolledText(
            editor_frame, bg=FIELD, fg=FG, insertbackground=ACCENT,
            relief="flat", borderwidth=0, undo=True, wrap="none",
            font=("Consolas", 9)
        )
        self.server_editor.grid(row=1, column=0, sticky="nsew")
        self.server_editor.bind("<<Modified>>", self._server_editor_changed)
        ttk.Button(editor_frame, text="Save File", style="Primary.TButton",
                   command=self._save_server_file).grid(row=2, column=0, sticky="e", pady=(6, 0))

        self._refresh_servers()

    def _refresh_servers(self):
        if not hasattr(self, "server_list"):
            return
        names = server.list_servers()
        self.server_list.delete(0, "end")
        for name in names:
            self.server_list.insert("end", name)
        if self._server_name in names:
            i = names.index(self._server_name)
            self.server_list.selection_set(i)
            self.server_list.see(i)
            self._load_server_panel(self._server_name)
        elif names:
            self.server_list.selection_set(0)
            self._load_server_panel(names[0])
        else:
            self._server_name = None
            self.server_title.config(text="No server selected")
            self.server_meta.config(text="Create a server to get started.")
            self._clear_server_files()

    def _server_selected(self, _event=None):
        sel = self.server_list.curselection()
        if sel:
            self._load_server_panel(self.server_list.get(sel[0]))

    def _load_server_panel(self, name):
        self._server_name = name
        try:
            cfg = server.load(name)
            state = "RUNNING" if server.running(name) else "STOPPED"
            self.server_title.config(text=name)
            self.server_meta.config(text=f"{cfg.get('type','Server')}  •  Minecraft {cfg.get('version','?')}  •  {cfg.get('ram','4G')} RAM  •  {state}")
            self.server_start_btn.config(state="disabled" if server.running(name) else "normal")
            self.server_stop_btn.config(state="normal" if server.running(name) else "disabled")
            self._refresh_server_files()
        except Exception as e:
            self.log_message("Server panel error: " + str(e))

    def _new_server_dialog(self):
        d = tk.Toplevel(self.root)
        d.title("Create Server")
        d.geometry("520x430")
        d.configure(bg=BG)
        d.transient(self.root)
        d.grab_set()
        card = ttk.Frame(d, style="Card.TFrame", padding=18)
        card.pack(fill="both", expand=True)
        card.columnconfigure(1, weight=1)

        name = tk.StringVar(value="My Server")
        kind = tk.StringVar(value="Paper")
        version = tk.StringVar()
        ram = tk.StringVar(value="4G")
        java = tk.StringVar(value="java")

        ttk.Label(card, text="Create a Server", style="Big.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(card, text="Server name", style="MutedCard.TLabel").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(card, textvariable=name).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=7)
        ttk.Label(card, text="Server type", style="MutedCard.TLabel").grid(row=2, column=0, sticky="w", pady=7)
        type_box = ttk.Combobox(card, textvariable=kind, values=list(server.SERVER_TYPES), state="readonly")
        type_box.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=7)
        ttk.Label(card, text="Minecraft version", style="MutedCard.TLabel").grid(row=3, column=0, sticky="w", pady=7)
        version_box = ttk.Combobox(card, textvariable=version, state="readonly")
        version_box.grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=7)
        ttk.Label(card, text="RAM", style="MutedCard.TLabel").grid(row=4, column=0, sticky="w", pady=7)
        ttk.Combobox(card, textvariable=ram, values=["2G","4G","6G","8G","12G","16G"], state="readonly").grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=7)
        ttk.Label(card, text="Java executable", style="MutedCard.TLabel").grid(row=5, column=0, sticky="w", pady=7)
        ttk.Entry(card, textvariable=java).grid(row=5, column=1, sticky="ew", padx=(12, 0), pady=7)
        info = ttk.Label(card, text="Loading versions…", style="MutedCard.TLabel", wraplength=430)
        info.grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 8))

        def load_versions():
            try:
                vals = server.versions(kind.get())
                self.root.after(0, lambda: (version_box.configure(values=vals), version.set(vals[0] if vals else "")))
                self.root.after(0, lambda: info.config(text=("Select a version and create the server." if vals else "This server type needs a JAR/installer upload after creation.")))
            except Exception as e:
                self.root.after(0, lambda: info.config(text="Could not load versions: " + str(e)))

        def type_changed(_e=None):
            version.set("")
            threading.Thread(target=load_versions, daemon=True).start()

        type_box.bind("<<ComboboxSelected>>", type_changed)
        threading.Thread(target=load_versions, daemon=True).start()

        def create_now():
            if not name.get().strip() or not version.get():
                messagebox.showinfo("Create Server", "Choose a name and version.", parent=d)
                return
            try:
                self.status.config(text="Creating " + name.get() + " server…")
                cfg = server.create(name.get().strip(), kind.get(), version.get(), ram.get(), java.get().strip() or "java")
                d.destroy()
                self._refresh_servers()
                self._load_server_panel(cfg["name"])
                self.status.config(text="Server created: " + cfg["name"], foreground=SUCCESS)
            except Exception as e:
                messagebox.showerror("Create Server", str(e), parent=d)

        ttk.Button(card, text="Create Server", style="Primary.TButton", command=create_now).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    def _delete_server(self):
        name = self._server_name
        if not name:
            return
        if messagebox.askyesno("Delete Server", "Delete '" + name + "' and ALL of its files?"):
            try:
                server.delete(name)
                self._server_name = None
                self._refresh_servers()
            except Exception as e:
                messagebox.showerror("Delete Server", str(e))

    def _start_server(self):
        if not self._server_name:
            return
        name = self._server_name
        try:
            server.start(name, lambda n, line: self.q.put(("server_output", (n, line), None, None)))
            self.server_console.insert("end", "[BlemmLauncher] Starting " + name + "…\n")
            self.server_console.see("end")
            self._load_server_panel(name)
        except Exception as e:
            messagebox.showerror("Start Server", str(e))

    def _stop_server(self):
        if self._server_name:
            try:
                server.stop(self._server_name)
                self.server_console.insert("end", "[BlemmLauncher] Stop requested.\n")
                self.server_console.see("end")
            except Exception as e:
                messagebox.showerror("Stop Server", str(e))

    def _send_server_command(self):
        if not self._server_name:
            return
        value = self.server_command.get().strip()
        if not value:
            return
        try:
            server.command(self._server_name, value)
            self.server_console.insert("end", "> " + value + "\n")
            self.server_console.see("end")
            self.server_command.delete(0, "end")
        except Exception as e:
            messagebox.showerror("Server Console", str(e))

    def _clear_server_files(self):
        if not hasattr(self, "server_tree"):
            return
        for item in self.server_tree.get_children():
            self.server_tree.delete(item)
        self.server_path_label.config(text="/")
        self.server_edit_label.config(text="Select a text file to edit")
        self.server_editor.delete("1.0", "end")
        self._server_edit_path = None

    def _refresh_server_files(self):
        if not self._server_name:
            self._clear_server_files()
            return
        try:
            self.server_path_label.config(text="/" + (self._server_path or ""))
            for item in self.server_tree.get_children():
                self.server_tree.delete(item)
            for item in server.tree(self._server_name, self._server_path):
                size = "" if item["dir"] else (str(item["size"]) + " B")
                self.server_tree.insert("", "end", iid=item["path"], text=("▸ " if item["dir"] else "   ") + item["name"],
                                        values=("Folder" if item["dir"] else "File", size))
        except Exception as e:
            self.log_message("File manager: " + str(e))

    def _server_open_item(self, _event=None):
        sel = self.server_tree.selection()
        if not sel or not self._server_name:
            return
        rel = sel[0]
        try:
            item = next(x for x in server.tree(self._server_name, self._server_path) if x["path"] == rel)
            if item["dir"]:
                self._server_path = rel
                self._refresh_server_files()
            else:
                self._open_server_file(rel)
        except Exception as e:
            messagebox.showerror("File Manager", str(e))

    def _open_server_file(self, rel):
        try:
            content = server.read_file(self._server_name, rel)
            self.server_editor.delete("1.0", "end")
            self.server_editor.insert("1.0", content)
            self.server_editor.edit_modified(False)
            self._server_edit_path = rel
            self._server_editor_dirty = False
            self.server_edit_label.config(text="Editing  /" + rel, fg=ACCENT)
        except Exception as e:
            messagebox.showerror("File Editor", str(e))

    def _server_editor_changed(self, _event=None):
        if self.server_editor.edit_modified():
            self._server_editor_dirty = True
            self.server_editor.edit_modified(False)

    def _save_server_file(self):
        if not self._server_name or not self._server_edit_path:
            return
        try:
            server.write_file(self._server_name, self._server_edit_path, self.server_editor.get("1.0", "end-1c"))
            self._server_editor_dirty = False
            self.server_edit_label.config(text="Saved  /" + self._server_edit_path, fg=SUCCESS)
            self.status.config(text="Saved " + self._server_edit_path, foreground=SUCCESS)
        except Exception as e:
            messagebox.showerror("Save File", str(e))

    def _server_up(self):
        if self._server_path:
            self._server_path = os.path.dirname(self._server_path).replace(os.sep, "/")
            if self._server_path == ".":
                self._server_path = ""
            self._refresh_server_files()

    def _server_new_file(self):
        if not self._server_name:
            return
        name = tk.simpledialog.askstring("New File", "File name:", parent=self.root)
        if not name:
            return
        rel = os.path.join(self._server_path, name).replace(os.sep, "/")
        try:
            server.create_file(self._server_name, rel)
            self._refresh_server_files()
        except Exception as e:
            messagebox.showerror("New File", str(e))

    def _server_new_folder(self):
        if not self._server_name:
            return
        name = tk.simpledialog.askstring("New Folder", "Folder name:", parent=self.root)
        if not name:
            return
        rel = os.path.join(self._server_path, name).replace(os.sep, "/")
        try:
            server.create_folder(self._server_name, rel)
            self._refresh_server_files()
        except Exception as e:
            messagebox.showerror("New Folder", str(e))

    def _server_rename(self):
        sel = self.server_tree.selection()
        if not sel or not self._server_name:
            return
        old = sel[0]
        name = tk.simpledialog.askstring("Rename", "New name:", initialvalue=os.path.basename(old), parent=self.root)
        if not name:
            return
        new = os.path.join(os.path.dirname(old), name).replace(os.sep, "/")
        try:
            server.rename(self._server_name, old, new)
            self._refresh_server_files()
        except Exception as e:
            messagebox.showerror("Rename", str(e))

    def _server_remove(self):
        sel = self.server_tree.selection()
        if not sel or not self._server_name:
            return
        rel = sel[0]
        if not messagebox.askyesno("Delete", "Delete '" + rel + "'?"):
            return
        try:
            server.remove(self._server_name, rel)
            if self._server_edit_path == rel:
                self._server_edit_path = None
                self.server_editor.delete("1.0", "end")
            self._refresh_server_files()
        except Exception as e:
            messagebox.showerror("Delete", str(e))

    def _server_upload(self):
        if not self._server_name:
            return
        paths = filedialog.askopenfilenames(title="Upload server files")
        if not paths:
            return
        try:
            dest = server.root(self._server_name)
            folder = server.path(self._server_name, self._server_path)
            for src in paths:
                shutil.copy2(src, os.path.join(folder, os.path.basename(src)))
            self._refresh_server_files()
            self.status.config(text="Uploaded " + str(len(paths)) + " file(s)", foreground=SUCCESS)
        except Exception as e:
            messagebox.showerror("Upload", str(e))

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
        for child in self.instance_grid.winfo_children():
            child.destroy()

        names = instances.list_instances()
        if not names:
            self._empty_instances = tk.Label(
                self.instance_grid,
                text="No instances yet.\nCreate one from the Install tab.",
                bg=BG, fg=MUTED, font=("Segoe UI", 11),
                justify="center"
            )
            self._empty_instances.grid(row=0, column=0, columnspan=4, pady=90)
        else:
            for i, name in enumerate(names):
                try:
                    self._instance_card(name, i)
                except Exception as e:
                    self.log_message("Could not display instance " + name + ": " + str(e))

        for col in range(4):
            self.instance_grid.columnconfigure(col, weight=1)

        self.sel = None
        self.version = None
        self.loader = None
        self._optifine.set(False)
        self.play_btn.config(state="disabled")
        self.i_title.config(text="Select an instance")
        self.i_info.config(text="Your Minecraft instances will appear above.")
        self._refresh_loader_instances()
        self._refresh_modrinth_targets()

    def _select_instance(self, name):
        if name not in instances.list_instances():
            return
        self.sel = name
        self._sel_ev_name(name)

    def _sel_ev_name(self, name):
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
                + str(cfg.get("ram", "4G")) + " RAM  •  "
                + str(self._count_mods(name)) + " mods"
            )
        )
        self.play_btn.config(state="normal")
        self._refresh_loader_instances()
        self._refresh_modrinth_targets()

    def _sel_ev(self, _=None):
        selection = getattr(self, "ilist", None)
        if selection is None:
            return
        picked = selection.curselection()
        if picked:
            self._sel_ev_name(selection.get(picked[0]))

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

            if loader == "vanilla":
                cfg = instances.load_cfg(name)
                cfg["loader"] = None
                cfg["loader_build"] = None
                cfg["version"] = mc_version
                instances.save_cfg(name, cfg)
                self.q.put(("loader_installed", (name, "vanilla", mc_version), None, None))
                return

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

    def _animate_status(self, phase=0):
        if not self.root.winfo_exists():
            return
        colors = [ACCENT, GREEN_SOFT, SUCCESS, ACCENT]
        try:
            self.status.configure(foreground=colors[phase % len(colors)])
            self.root.after(180, lambda: self._animate_status(phase + 1))
        except Exception:
            return

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

                elif kind == "server_output":
                    name, line = text
                    if hasattr(self, "server_console") and name == self._server_name:
                        self.server_console.insert("end", str(line) + "\n")
                        self.server_console.see("end")
                        self._load_server_panel(name)

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
