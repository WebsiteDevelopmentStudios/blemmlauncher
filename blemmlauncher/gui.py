"""BlemmLauncher GUI - tabbed desktop launcher UI."""

import os
import json
import shutil
import queue
import threading
import subprocess
import socket
import sys
import time
import io
import urllib.request
import tkinter as tk
import webbrowser
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from PIL import Image, ImageTk

from . import core, instances, server, updater
from .server_manager import OwnerServerManager
from Dev import auth as dev_auth


BG = "#07110b"
PANEL = "#0b1911"
CARD = "#102218"
FIELD = "#142b1d"
FG = "#9CFFBC"
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
        root.minsize(760, 480)
        style_dark(root)
        # Keep the complete launcher usable in a normal, non-maximized window.
        # Tk scaling is adjusted as the window gets smaller so dense pages do
        # not immediately run below the visible viewport.
        self._ui_scale = 1.0
        root.bind("<Configure>", self._responsive_scale)

        self.q = queue.Queue()
        self.sel = None
        self.version = None
        self.loader = None
        self._all_versions = []
        self._modrinth_hits = []
        self._modrinth_searching = False
        self._modrinth_home_loaded = False
        self._modrinth_image_refs = {}
        self._server_name = None
        self._server_path = ""
        self._server_edit_path = None
        self._server_editor_dirty = False
        # Claimed base domains. Each server stores its own selection.
        self._server_domains = ("blemm.devs.surf", "blemm.vexr.dev")
        self._server_domain_suffix = tk.StringVar(value=self._server_domains[0])

        self._profile_path = os.path.join(instances.LAUNCHERS_ROOT, "profile.json")
        self._profile = self._load_profile()
        self._uname = tk.StringVar(value=self._profile.get("username", "Blemm"))
        self._ram = tk.StringVar(value="4G")
        self._optifine = tk.BooleanVar(value=False)
        self._dev_identity = None
        self._dev_username = tk.StringVar()
        self._dev_password = tk.StringVar()
        self._remote_agent_id = None
        self._remote_agents = []
        self._remote_server = tk.StringVar(value="Survival")
        self._remote_file = tk.StringVar()
        self._owner_agent_started = False

        self._build_header()
        self._build_tabs()
        self._build_status()

        core.set_reporter(self._on_report)
        threading.Thread(
            target=self._check_for_updates,
            daemon=True
        ).start()
        root.after(100, self._drain)

        self._refresh_list()
        self._animate_status()
        threading.Thread(target=self._load_versions, daemon=True).start()

    def _responsive_scale(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        try:
            width = max(1, self.root.winfo_width())
            height = max(1, self.root.winfo_height())
            target = min(1.0, max(0.78, min(width / 1050.0, height / 720.0)))
            if abs(target - self._ui_scale) < 0.035:
                return
            self._ui_scale = target
            self.root.tk.call("tk", "scaling", target)
        except Exception:
            pass

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
        self.profile_tab = tk.Frame(self.content_area, bg=BG)
        self.log_tab = tk.Frame(self.content_area, bg=BG)
        self.developer_tab = tk.Frame(self.content_area, bg=BG)

        self.pages = {
            "Play": self.play_tab,
            "Install": self.loader_tab,
            "Modrinth": self.modrinth_tab,
            "Server": self.server_tab,
            "Profile": self.profile_tab,
            "Logs": self.log_tab,
            "Developer": self.developer_tab,
        }

        for page in self.pages.values():
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_play_tab()
        self._build_loader_tab()
        self._build_modrinth_tab()
        self._build_server_tab()
        self._build_profile_tab()
        self._build_log_tab()
        self._build_developer_tab()

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
            ("Profile", "●"),
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
            x1, y1, x2, y2, r = 2, 2, 213, 42, 4
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
        if name == "Developer" and not self._dev_identity:
            return
        page = self.pages.get(name)
        if page is None:
            return
        if name == "Server" and not server.list_servers():
            self._new_server_dialog()
            return
        page.lift()
        if name == "Modrinth" and not self._modrinth_home_loaded:
            self.root.after(50, self._load_modrinth_home)
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
            x1, y1, x2, y2, r = 2, 2, 213, 42, 4
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
            icons = {"Play": "⌂", "Install": "+", "Modrinth": "◇", "Server": "▣", "Profile": "●", "Logs": "≡", "Developer": "⚙"}
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

    def _load_profile(self):
        try:
            if os.path.exists(self._profile_path):
                with open(self._profile_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("username"):
                    return data
        except Exception:
            pass
        return {"username": "Blemm"}

    def _save_profile(self):
        username = self._uname.get().strip()
        if not username or len(username) > 16 or not all(c.isalnum() or c == "_" for c in username):
            messagebox.showerror("Profile", "Username must be 1–16 characters using only letters, numbers, or underscores.")
            return
        os.makedirs(os.path.dirname(self._profile_path), exist_ok=True)
        with open(self._profile_path, "w", encoding="utf-8") as f:
            json.dump({"username": username}, f, indent=2)
        for name in instances.list_instances():
            try:
                cfg = instances.load_cfg(name)
                cfg["username"] = username
                instances.save_cfg(name, cfg)
            except Exception:
                pass
        self.status.config(text="Profile saved • " + username, foreground=SUCCESS)

    def _build_profile_tab(self):
        tab = self.profile_tab
        tab.columnconfigure(0, weight=1)
        card = ttk.Frame(tab, style="Card.TFrame", padding=24)
        card.grid(row=0, column=0, sticky="new", padx=8, pady=8)
        ttk.Label(card, text="Profile", style="Big.TLabel").pack(anchor="w")
        ttk.Label(card, text="Choose the username BlemmLauncher uses for local/offline Minecraft launches.",
                  style="MutedCard.TLabel", wraplength=700).pack(anchor="w", pady=(4, 20))
        ttk.Label(card, text="Minecraft username", style="MutedCard.TLabel").pack(anchor="w")
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 8))
        ttk.Entry(row, textvariable=self._uname, width=28).pack(side="left")
        ttk.Button(row, text="Save Profile", style="Primary.TButton",
                   command=self._save_profile).pack(side="left", padx=(10, 0))
        ttk.Label(card, text="16 characters max • letters, numbers, and underscores.",
                  style="MutedCard.TLabel").pack(anchor="w")

        dev_card = ttk.Frame(tab, style="Card.TFrame", padding=24)
        dev_card.grid(row=1, column=0, sticky="new", padx=8, pady=(4, 8))
        ttk.Label(dev_card, text="Developer Access", style="Big.TLabel").pack(anchor="w")
        ttk.Label(
            dev_card,
            text="Developer-only login. Credentials are checked by the Cloudflare Worker.",
            style="MutedCard.TLabel",
            wraplength=700
        ).pack(anchor="w", pady=(4, 14))

        self._dev_status_label = ttk.Label(
            dev_card,
            text="Not authenticated",
            style="MutedCard.TLabel"
        )
        self._dev_status_label.pack(anchor="w", pady=(0, 12))

        ttk.Label(dev_card, text="Developer username", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Entry(dev_card, textvariable=self._dev_username, width=32).pack(anchor="w", pady=(5, 10))

        ttk.Label(dev_card, text="Developer password", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Entry(
            dev_card,
            textvariable=self._dev_password,
            show="•",
            width=32
        ).pack(anchor="w", pady=(5, 12))

        self._dev_login_button = ttk.Button(
            dev_card,
            text="Developer Login",
            style="Primary.TButton",
            command=self._developer_login
        )
        self._dev_login_button.pack(anchor="w")

        ttk.Label(
            dev_card,
            text="The password is sent over HTTPS and is not saved in the launcher.",
            style="MutedCard.TLabel",
            wraplength=700
        ).pack(anchor="w", pady=(10, 0))

    def _developer_login(self):
        username = self._dev_username.get().strip()
        password = self._dev_password.get()
        if not username or not password:
            self._dev_status_label.config(
                text="Enter your developer username and password.",
                foreground=DANGER
            )
            return

        self._dev_login_button.config(state="disabled", text="Signing in…")
        self._dev_status_label.config(text="Authenticating…", foreground=MUTED)

        def worker():
            try:
                identity = dev_auth.login(username, password)
                self.q.put(("dev_login", identity, None, None))
            except Exception as exc:
                self.q.put(("dev_login_error", str(exc), None, None))

        threading.Thread(target=worker, daemon=True).start()


    def _build_developer_tab(self):
        tab = self.developer_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        card = ttk.Frame(tab, style="Card.TFrame", padding=24)
        card.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        ttk.Label(card, text="Developer", style="Big.TLabel").pack(anchor="w")
        self._developer_identity_label = ttk.Label(card, text="Developer access", style="MutedCard.TLabel")
        self._developer_identity_label.pack(anchor="w", pady=(4, 10))

        remote = ttk.Frame(card, style="Card.TFrame")
        remote.pack(fill="x", pady=(0, 12))
        ttk.Label(remote, text="Remote Developer Server", style="Accent.TLabel").pack(anchor="w")
        ttk.Label(
            remote,
            text="Control a Minecraft server from anywhere through the secure Cloudflare relay. The server PC makes outbound HTTPS connections; no server-management port is exposed.",
            style="MutedCard.TLabel", wraplength=900
        ).pack(anchor="w", pady=(3, 8))

        pair_row = ttk.Frame(remote, style="Card.TFrame")
        pair_row.pack(fill="x", pady=(0, 7))
        ttk.Button(pair_row, text="Generate Pairing Code", style="Primary.TButton",
                   command=self._remote_pair).pack(side="left")
        ttk.Button(pair_row, text="Connect This PC",
                   command=self._remote_launch_agent).pack(side="left", padx=(8, 0))
        ttk.Button(pair_row, text="Refresh Agents",
                   command=self._remote_refresh_agents).pack(side="left", padx=(8, 0))
        self._remote_pairing_label = ttk.Label(pair_row, text="No pairing code generated.",
                                               style="MutedCard.TLabel")
        self._remote_pairing_label.pack(side="left", padx=(12, 0))

        # Developer controls are intentionally locked to the reserved
        # developer server. There is no server-PC or Minecraft-server selector
        # in the Developer UI.
        self._remote_server.set("Survival")
        ttk.Label(
            remote,
            text="Target server: Survival",
            style="Accent.TLabel"
        ).pack(anchor="w", pady=(0, 7))

        control_row = ttk.Frame(remote, style="Card.TFrame")
        control_row.pack(fill="x", pady=(0, 7))
        for label, action in (("Refresh", "status"), ("Start", "start"), ("Stop", "stop"),
                              ("Restart", "restart"), ("Console", "logs")):
            ttk.Button(control_row, text=label,
                       command=lambda a=action: self._remote_action(a)).pack(side="left", padx=(0, 6))
        self._remote_status_label = ttk.Label(control_row, text="Survival server ready.",
                                              style="MutedCard.TLabel")
        self._remote_status_label.pack(side="left", padx=(8, 0))

        self._remote_console = scrolledtext.ScrolledText(
            remote, height=7, bg="#07170d", fg="#8CFFB1", insertbackground=ACCENT,
            relief="flat", borderwidth=0, wrap="none", font=("Consolas", 9)
        )
        self._remote_console.pack(fill="x", pady=(0, 7))

        command_row = ttk.Frame(remote, style="Card.TFrame")
        command_row.pack(fill="x")
        self._remote_command_entry = ttk.Entry(command_row)
        self._remote_command_entry.pack(side="left", fill="x", expand=True)
        self._remote_command_entry.bind("<Return>", lambda _e: self._remote_send_console())
        ttk.Button(command_row, text="Send Command", style="Primary.TButton",
                   command=self._remote_send_console).pack(side="left", padx=(8, 0))

        file_row = ttk.Frame(remote, style="Card.TFrame")
        file_row.pack(fill="x", pady=(7, 0))
        ttk.Label(file_row, text="Remote file", style="MutedCard.TLabel").pack(side="left")
        ttk.Entry(file_row, textvariable=self._remote_file).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(file_row, text="Load", command=self._remote_read_file).pack(side="left")
        ttk.Button(file_row, text="Save", command=self._remote_write_file).pack(side="left", padx=(6, 0))
        ttk.Button(file_row, text="Import", command=self._remote_import_file).pack(side="left", padx=(6, 0))

        self._developer_owner_frame = ttk.Frame(card, style="Card.TFrame")
        ttk.Label(self._developer_owner_frame, text="Owner controls", style="Accent.TLabel").pack(anchor="w")
        # Use classic Tk buttons here instead of themed ttk buttons. Some Windows
        # ttk themes can render the owner-control text incorrectly/blank.
        owner_actions = tk.Frame(self._developer_owner_frame, bg=CARD)
        owner_actions.pack(fill="x", pady=(8, 8))

        def owner_button(parent, text, command, primary=False):
            return tk.Button(
                parent,
                text=text,
                command=command,
                bg=ACCENT2 if primary else FIELD,
                fg="#04130a" if primary else FG,
                activebackground=GREEN_SOFT if primary else GREEN_DARK,
                activeforeground="#04130a" if primary else FG,
                relief="flat",
                bd=0,
                highlightthickness=0,
                padx=14,
                pady=8,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )

        owner_button(owner_actions, "Server Management", self._open_owner_server_manager, True).pack(side="left")
        owner_button(owner_actions, "Refresh Developers", self._developer_refresh).pack(side="left", padx=(8, 0))
        owner_button(
            owner_actions, "+ Create Developer", self._developer_create, primary=True
        ).pack(side="left", padx=(8, 0))

        tree_frame = tk.Frame(self._developer_owner_frame, bg=CARD)
        tree_frame.pack(fill="x", pady=(0, 8))

        self._developer_tree = ttk.Treeview(
            tree_frame, columns=("username", "role", "created"),
            show="headings", height=7
        )
        for col, title, width in (
            ("username", "Username", 220),
            ("role", "Role", 120),
            ("created", "Created", 220),
        ):
            self._developer_tree.heading(col, text=title)
            self._developer_tree.column(col, width=width)
        self._developer_tree.pack(fill="x")

        actions = tk.Frame(self._developer_owner_frame, bg=CARD)
        actions.pack(fill="x")

        owner_button(
            actions, "Reset Selected Password", self._developer_reset
        ).pack(side="left")
        owner_button(
            actions, "Delete Selected", self._developer_delete
        ).pack(side="left", padx=(8, 0))

        self._developer_nonowner_label = ttk.Label(
            card,
            text="You are authenticated as a developer. Owner-only account management is hidden.",
            style="MutedCard.TLabel", wraplength=700
        )

    def _show_developer_controls(self):
        if not self._dev_identity:
            return
        username = str(self._dev_identity.get("username", "Developer"))
        role = str(self._dev_identity.get("role", "developer"))
        self._developer_identity_label.config(
            text="Signed in as " + username + " • " + role.upper(),
            foreground=SUCCESS
        )
        if role == "owner":
            self._auto_connect_owner_pc()
        if role == "owner":
            self._developer_nonowner_label.pack_forget()
            self._developer_owner_frame.pack(fill="both", expand=True)
            self._developer_refresh()
        else:
            self._developer_owner_frame.pack_forget()
            self._developer_nonowner_label.pack(anchor="w", pady=(8, 0))

    def _remote_token(self):
        return (self._dev_identity or {}).get("token", "")

    def _auto_connect_owner_pc(self):
        if self._owner_agent_started:
            return
        token = self._remote_token()
        if not token:
            return
        self.status.config(text="Connecting this owner PC…", foreground=MUTED)

        def worker():
            try:
                name = socket.gethostname() if "socket" in globals() else ""
                result = dev_auth.register_owner_agent(token, name)
                state = {
                    "agent_id": result["agent_id"],
                    "agent_token": result["agent_token"],
                    "name": result.get("name", "Owner PC"),
                }
                # Store only the agent credential, never the developer password.
                if getattr(sys, "frozen", False):
                    root = os.path.dirname(os.path.abspath(sys.executable))
                    state_dir = os.path.join(root, "Dev")
                    agent_command = [sys.executable, "--agent"]
                else:
                    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                    state_dir = os.path.join(root, "Dev")
                    agent_command = [sys.executable, "-m", "Dev.agent"]
                state_path = os.path.join(state_dir, ".agent.json")
                os.makedirs(os.path.dirname(state_path), exist_ok=True)
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)

                flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
                env = os.environ.copy()
                env["BLEMM_AGENT_STATE_DIR"] = state_dir
                subprocess.Popen(
                    agent_command,
                    cwd=root,
                    creationflags=flags,
                    env=env,
                )
                self.q.put(("owner_agent_ready", result, None, None))
            except Exception as exc:
                self.q.put(("owner_agent_error", str(exc), None, None))

        threading.Thread(target=worker, daemon=True).start()

    def _remote_pair(self):
        token = self._remote_token()
        if not token:
            return
        def worker():
            try:
                result = dev_auth.create_agent_pairing(token)
                self.q.put(("remote_pair", result, None, None))
            except Exception as exc:
                self.q.put(("remote_error", str(exc), None, None))
        threading.Thread(target=worker, daemon=True).start()

    def _remote_launch_agent(self):
        try:
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
            subprocess.Popen([sys.executable, "-m", "Dev.agent"], cwd=root, creationflags=flags)
            self.status.config(text="Started the Developer Server Agent on this PC.", foreground=SUCCESS)
        except Exception as exc:
            messagebox.showerror("Developer Server Agent", str(exc))

    def _remote_refresh_agents(self):
        token = self._remote_token()
        if not token:
            return
        def worker():
            try:
                rows = dev_auth.list_agents(token)
                self.q.put(("remote_agents", rows, None, None))
            except Exception as exc:
                self.q.put(("remote_error", str(exc), None, None))
        threading.Thread(target=worker, daemon=True).start()

    def _remote_selected_server(self):
        return "Survival"

    def _remote_action(self, action, payload=None):
        # The owner can manage servers on this PC directly. This keeps the
        # Developer tab in sync with Owner Server Management instead of waiting
        # for the relay/agent round trip.
        if self._dev_identity and str(self._dev_identity.get("role", "")).lower() == "owner":
            payload = dict(payload or {})
            name = str(payload.get("server", "")).strip() or self._remote_selected_server()
            if action not in ("status", "logs") and not name:
                self._remote_status_label.config(text="Choose a Minecraft server first.", foreground=DANGER)
                return
            def local_worker():
                try:
                    if action == "status":
                        rows = []
                        for n in server.list_servers():
                            try:
                                cfg = server.load(n)
                                rows.append({"name": n, "running": bool(server.running(n)),
                                              "type": cfg.get("type"), "version": cfg.get("version"),
                                              "ram": cfg.get("ram")})
                            except Exception:
                                rows.append({"name": n, "running": bool(server.running(n))})
                        result = {"servers": rows}
                    elif action == "logs":
                        result = {"server": name, "lines": server.get_logs(name)}
                    elif action == "console":
                        command = str(payload.get("command", "")).strip()
                        if not command:
                            raise RuntimeError("Console command is empty.")
                        server.command(name, command)
                        result = {"server": name, "sent": command}
                    elif action == "start":
                        server.start(name)
                        result = {"server": name, "running": True}
                    elif action == "stop":
                        server.stop(name)
                        result = {"server": name, "running": False}
                    elif action == "restart":
                        server.stop(name)
                        time.sleep(1.5)
                        server.start(name)
                        result = {"server": name, "running": True}
                    else:
                        raise RuntimeError("Unsupported local developer action: " + action)
                    self.q.put(("remote_result", (action, "completed", result), None, None))
                except Exception as exc:
                    self.q.put(("remote_error", str(exc), None, None))
            threading.Thread(target=local_worker, daemon=True).start()
            self._remote_status_label.config(text="Running " + action + "…", foreground=MUTED)
            return

        token = self._remote_token()
        agent_id = self._remote_agent_id
        if not token or not agent_id:
            self._remote_status_label.config(text="No connected server is available.", foreground=DANGER)
            return
        payload = dict(payload or {})
        payload["server"] = "Survival"

        def worker():
            try:
                queued = dev_auth.send_agent_command(token, agent_id, action, payload)
                command_id = queued.get("command_id")
                if not command_id:
                    raise RuntimeError("Worker did not return a command id.")
                for _ in range(45):
                    time.sleep(1)
                    rows = dev_auth.list_agent_commands(token, agent_id)
                    row = next((x for x in rows if int(x.get("id", -1)) == int(command_id)), None)
                    if row and row.get("status") in ("completed", "error"):
                        try:
                            result = json.loads(row.get("result") or "{}")
                        except Exception:
                            result = {"raw": row.get("result", "")}
                        self.q.put(("remote_result", (action, row.get("status"), result), None, None))
                        return
                raise RuntimeError("Remote server did not answer within 45 seconds.")
            except Exception as exc:
                self.q.put(("remote_error", str(exc), None, None))

        threading.Thread(target=worker, daemon=True).start()
        self._remote_status_label.config(text="Sending " + action + "…", foreground=MUTED)

    def _schedule_remote_console_refresh(self):
        if not self.root.winfo_exists():
            return
        if self._remote_selected_server():
            self.root.after(2000, self._poll_remote_console)

    def _poll_remote_console(self):
        if not self.root.winfo_exists():
            return
        name = "Survival"
        if name and (
            (self._dev_identity and str(self._dev_identity.get("role", "")).lower() == "owner" and server.running(name))
            or self._remote_agent_id
        ):
            self._remote_action("logs")

    def _remote_send_console(self):
        command = self._remote_command_entry.get().strip()
        if not command:
            return
        self._remote_command_entry.delete(0, "end")
        self._remote_action("console", {"server": "Survival", "command": command})

    def _remote_read_file(self):
        rel = self._remote_file.get().strip()
        if not rel:
            return
        self._remote_action("read_file", {"server": "survival", "path": rel})

    def _remote_import_file(self):
        source = filedialog.askopenfilename(
            parent=self.root,
            title="Import file into Survival"
        )
        if not source:
            return
        filename = os.path.basename(source)
        destination = self._remote_file.get().strip().replace("\\", "/").strip("/")
        if not destination:
            destination = filename
            self._remote_file.set(destination)
        else:
            # If the current field points at a directory, place the imported
            # file inside it; otherwise the selected path is replaced.
            if destination.endswith("/"):
                destination += filename
        try:
            size = os.path.getsize(source)
            if size > 50 * 1024 * 1024:
                raise RuntimeError("Imported files are limited to 50 MB.")
            with open(source, "rb") as f:
                import base64
                encoded = base64.b64encode(f.read()).decode("ascii")
            self._remote_action(
                "import_file",
                {"server": "Survival", "path": destination, "data": encoded}
            )
        except Exception as e:
            messagebox.showerror("Import File", str(e), parent=self.root)

    def _remote_write_file(self):
        rel = self._remote_file.get().strip()
        if not rel:
            return
        content = self._remote_console.get("1.0", "end-1c")
        self._remote_action("write_file", {
            "server": "survival",
            "path": rel,
            "content": content,
        })

    def _add_developer_nav(self):
        if getattr(self, "_developer_nav_added", False):
            return
        self._nav_button("Developer", "⚙")
        self._developer_nav_added = True
        self._refresh_nav_buttons()

    def _open_owner_server_manager(self):
        if not self._dev_identity or self._dev_identity.get("role") != "owner":
            return
        OwnerServerManager(self)

    def _developer_refresh(self):
        if not self._dev_identity or self._dev_identity.get("role") != "owner":
            return
        token = self._dev_identity.get("token", "")
        def worker():
            try:
                rows = dev_auth.list_developers(token)
                self.q.put(("developer_list", rows, None, None))
            except Exception as exc:
                self.q.put(("developer_error", str(exc), None, None))
        threading.Thread(target=worker, daemon=True).start()

    def _developer_create(self):
        if not self._dev_identity or self._dev_identity.get("role") != "owner":
            return
        username = simpledialog.askstring("Create Developer", "Developer username:", parent=self.root)
        if not username:
            return
        password = simpledialog.askstring(
            "Create Developer", "Temporary password (8+ characters):",
            parent=self.root, show="•"
        )
        if not password:
            return
        token = self._dev_identity.get("token", "")
        def worker():
            try:
                result = dev_auth.create_developer(token, username.strip(), password)
                self.q.put(("developer_created", result, None, None))
            except Exception as exc:
                self.q.put(("developer_error", str(exc), None, None))
        threading.Thread(target=worker, daemon=True).start()

    def _selected_developer(self):
        if not hasattr(self, "_developer_tree"):
            return None
        selection = self._developer_tree.selection()
        if not selection:
            return None
        values = self._developer_tree.item(selection[0], "values")
        return values[0] if values else None

    def _developer_reset(self):
        username = self._selected_developer()
        if not username or username.lower() == "blemm":
            messagebox.showinfo("Developer", "Select a non-owner developer account.")
            return
        password = simpledialog.askstring(
            "Reset Password", "New password for " + username + ":",
            parent=self.root, show="•"
        )
        if not password:
            return
        token = self._dev_identity.get("token", "")
        def worker():
            try:
                dev_auth.reset_developer_password(token, username, password)
                self.q.put(("developer_created", {"username": username}, None, None))
            except Exception as exc:
                self.q.put(("developer_error", str(exc), None, None))
        threading.Thread(target=worker, daemon=True).start()

    def _developer_delete(self):
        username = self._selected_developer()
        if not username or username.lower() == "blemm":
            messagebox.showinfo("Developer", "Select a non-owner developer account.")
            return
        if not messagebox.askyesno("Delete Developer", "Delete '" + username + "'?", parent=self.root):
            return
        token = self._dev_identity.get("token", "")
        def worker():
            try:
                dev_auth.delete_developer(token, username)
                self.q.put(("developer_deleted", username, None, None))
            except Exception as exc:
                self.q.put(("developer_error", str(exc), None, None))
        threading.Thread(target=worker, daemon=True).start()

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
        for col in range(3):
            self.instance_grid.columnconfigure(col, weight=1, uniform="instance_cards")

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
            width=225, height=300
        )
        card.grid(
            row=index // 3, column=index % 3,
            padx=8, pady=8, sticky="nsew"
        )
        card.grid_propagate(False)

        art = tk.Canvas(card, width=223, height=165, bg="#101814", highlightthickness=0, bd=0)
        art.pack(fill="x")

        # Loader-specific artwork.  Each instance gets a real visual identity
        # instead of the old generic landscape, while remaining offline-safe.
        loader_key = str(cfg.get("loader") or "vanilla").lower()
        loader_art = {
            "vanilla": ("#172019", "#6ee7a1", "#0a130e", "MINECRAFT", "◆"),
            "fabric": ("#182b35", "#62d8ff", "#08151c", "FABRIC", "✦"),
            "forge": ("#33251d", "#f0a35b", "#160d09", "FORGE", "⚒"),
            "neoforge": ("#2a202e", "#d7a5ff", "#120b18", "NEOFORGE", "✧"),
        }
        c1, c2, c3, art_name, art_symbol = loader_art.get(
            loader_key, loader_art["vanilla"]
        )

        art.create_rectangle(0, 0, 223, 165, fill=c1, outline="")
        # Layered diagonal bands give the card a wallpaper-like look.
        art.create_polygon(0, 118, 78, 34, 136, 165, 0, 165, fill=c3, outline="")
        art.create_polygon(90, 0, 223, 0, 223, 104, 160, 74, fill=c3, outline="")
        art.create_oval(150, 18, 206, 74, fill=c2, outline="")
        art.create_oval(166, 34, 190, 58, fill=c1, outline="")
        art.create_text(
            16, 15, text=art_name, anchor="nw",
            fill="#e9fff1", font=("Segoe UI", 9, "bold")
        )
        art.create_text(
            111, 83, text=art_symbol,
            fill=c2, font=("Segoe UI Symbol", 42, "bold")
        )
        art.create_text(
            16, 138, text=loader.upper(), anchor="sw",
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
            values=["Loading versions…"], state="readonly"
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
        if self._all_versions:
            self.loader_version_combo.configure(values=["release"] + self._all_versions)
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

        ttk.Label(top, text="Modrinth Store", style="Big.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            top,
            text="Discover mods, modpacks, shaders, resource packs and more — without leaving BlemmLauncher.",
            style="MutedCard.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(2, 9))

        searchbar = ttk.Frame(top, style="Card.TFrame")
        searchbar.grid(row=2, column=0, sticky="ew")
        searchbar.columnconfigure(0, weight=1)
        ttk.Entry(searchbar, textvariable=self.modrinth_query).grid(row=0, column=0, sticky="ew")
        ttk.Combobox(
            searchbar, textvariable=self.modrinth_type,
            values=["mod", "modpack", "shader", "resourcepack", "datapack", "world"],
            state="readonly", width=18
        ).grid(row=0, column=1, padx=7)
        ttk.Button(searchbar, text="Search", style="Primary.TButton",
                   command=self.modrinth_search).grid(row=0, column=2)
        ttk.Button(searchbar, text="Discover",
                   command=self._show_modrinth_home).grid(row=0, column=3, padx=(7, 0))

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

        canvas = tk.Canvas(body, bg=CARD, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        self.modrinth_cards = ttk.Frame(canvas, style="Card.TFrame")
        self._modrinth_cards_root = self.modrinth_cards
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
            text="Loading Modrinth Discover…",
            style="MutedCard.TLabel"
        )
        self.modrinth_message.pack(anchor="w", padx=18, pady=18)

        self.root.after(250, self._load_modrinth_home)

    def _modrinth_clear_cards(self):
        for child in self._modrinth_cards_root.winfo_children():
            child.destroy()

    def _show_modrinth_home(self):
        self._modrinth_home_loaded = False
        self._load_modrinth_home()

    def _load_modrinth_home(self):
        if self._modrinth_searching:
            return
        target = self.modrinth_target.get().strip()
        mc_version = None
        loader = None
        if target:
            try:
                cfg = instances.load_cfg(target)
                mc_version = cfg.get("version")
                loader = cfg.get("loader")
            except Exception:
                pass
        if not mc_version:
            mc_version = self._all_versions[0] if self._all_versions else None
        if not mc_version:
            self.modrinth_message.config(text="Waiting for Minecraft versions…")
            return

        self._modrinth_searching = True
        self._modrinth_clear_cards()
        ttk.Label(
            self._modrinth_cards_root,
            text="Discover • Minecraft " + str(mc_version),
            style="Accent.TLabel"
        ).pack(anchor="w", padx=18, pady=(16, 5))
        ttk.Label(
            self._modrinth_cards_root,
            text="Popular projects from Modrinth. Select an instance above to filter by its version.",
            style="MutedCard.TLabel"
        ).pack(anchor="w", padx=18, pady=(0, 12))

        categories = [
            ("Popular Mods", "mod"),
            ("Popular Modpacks", "modpack"),
            ("Popular Resource Packs", "resourcepack"),
            ("Popular Shaders", "shader"),
        ]

        def worker():
            try:
                sections = []
                for title, ptype in categories:
                    hits = instances.modrinth_search(
                        "", mc_version,
                        loader if ptype == "mod" else None,
                        ptype
                    )
                    sections.append((title, ptype, hits[:6]))
                self.q.put(("modrinth_home_results", (mc_version, loader, sections), None, None))
            except Exception as e:
                self.q.put(("modrinth_error", str(e), None, None))

        threading.Thread(target=worker, daemon=True).start()

    def _modrinth_image(self, parent, url, size=72):
        if not url:
            return
        key = (str(url), size)
        if key in self._modrinth_image_refs:
            photo = self._modrinth_image_refs[key]
            parent.configure(image=photo, text="")
            parent.image = photo
            return

        def worker():
            try:
                req = urllib.request.Request(
                    str(url),
                    headers={"User-Agent": "BlemmLauncher/1.0", "Accept": "image/*"}
                )
                with urllib.request.urlopen(req, timeout=12) as r:
                    raw = r.read()
                image = Image.open(io.BytesIO(raw)).convert("RGBA")
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                # ImageTk.PhotoImage must be created on Tk's main thread.
                self.q.put(("modrinth_image", (parent, key, image), None, None))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _store_card(self, hit, target_name, mc_version, loader, ptype, parent=None):
        host = parent or self._modrinth_cards_root
        card = tk.Frame(
            host, bg=CARD, highlightthickness=1,
            highlightbackground="#183222", bd=0
        )
        card.pack(fill="x", padx=10, pady=5, ipady=3)
        card.columnconfigure(1, weight=1)

        title = hit.get("title", "Unknown")
        author = hit.get("author", "Unknown")
        downloads = hit.get("downs", 0)
        desc = hit.get("desc", "") or "No description available."

        image_box = tk.Frame(card, bg="#0c1711", width=78, height=78)
        image_box.grid(row=0, column=0, rowspan=3, padx=(10, 12), pady=7)
        image_box.grid_propagate(False)
        image_label = tk.Label(
            image_box, text=ptype.upper()[:3], bg="#102218", fg=ACCENT,
            font=("Segoe UI", 9, "bold")
        )
        image_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._modrinth_image(image_label, hit.get("icon"), 68)

        tk.Label(
            card, text=title, bg=CARD, fg=FG,
            font=("Segoe UI", 12, "bold"), anchor="w"
        ).grid(row=0, column=1, sticky="ew", pady=(8, 1))
        ttk.Label(
            card,
            text="by " + author + "  •  " + f"{downloads:,}" + " downloads  •  " + ptype,
            style="MutedCard.TLabel"
        ).grid(row=1, column=1, sticky="w", pady=(1, 3))
        ttk.Label(
            card, text=desc, style="MutedCard.TLabel",
            wraplength=620, justify="left"
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
        self._modrinth_clear_cards()
        ttk.Label(
            self._modrinth_cards_root,
            text="Searching Modrinth…",
            style="MutedCard.TLabel"
        ).pack(anchor="w", padx=18, pady=18)

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
        actions = tk.Frame(header, bg=BG)
        actions.grid(row=0, column=2, rowspan=2, sticky="e")
        self.new_server_btn = ttk.Button(actions, text="+ New Server", style="Primary.TButton",
                                         command=self._new_server_dialog)
        self.new_server_btn.pack(side="left", padx=(0, 8))
        self.delete_server_btn = ttk.Button(actions, text="Delete Server",
                                            command=self._delete_server)
        self.delete_server_btn.pack(side="left")

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
        self.delete_server_btn.config(state="disabled")
        ttk.Button(left, text="Delete Server", command=self._delete_server).pack(fill="x", pady=(8, 0))
        self.server_locked_label = tk.Label(left, text="🔒 Create a server first",
                                            bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.server_count_label = tk.Label(left, text="0 / 2 servers",
                                           bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.server_locked_label.pack(anchor="w", padx=4, pady=(8, 2))
        self.server_count_label.pack(anchor="w", padx=4, pady=(0, 2))

        right = tk.Frame(tab, bg=BG)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.server_selector = tk.Frame(right, bg=BG)
        self.server_selector.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Label(self.server_selector, text="Choose a server", bg=BG, fg=FG,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=6, pady=(8, 2))
        tk.Label(self.server_selector,
                 text="Choose a server before opening its console, settings, or files.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=6, pady=(0, 14))
        self.server_selector_cards = tk.Frame(self.server_selector, bg=BG)
        self.server_selector_cards.pack(fill="both", expand=True, padx=2)

        self.server_workspace = tk.Frame(right, bg=BG)
        self.server_workspace.place_forget()
        self.server_workspace.columnconfigure(0, weight=1)
        self.server_workspace.rowconfigure(1, weight=1)

        info = ttk.Frame(self.server_workspace, style="Card.TFrame", padding=12)
        info.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        info.columnconfigure(1, weight=1)
        self.server_title = tk.Label(info, text="No server selected", bg=CARD, fg=FG,
                                     font=("Segoe UI", 15, "bold"))
        self.server_title.grid(row=0, column=0, sticky="w")
        self.server_meta = tk.Label(info, text="Create a server to get started.",
                                    bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.server_meta.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.server_network = tk.Frame(info, bg=CARD)
        self.server_network.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.server_network.columnconfigure(1, weight=1)
        self.server_local_label = tk.Label(
            self.server_network, text="Local: —", bg=CARD, fg=ACCENT,
            font=("Consolas", 9, "bold"), anchor="w"
        )
        self.server_local_label.grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.server_lan_label = tk.Label(
            self.server_network, text="LAN: —", bg=CARD, fg=FG,
            font=("Consolas", 9), anchor="w"
        )
        self.server_lan_label.grid(row=0, column=1, sticky="w")
        ttk.Button(self.server_network, text="Copy LAN IP", command=self._copy_server_lan).grid(
            row=0, column=2, sticky="e", padx=(8, 0)
        )
        ttk.Button(self.server_network, text="Copy Address", command=self._copy_server_address).grid(
            row=0, column=3, sticky="e", padx=(8, 0)
        )
        self.server_network_hint = tk.Label(
            self.server_network,
            text="Use Local on this PC • use LAN from another device on the same Wi‑Fi/network",
            bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w"
        )
        self.server_network_hint.grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))
        domain_box = tk.Frame(info, bg=CARD)
        domain_box.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        domain_box.columnconfigure(1, weight=1)
        tk.Label(domain_box, text="DOMAIN", bg=CARD, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.server_domain_combo = ttk.Combobox(
            domain_box, textvariable=self._server_domain_suffix,
            values=self._server_domains, state="readonly", width=24
        )
        self.server_domain_combo.grid(row=0, column=1, sticky="w")
        self.server_domain_combo.bind("<<ComboboxSelected>>", self._server_domain_changed)
        self.server_domain_label = tk.Label(domain_box, text="—", bg=CARD, fg=FG,
                                            font=("Consolas", 9, "bold"), anchor="w")
        self.server_domain_label.grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Button(domain_box, text="Copy Domain", command=self._copy_server_domain).grid(row=0, column=3, sticky="e", padx=(8, 0))
        ttk.Button(domain_box, text="Domain Help", command=self._open_free_domain).grid(row=0, column=4, sticky="e", padx=(8, 0))
        self.server_domain_hint = tk.Label(domain_box,
            text="The free-domains project is a directory; registration is done through the provider you choose.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.server_domain_hint.grid(row=1, column=0, columnspan=5, sticky="w", pady=(5, 0))
        controls = tk.Frame(info, bg=CARD)
        controls.grid(row=0, column=2, rowspan=2, sticky="e")
        self.server_start_btn = ttk.Button(controls, text="▶ Start", style="Primary.TButton",
                                           command=self._start_server, state="disabled")
        self.server_start_btn.pack(side="left", padx=3)
        self.server_stop_btn = ttk.Button(controls, text="■ Stop",
                                          command=self._stop_server, state="disabled")
        self.server_stop_btn.pack(side="left", padx=3)
        ttk.Button(controls, text="Refresh Files", command=self._refresh_server_files).pack(side="left", padx=3)

        notebook = ttk.Notebook(self.server_workspace)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.server_console_tab = ttk.Frame(notebook, style="Card.TFrame")
        self.server_files_tab = ttk.Frame(notebook, style="Card.TFrame")
        notebook.add(self.server_console_tab, text="  Console  ")
        notebook.add(self.server_files_tab, text="  File Manager  ")

        console_wrap = tk.Frame(self.server_console_tab, bg=CARD)
        console_wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.server_console = scrolledtext.ScrolledText(
            console_wrap, height=9, bg="#041008", fg="#8CFFB1",
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
        self.server_path_label = tk.Label(filebar, text="  /", bg=CARD, fg="#55F58B",
                                          font=("Consolas", 10, "bold"), anchor="w")
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
        tree_style = ttk.Style()
        tree_style.configure(
            "Server.Treeview",
            background="#07170d",
            fieldbackground="#07170d",
            foreground="#8CFFB1",
            borderwidth=0,
            rowheight=29,
            font=("Consolas", 9)
        )
        tree_style.map(
            "Server.Treeview",
            background=[("selected", "#0A3A20")],
            foreground=[("selected", "#55F58B")]
        )
        tree_style.configure(
            "Server.Treeview.Heading",
            background="#0B2415",
            foreground="#55F58B",
            relief="flat",
            font=("Segoe UI", 9, "bold")
        )
        self.server_tree = ttk.Treeview(
            tree_frame,
            columns=("type", "size"),
            show="tree headings",
            height=17,
            style="Server.Treeview"
        )
        self.server_tree.heading("#0", text="  FILES")
        self.server_tree.heading("type", text="Type")
        self.server_tree.heading("size", text="Size")
        self.server_tree.column("#0", width=235, minwidth=180)
        self.server_tree.column("type", width=75, anchor="center")
        self.server_tree.column("size", width=90, anchor="e")
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
            editor_frame, bg="#07170d", fg="#8CFFB1", insertbackground=ACCENT,
            relief="flat", borderwidth=0, undo=True, wrap="none",
            font=("Consolas", 9)
        )
        self.server_editor.grid(row=1, column=0, sticky="nsew")
        self.server_editor.bind("<<Modified>>", self._server_editor_changed)
        ttk.Button(editor_frame, text="Save File", style="Primary.TButton",
                   command=self._save_server_file).grid(row=2, column=0, sticky="e", pady=(6, 0))

        self._refresh_servers()

    def _show_server_selector(self):
        self.server_workspace.place_forget()
        self.server_selector.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _show_server_workspace(self):
        self.server_selector.place_forget()
        self.server_workspace.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _rebuild_server_selector(self):
        if not hasattr(self, "server_selector_cards"):
            return
        for child in self.server_selector_cards.winfo_children():
            child.destroy()
        names = server.list_servers()
        if not names:
            tk.Label(self.server_selector_cards,
                     text="No servers yet.\nUse + New Server to create one.",
                     bg=BG, fg=MUTED, font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", padx=12, pady=20)
            return
        for name in names:
            try:
                cfg = server.load(name)
                state = "RUNNING" if server.running(name) else "STOPPED"
                meta = f"{cfg.get('type','Server')}  •  Minecraft {cfg.get('version','?')}  •  {cfg.get('ram','4G')} RAM  •  {state}"
            except Exception:
                meta = "Server information unavailable"
            card = tk.Frame(self.server_selector_cards, bg=CARD,
                            highlightthickness=1, highlightbackground=GREEN_DARK,
                            padx=14, pady=12)
            card.pack(fill="x", pady=6)
            card.columnconfigure(0, weight=1)
            tk.Label(card, text=name, bg=CARD, fg=FG,
                     font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
            tk.Label(card, text=meta, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(3, 0))
            ttk.Button(card, text="Choose server", style="Primary.TButton",
                       command=lambda n=name: self._load_server_panel(n)).grid(
                           row=0, column=1, rowspan=2, padx=(18, 0))

    def _update_server_access(self):
        unlocked = bool(server.list_servers())
        self._server_access = unlocked
        if hasattr(self, "server_locked_label"):
            self.server_locked_label.config(text="✓ Panel unlocked" if unlocked else "🔒 Create a server first")

    def _refresh_servers(self):
        if not hasattr(self, "server_list"):
            return
        names = server.list_servers()
        if hasattr(self, "server_count_label"):
            self.server_count_label.config(text=str(len(names)) + " / " + str(server.MAX_SERVERS) + " servers")
        if hasattr(self, "new_server_btn"):
            self.new_server_btn.config(state="disabled" if len(names) >= server.MAX_SERVERS else "normal")
        self.server_list.delete(0, "end")
        self._rebuild_server_selector()
        for name in names:
            self.server_list.insert("end", name)
        if self._server_name in names:
            i = names.index(self._server_name)
            self.server_list.selection_set(i)
            self.server_list.see(i)
            self._show_server_selector()
        elif names:
            self.server_list.selection_set(0)
            self._server_name = None
            self._show_server_selector()
        else:
            self._server_name = None
            self._show_server_selector()
            self.server_title.config(text="No server selected")
            self.server_meta.config(text="Create a server to get started.")
            self._clear_server_files()

    def _server_selected(self, _event=None):
        sel = self.server_list.curselection()
        if sel:
            self._server_name = self.server_list.get(sel[0])
            if hasattr(self, "delete_server_btn"):
                self.delete_server_btn.config(state="normal")
            self._show_server_selector()

    def _load_server_panel(self, name):
        self._server_name = name
        self._show_server_workspace()
        try:
            cfg = server.load(name)
            state = "RUNNING" if server.running(name) else "STOPPED"
            self.server_title.config(text=name)
            self.server_meta.config(text=f"{cfg.get('type','Server')}  •  Minecraft {cfg.get('version','?')}  •  {cfg.get('ram','4G')} RAM  •  {state}")
            self._refresh_server_network()
            self.server_start_btn.config(state="disabled" if server.running(name) else "normal")
            self.server_stop_btn.config(state="normal" if server.running(name) else "disabled")
            self._refresh_server_files()
        except Exception as e:
            self.log_message("Server panel error: " + str(e))

    def _refresh_server_network(self):
        if not self._server_name:
            return
        try:
            info = server.network_info(self._server_name)
            self.server_local_label.config(text="Local: " + info["local_address"])
            self.server_lan_label.config(text="LAN: " + info["lan_address"])
            self.server_network_hint.config(
                text="Port " + str(info["port"]) + " • Local works on this PC • LAN works from another device on the same network"
            )
        except Exception as e:
            self.server_local_label.config(text="Local: unavailable")
            self.server_lan_label.config(text="LAN: unavailable")
            self.server_network_hint.config(text=str(e))

        self._refresh_server_domain()
    def _copy_server_lan(self):
        if not self._server_name:
            return
        try:
            value = server.network_info(self._server_name)["lan_address"]
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.status.config(text="Copied LAN address: " + value, foreground=SUCCESS)
        except Exception as e:
            messagebox.showerror("Copy LAN IP", str(e))

    def _copy_server_address(self):
        if not self._server_name:
            return
        try:
            value = server.network_info(self._server_name)["lan_address"]
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.status.config(text="Copied server address: " + value, foreground=SUCCESS)
        except Exception as e:
            messagebox.showerror("Copy Address", str(e))

    def _server_domain_changed(self, _event=None):
        if not self._server_name:
            return
        try:
            cfg = server.load(self._server_name)
            cfg["domain_suffix"] = self._server_domain_suffix.get().strip().lower()
            server.save(self._server_name, cfg)
            self._refresh_server_domain()
            self.status.config(
                text="Domain set to " + cfg["domain_suffix"] + " for " + self._server_name,
                foreground=SUCCESS
            )
        except Exception as e:
            messagebox.showerror("Domain", str(e))

    def _refresh_server_domain(self):
        if not self._server_name:
            return
        try:
            cfg = server.load(self._server_name)
            suffix = str(cfg.get("domain_suffix") or self._server_domains[0]).strip().lower()
            if suffix not in self._server_domains:
                suffix = self._server_domains[0]
            self._server_domain_suffix.set(suffix)
            self.server_domain_combo.set(suffix)
            info = server.domain_info(self._server_name, suffix)
            self.server_domain_label.config(text=info["domain"])
            self.server_domain_hint.config(
                text=info["status"]
            )
        except Exception as e:
            self.server_domain_label.config(text="Unavailable")
            self.server_domain_hint.config(text=str(e))

    def _copy_server_domain(self):
        if not self._server_name:
            return
        try:
            value = server.domain_info(self._server_name, self._server_domain_suffix.get())["domain"]
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.status.config(text="Copied domain: " + value, foreground=SUCCESS)
        except Exception as e:
            messagebox.showerror("Copy Domain", str(e))

    def _open_free_domain(self):
        webbrowser.open("https://github.com/harys722/free-domains")
        self.status.config(text="Opened the Free Domains directory. Choose a provider and register the displayed hostname.", foreground=SUCCESS)

    def _new_server_dialog(self):
        d = tk.Toplevel(self.root)
        d.title("Create Server")
        d.geometry("600x480")
        d.minsize(560, 430)
        d.configure(bg=BG)
        d.transient(self.root)
        d.grab_set()

        name = tk.StringVar(value="My Server")
        kind = tk.StringVar(value="Paper")
        version = tk.StringVar()
        ram = tk.StringVar(value="4G")
        java = tk.StringVar(value="")
        step = tk.IntVar(value=0)

        shell = tk.Frame(d, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        progress = tk.Label(shell, text="1  •  Name     2  •  Server     3  •  Java",
                            bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        progress.pack(anchor="w", pady=(0, 12))

        pages = [ttk.Frame(shell, style="Card.TFrame", padding=20) for _ in range(3)]

        ttk.Label(pages[0], text="Name your server", style="Big.TLabel").pack(anchor="w")
        ttk.Label(pages[0], text="Choose a name and memory allocation.",
                  style="MutedCard.TLabel").pack(anchor="w", pady=(4, 18))
        ttk.Label(pages[0], text="Server name", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Entry(pages[0], textvariable=name).pack(fill="x", pady=(6, 14), ipady=5)
        ttk.Label(pages[0], text="RAM", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Combobox(pages[0], textvariable=ram,
                     values=["2G","4G","6G","8G","12G","16G"],
                     state="readonly").pack(fill="x", pady=(6, 0), ipady=4)

        ttk.Label(pages[1], text="Choose server software", style="Big.TLabel").pack(anchor="w")
        ttk.Label(pages[1], text="Select the Minecraft version and server type.",
                  style="MutedCard.TLabel").pack(anchor="w", pady=(4, 18))
        ttk.Label(pages[1], text="Server type", style="MutedCard.TLabel").pack(anchor="w")
        type_box = ttk.Combobox(pages[1], textvariable=kind,
                                values=list(server.SERVER_TYPES), state="readonly")
        type_box.pack(fill="x", pady=(6, 14), ipady=4)
        ttk.Label(pages[1], text="Minecraft version", style="MutedCard.TLabel").pack(anchor="w")
        version_box = ttk.Combobox(pages[1], textvariable=version, state="readonly")
        version_box.pack(fill="x", pady=(6, 6), ipady=4)
        version_info = ttk.Label(pages[1], text="Loading versions…",
                                 style="MutedCard.TLabel", wraplength=500)
        version_info.pack(anchor="w", pady=(4, 0))

        ttk.Label(pages[2], text="Java (optional)", style="Big.TLabel").pack(anchor="w")
        ttk.Label(pages[2],
                  text="Leave this empty to automatically install and use the required Java runtime.",
                  style="MutedCard.TLabel", wraplength=500).pack(anchor="w", pady=(4, 18))
        ttk.Label(pages[2], text="Java executable", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Entry(pages[2], textvariable=java).pack(fill="x", pady=(6, 8), ipady=5)
        ttk.Label(pages[2],
                  text="Optional. Example: C:\\Program Files\\Java\\bin\\java.exe",
                  style="MutedCard.TLabel", wraplength=500).pack(anchor="w")

        buttons = tk.Frame(shell, bg=BG)
        buttons.pack(fill="x", pady=(12, 0))
        back = ttk.Button(buttons, text="Back")
        back.pack(side="left")
        next_btn = ttk.Button(buttons, text="Next", style="Primary.TButton")
        next_btn.pack(side="right")

        def show(n):
            step.set(n)
            for p in pages: p.pack_forget()
            pages[n].pack(fill="both", expand=True)
            back.config(state="normal" if n else "disabled")
            next_btn.config(text="Create Server" if n == 2 else "Next")
            progress.config(text=[
                "1  •  Name     2  •  Server     3  •  Java",
                "✓ Name     2  •  Server     3  •  Java",
                "✓ Name     ✓ Server     3  •  Java"
            ][n])

        def load_versions():
            try:
                vals = server.versions(kind.get())
                d.after(0, lambda: version_box.configure(values=vals))
                d.after(0, lambda: version.set(vals[0] if vals else ""))
                d.after(0, lambda: version_info.config(
                    text="Select the Minecraft version to install." if vals else "No versions were returned."
                ))
            except Exception as e:
                d.after(0, lambda: version_info.config(text="Could not load versions: " + str(e)))

        def type_changed(_e=None):
            version.set("")
            version_info.config(text="Loading versions…")
            threading.Thread(target=load_versions, daemon=True).start()

        def create_now():
            if not name.get().strip():
                show(0); messagebox.showinfo("Create Server", "Enter a server name.", parent=d); return
            if not version.get():
                show(1); messagebox.showinfo("Create Server", "Choose a Minecraft version.", parent=d); return
            try:
                self.status.config(text="Creating " + name.get().strip() + " server…")
                cfg = server.create(name.get().strip(), kind.get(), version.get(), ram.get(),
                                    java.get().strip() or None)
                cfg["domain_suffix"] = self._server_domain_suffix.get().strip().lower() or self._server_domains[0]
                server.save(name.get().strip(), cfg)
                d.destroy()
                self._refresh_servers()
                self._update_server_access()
                self._show_server_selector()
                self.server_tab.lift()
                self._page_name = "Server"
                self.current_page.config(text="Server")
                self._refresh_nav_buttons()
                self.status.config(text="Server created: " + cfg["name"], foreground=SUCCESS)
            except Exception as e:
                messagebox.showerror("Create Server", str(e), parent=d)

        def next_step():
            n = step.get()
            if n == 0:
                if not name.get().strip():
                    messagebox.showinfo("Create Server", "Enter a server name.", parent=d); return
                show(1)
            elif n == 1:
                if not version.get():
                    messagebox.showinfo("Create Server", "Choose a Minecraft version.", parent=d); return
                show(2)
            else:
                create_now()

        back.config(command=lambda: show(max(0, step.get() - 1)))
        next_btn.config(command=next_step)
        type_box.bind("<<ComboboxSelected>>", type_changed)
        show(0)
        threading.Thread(target=load_versions, daemon=True).start()

    def _delete_server(self):
        name = self._server_name
        if not name:
            return
        if messagebox.askyesno("Delete Server", "Delete '" + name + "' and ALL of its files?"):
            try:
                server.delete(name)
                self._server_name = None
                self._refresh_servers()
                self._update_server_access()
                if not server.list_servers():
                    self.show_page("Play")
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
                def vanilla_worker():
                    try:
                        instances.install_vanilla(mc_version)
                        cfg = instances.load_cfg(name)
                        cfg["loader"] = None
                        cfg["loader_build"] = None
                        cfg["version"] = mc_version
                        instances.save_cfg(name, cfg)
                        self.q.put(("loader_installed", (name, "vanilla", mc_version), None, None))
                    except Exception as e:
                        self.q.put(("fatal", "Minecraft installation failed:\n" + str(e), None, None))
                self.status.config(text="Installing Minecraft " + mc_version + "…")
                self.bar.config(mode="indeterminate")
                self.bar.start(15)
                threading.Thread(target=vanilla_worker, daemon=True).start()
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
        d.geometry("600x470")
        d.minsize(560, 420)
        d.configure(bg=BG)
        d.transient(self.root)
        d.grab_set()

        name = tk.StringVar(value="My Minecraft")
        version = tk.StringVar(value="release")
        loader = tk.StringVar(value="vanilla")
        ram = tk.StringVar(value=self._ram.get() or "4G")
        uname = tk.StringVar(value=self._uname.get() or "Blemm")
        step = tk.IntVar(value=0)

        shell = tk.Frame(d, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        progress = tk.Label(shell, text="1  •  Name     2  •  Minecraft     3  •  Profile",
                            bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        progress.pack(anchor="w", pady=(0, 12))
        pages = [ttk.Frame(shell, style="Card.TFrame", padding=20) for _ in range(3)]

        ttk.Label(pages[0], text="Name your instance", style="Big.TLabel").pack(anchor="w")
        ttk.Label(pages[0], text="Choose a name for this Minecraft installation.",
                  style="MutedCard.TLabel").pack(anchor="w", pady=(4, 18))
        ttk.Label(pages[0], text="Instance name", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Entry(pages[0], textvariable=name).pack(fill="x", pady=(6, 0), ipady=5)

        ttk.Label(pages[1], text="Choose Minecraft", style="Big.TLabel").pack(anchor="w")
        ttk.Label(pages[1], text="Select the game version and loader.",
                  style="MutedCard.TLabel").pack(anchor="w", pady=(4, 18))
        ttk.Label(pages[1], text="Minecraft version", style="MutedCard.TLabel").pack(anchor="w")
        version_box = ttk.Combobox(pages[1], textvariable=version,
                                   values=["release"], state="readonly")
        version_box.pack(fill="x", pady=(6, 14), ipady=4)
        ttk.Label(pages[1], text="Loader", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Combobox(pages[1], textvariable=loader,
                     values=["vanilla","fabric","neoforge","forge"],
                     state="readonly").pack(fill="x", pady=(6, 0), ipady=4)

        ttk.Label(pages[2], text="Profile & memory", style="Big.TLabel").pack(anchor="w")
        ttk.Label(pages[2], text="These settings are saved to the instance.",
                  style="MutedCard.TLabel").pack(anchor="w", pady=(4, 18))
        ttk.Label(pages[2], text="Username", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Entry(pages[2], textvariable=uname).pack(fill="x", pady=(6, 14), ipady=5)
        ttk.Label(pages[2], text="RAM", style="MutedCard.TLabel").pack(anchor="w")
        ttk.Combobox(pages[2], textvariable=ram,
                     values=["2G","4G","6G","8G","12G","16G"],
                     state="readonly").pack(fill="x", pady=(6, 0), ipady=4)

        buttons = tk.Frame(shell, bg=BG)
        buttons.pack(fill="x", pady=(12, 0))
        back = ttk.Button(buttons, text="Back")
        back.pack(side="left")
        next_btn = ttk.Button(buttons, text="Next", style="Primary.TButton")
        next_btn.pack(side="right")

        def show(n):
            step.set(n)
            for p in pages: p.pack_forget()
            pages[n].pack(fill="both", expand=True)
            back.config(state="normal" if n else "disabled")
            next_btn.config(text="Create Instance" if n == 2 else "Next")
            progress.config(text=[
                "1  •  Name     2  •  Minecraft     3  •  Profile",
                "✓ Name     2  •  Minecraft     3  •  Profile",
                "✓ Name     ✓ Minecraft     3  •  Profile"
            ][n])

        def create_now():
            try:
                v = version.get()
                if v == "release":
                    v = core.manifest()["latest"]["release"]
                if not v:
                    raise RuntimeError("Choose a Minecraft version.")
                instance_name = name.get().strip() or "My Minecraft"
                ld = None if loader.get() == "vanilla" else loader.get()
                instances.create(instance_name, v, ld, ram.get(), uname.get() or "Blemm")
                d.destroy()
                self._refresh_list()
                self._select_instance(instance_name)
            except Exception as e:
                messagebox.showerror("New Instance", str(e), parent=d)

        def next_step():
            n = step.get()
            if n == 0:
                if not name.get().strip():
                    messagebox.showinfo("New Instance", "Enter an instance name.", parent=d); return
                show(1)
            elif n == 1:
                show(2)
            else:
                create_now()

        back.config(command=lambda: show(max(0, step.get() - 1)))
        next_btn.config(command=next_step)

        def apply_versions():
            try:
                vals = self._all_versions or core.list_versions()[0]
                d.after(0, lambda: version_box.configure(values=["release"] + vals))
            except Exception:
                pass

        show(0)
        threading.Thread(target=apply_versions, daemon=True).start()

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

    def _check_for_updates(self):
        try:
            update = updater.check_latest()
            if update:
                self.q.put(("update_available", update, None, None))
        except Exception:
            pass

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

                if kind == "update_available":
                    update = text or {}
                    version = str(update.get("version", ""))
                    if messagebox.askyesno(
                        "BlemmLauncher Update",
                        "New update! Install now?\\n\\nVersion " + version
                    ):
                        try:
                            self.status.config(
                                text="Downloading update…",
                                foreground=FG
                            )
                            updater.install(update)
                            self.root.destroy()
                            return
                        except Exception as e:
                            messagebox.showerror(
                                "BlemmLauncher Update",
                                "Update failed:\\n" + str(e)
                            )

                elif kind == "owner_agent_ready":
                    self._remote_agent_id = text.get("agent_id")
                    self._owner_agent_started = True
                    self.status.config(
                        text="Owner PC connected permanently.",
                        foreground=SUCCESS
                    )
                    self._remote_refresh_agents()

                elif kind == "owner_agent_error":
                    self.status.config(
                        text="Owner PC connection failed: " + str(text),
                        foreground=DANGER
                    )

                elif kind == "stage":
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
                    values = ["release"] + list(text)
                    self.loader_version_combo.configure(values=values)
                    if self.loader_version.get() not in values:
                        self.loader_version.set("release")

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

                elif kind == "modrinth_home_results":
                    mc_version, loader, sections = text
                    self._modrinth_searching = False
                    self._modrinth_home_loaded = True
                    self._modrinth_clear_cards()
                    ttk.Label(
                        self.modrinth_cards,
                        text="Discover • Minecraft " + str(mc_version),
                        style="Accent.TLabel"
                    ).pack(anchor="w", padx=18, pady=(16, 6))
                    for section_title, ptype, hits in sections:
                        section = ttk.Frame(self.modrinth_cards, style="Card.TFrame")
                        section.pack(fill="x", padx=10, pady=(8, 4))
                        ttk.Label(
                            section, text=section_title,
                            style="Big.TLabel"
                        ).pack(anchor="w", padx=8, pady=(4, 4))
                        if not hits:
                            ttk.Label(
                                section, text="Nothing found for this version.",
                                style="MutedCard.TLabel"
                            ).pack(anchor="w", padx=8, pady=(0, 8))
                            continue
                        for hit in hits:
                            # Re-parent the card into this section temporarily.
                            self.modrinth_cards = section
                            self._store_card(
                                hit, self.modrinth_target.get().strip(),
                                mc_version, loader, ptype, parent=section
                            )
                        self.modrinth_cards = self._modrinth_cards_root
                    # Restore the actual scroll content frame.
                    # Cards above were created in each section, so keep the root frame reference.
                    self.modrinth_cards = self._modrinth_cards_root
                    self.status.config(
                        text="Modrinth Discover loaded", foreground=SUCCESS
                    )

                elif kind == "modrinth_image":
                    parent, key, image = text
                    if parent is not None and parent.winfo_exists():
                        photo = ImageTk.PhotoImage(image)
                        parent.configure(image=photo, text="")
                        parent.image = photo
                        self._modrinth_image_refs[key] = photo

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

                elif kind == "dev_login":
                    self._dev_identity = text
                    username = str((text or {}).get("username", "Developer"))
                    self._dev_status_label.config(
                        text="Authenticated • " + username,
                        foreground=SUCCESS
                    )
                    self._dev_login_button.config(
                        state="normal",
                        text="Developer Authenticated"
                    )
                    self._add_developer_nav()
                    self._show_developer_controls()
                    self.status.config(
                        text="Developer authentication successful",
                        foreground=SUCCESS
                    )
                    self.log_message("Developer authenticated: " + username)
                    self._remote_refresh_agents()

                elif kind == "dev_login_error":
                    self._dev_status_label.config(
                        text="Authentication failed",
                        foreground=DANGER
                    )
                    self._dev_login_button.config(
                        state="normal",
                        text="Developer Login"
                    )
                    self.status.config(
                        text="Developer authentication failed",
                        foreground=DANGER
                    )
                    self.log_message("Developer authentication failed: " + str(text))


                elif kind == "remote_pair":
                    code = str((text or {}).get("pairing_code", ""))
                    self._remote_pairing_label.config(
                        text="Pairing code: " + code + "  • expires in 10 minutes",
                        foreground=SUCCESS
                    )
                    self.status.config(text="Pairing code generated. Run the agent on the server PC.", foreground=SUCCESS)

                elif kind == "remote_agents":
                    self._remote_agents = list(text or [])

                    # The Developer tab no longer exposes a server-PC selector.
                    # Automatically use the first online paired agent.
                    online = [
                        a for a in self._remote_agents
                        if str(a.get("status", "")).lower() == "online"
                    ]
                    candidates = online or self._remote_agents
                    if candidates:
                        if self._remote_agent_id not in [a.get("id") for a in candidates]:
                            self._remote_agent_id = candidates[0].get("id")
                        selected = next(
                            (a for a in candidates if a.get("id") == self._remote_agent_id),
                            candidates[0]
                        )
                        self._remote_agent_id = selected.get("id")
                        self._remote_status_label.config(
                            text=str(selected.get("status", "offline")).upper(),
                            foreground=(
                                SUCCESS
                                if str(selected.get("status", "")).lower() == "online"
                                else DANGER
                            )
                        )
                        self._remote_action("status")
                    else:
                        self._remote_agent_id = None
                        self._remote_status_label.config(
                            text="No paired server PCs.",
                            foreground=MUTED
                        )

                elif kind == "remote_result":
                    action, result_status, result = text
                    if result_status == "error":
                        self._remote_status_label.config(text=str(result.get("error", "Remote action failed.")), foreground=DANGER)
                    else:
                        self._remote_status_label.config(text=action.title() + " completed", foreground=SUCCESS)
                        if action == "status":
                            servers = result.get("servers", [])
                        elif action == "logs":
                            self._remote_console.delete("1.0", "end")
                            for line in result.get("lines", []):
                                self._remote_console.insert("end", str(line.get("line", "")) + "\n")
                            self._remote_console.see("end")
                            self._schedule_remote_console_refresh()
                        elif action == "read_file":
                            self._remote_console.delete("1.0", "end")
                            self._remote_console.insert("1.0", result.get("content", ""))
                        elif action == "write_file":
                            self.status.config(text="Saved remote file: " + str(result.get("path", "")), foreground=SUCCESS)

                elif kind == "remote_error":
                    self._remote_status_label.config(text="Remote server error: " + str(text), foreground=DANGER)
                    self.status.config(text="Remote developer server action failed", foreground=DANGER)

                elif kind == "developer_list":
                    for item in self._developer_tree.get_children():
                        self._developer_tree.delete(item)
                    for row in text or []:
                        self._developer_tree.insert(
                            "", "end",
                            values=(row.get("username", ""), row.get("role", "developer"),
                                    row.get("created_at", ""))
                        )
                    self.status.config(text="Developer accounts refreshed", foreground=SUCCESS)

                elif kind == "developer_created":
                    self.status.config(text="Developer account updated", foreground=SUCCESS)
                    self._developer_refresh()

                elif kind == "developer_deleted":
                    self.status.config(text="Developer deleted: " + str(text), foreground=SUCCESS)
                    self._developer_refresh()

                elif kind == "developer_error":
                    self.status.config(text="Developer action failed", foreground=DANGER)
                    self.log_message("Developer error: " + str(text))

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
