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
        root.geometry("860x600")
        root.minsize(760, 540)

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
            text="instances · loaders · modrinth · import/export",
            style="Muted.TLabel"
        ).pack(side="left", padx=10, pady=(10, 0))

        # ------------------------------------------------------------
        # Body
        # ------------------------------------------------------------

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=14, pady=8)

        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left column ------------------------------------------------

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

        # Right column -----------------------------------------------

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
                "Import hack clients / custom JARs with 'Client…' on the "
                "left. OptiFine: installer JAR or drop a JAR in mods/."
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
