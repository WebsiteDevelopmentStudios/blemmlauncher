import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext

from Dev import auth as dev_auth
from . import server

BG = "#07110b"
CARD = "#102218"
FIELD = "#142b1d"
FG = "#9CFFBC"
MUTED = "#82a995"
ACCENT = "#38ed7c"
PRIMARY = "#19b95b"
DANGER = "#ff687a"


class OwnerServerManager:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("BlemmLauncher • Server Management")
        self.win.geometry("1050x700")
        self.win.minsize(900, 600)
        self.win.configure(bg=BG)

        self.agent = ""
        self.server = ""
        self.path = ""
        self.agents = []
        self.servers = []
        self.local = bool((getattr(app, "_dev_identity", None) or {}).get("role") == "owner")

        self.status = tk.StringVar(value="Loading…")
        self.server_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.file_var = tk.StringVar()

        self._build()
        self.refresh_agents()

    def _button(self, parent, text, command, primary=False, danger=False):
        return tk.Button(
            parent, text=text, command=command,
            bg=DANGER if danger else (PRIMARY if primary else FIELD),
            fg="#04130a" if primary else ("#21060a" if danger else FG),
            activebackground=ACCENT if primary else "#0a3a20",
            activeforeground="#04130a" if primary else FG,
            relief="flat", bd=0, highlightthickness=0,
            padx=11, pady=7, font=("Segoe UI", 9, "bold"), cursor="hand2"
        )

    def _build(self):
        head = tk.Frame(self.win, bg=BG)
        head.pack(fill="x", padx=16, pady=14)
        tk.Label(head, text="Server Management", bg=BG, fg=FG,
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(head, textvariable=self.status, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="right")

        bar = tk.Frame(self.win, bg=CARD)
        bar.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(bar, text="Server PC", bg=CARD, fg=MUTED).pack(side="left", padx=10, pady=9)
        self.agent_box = ttk.Combobox(bar, state="readonly", width=32)
        self.agent_box.pack(side="left", padx=(0, 12))
        tk.Label(bar, text="Minecraft server", bg=CARD, fg=MUTED).pack(side="left")
        self.server_box = ttk.Combobox(bar, textvariable=self.server_var, state="readonly", width=28)
        self.server_box.pack(side="left", padx=8)
        self.agent_box.bind("<<ComboboxSelected>>", lambda e: self._agent_changed())
        self.server_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_files())

        controls = tk.Frame(self.win, bg=BG)
        controls.pack(fill="x", padx=16, pady=(0, 8))
        self._button(controls, "Create Server", self.create_server, True).pack(side="left")
        self._button(controls, "Refresh", self.refresh_servers).pack(side="left", padx=6)
        for label, action in (("Start","start"),("Stop","stop"),("Restart","restart"),("Console","logs")):
            self._button(controls, label, lambda a=action: self.server_action(a)).pack(side="left", padx=3)
        self._button(controls, "Delete Server", self.delete_server, danger=True).pack(side="right")

        body = tk.Frame(self.win, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        left = tk.Frame(body, bg=CARD)
        left.pack(side="left", fill="both", expand=False)
        tk.Label(left, text="Server Files", bg=CARD, fg=FG,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        tk.Label(left, textvariable=self.path_var, bg=CARD, fg=MUTED).pack(anchor="w", padx=10, pady=(0, 6))
        self.files = tk.Listbox(left, width=38, bg="#0a1710", fg=FG,
                                selectbackground="#0a3a20", relief="flat", bd=0)
        self.files.pack(fill="both", expand=True, padx=8)
        self.files.bind("<Double-Button-1>", lambda e: self.open_selected())

        row = tk.Frame(left, bg=CARD)
        row.pack(fill="x", padx=8, pady=8)
        for label, fn in (("Open",self.open_selected),("Up",self.go_up),
                          ("New File",self.new_file),("New Folder",self.new_folder),
                          ("Rename",self.rename),("Delete",self.delete_file)):
            self._button(row, label, fn).pack(side="left", padx=2)

        right = tk.Frame(body, bg=CARD)
        right.pack(side="left", fill="both", expand=True, padx=(10,0))
        top = tk.Frame(right, bg=CARD)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="File", bg=CARD, fg=MUTED).pack(side="left")
        tk.Entry(top, textvariable=self.file_var, bg=FIELD, fg=FG,
                 insertbackground=FG, relief="flat").pack(side="left", fill="x", expand=True, padx=7, ipady=6)
        self._button(top, "Load", self.load_file).pack(side="left")
        self._button(top, "Save", self.save_file, True).pack(side="left", padx=5)
        self.editor = scrolledtext.ScrolledText(
            right, bg="#07170d", fg="#8CFFB1", insertbackground=ACCENT,
            relief="flat", bd=0, wrap="none", font=("Consolas", 9)
        )
        self.editor.pack(fill="both", expand=True, padx=10, pady=(0,10))

    def call(self, action, payload, callback):
        if self.local:
            def local_worker():
                try:
                    name = str(payload.get("server", "")).strip()
                    if action == "status":
                        rows = []
                        for n in server.list_servers():
                            try:
                                cfg = server.load(n)
                                rows.append({"name": n, "running": bool(server.running(n)), "type": cfg.get("type"), "version": cfg.get("version"), "ram": cfg.get("ram")})
                            except Exception:
                                rows.append({"name": n, "running": bool(server.running(n))})
                        result = {"servers": rows}
                    elif action == "start":
                        server.start(name, lambda n, line: None)
                        result = {"server": name, "running": True}
                    elif action == "stop":
                        server.stop(name)
                        result = {"server": name, "running": False}
                    elif action == "restart":
                        server.stop(name)
                        time.sleep(1.5)
                        server.start(name, lambda n, line: None)
                        result = {"server": name, "running": True}
                    elif action == "logs":
                        result = {"server": name, "lines": []}
                    elif action == "create_server":
                        result = server.create(name, str(payload.get("type", "paper")).strip().lower(), str(payload.get("version", "")).strip(), ram=str(payload.get("ram", "4G")).strip() or "4G")
                    elif action == "files":
                        rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
                        result = {"server": name, "path": rel, "files": server.tree(name, rel)}
                    elif action == "read_file":
                        rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
                        result = {"server": name, "path": rel, "content": server.read_file(name, rel)}
                    elif action == "write_file":
                        rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
                        content = str(payload.get("content", ""))
                        if len(content.encode("utf-8")) > 5 * 1024 * 1024:
                            raise RuntimeError("Remote editor writes are limited to 5 MB.")
                        server.write_file(name, rel, content)
                        result = {"server": name, "path": rel, "saved": True}
                    elif action == "create_folder":
                        rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
                        server.create_folder(name, rel)
                        result = {"server": name, "path": rel, "created": True}
                    elif action == "create_file":
                        rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
                        server.create_file(name, rel, str(payload.get("content", "")))
                        result = {"server": name, "path": rel, "created": True}
                    elif action == "delete_file":
                        rel = str(payload.get("path", "")).replace("\\", "/").strip("/")
                        if not rel:
                            raise RuntimeError("Cannot delete the server root.")
                        server.remove(name, rel)
                        result = {"server": name, "path": rel, "deleted": True}
                    elif action == "rename_file":
                        old = str(payload.get("old", "")).replace("\\", "/").strip("/")
                        new = str(payload.get("new", "")).replace("\\", "/").strip("/")
                        server.rename(name, old, new)
                        result = {"server": name, "old": old, "new": new}
                    elif action == "delete_server":
                        server.delete(name)
                        result = {"server": name, "deleted": True}
                    else:
                        raise RuntimeError("Unsupported local server action: " + action)
                    self.win.after(0, lambda r=result: callback(r, None))
                except Exception as exc:
                    self.win.after(0, lambda e=str(exc): callback(None, e))
            threading.Thread(target=local_worker, daemon=True).start()
            return

        token = self.app._remote_token()
        if not token:
            callback(None, "Developer authentication has expired. Please log in again.")
            return
        if not self.agent:
            callback(None, "Select an online server PC.")
            return
        selected_agent = next(
            (a for a in self.agents if str(a.get("id", "")) == str(self.agent)),
            None,
        )
        if selected_agent and str(selected_agent.get("status", "")).lower() != "online":
            callback(None, "The selected server PC is offline. Start the BlemmLauncher agent on that PC.")
            return

        def worker():
            try:
                queued = dev_auth.send_agent_command(token, self.agent, action, payload)
                cid = queued.get("command_id")
                for _ in range(60):
                    time.sleep(1)
                    rows = dev_auth.list_agent_commands(token, self.agent)
                    row = next((x for x in rows if int(x.get("id",-1)) == int(cid)), None)
                    if row and row.get("status") in ("completed","error"):
                        try:
                            result = json.loads(row.get("result") or "{}")
                        except Exception:
                            result = {}
                        err = result.get("error") if row.get("status") == "error" else None
                        self.win.after(0, lambda r=result, e=err: callback(r, e))
                        return
                self.win.after(0, lambda: callback(None, "Remote server timed out."))
            except Exception as exc:
                self.win.after(0, lambda: callback(None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _agent_changed(self):
        index = self.agent_box.current()
        if 0 <= index < len(self.agents):
            self.agent = self.agents[index].get("id", "")
        self.server_var.set("")
        self.server_box["values"] = ()
        self.files.delete(0, "end")
        self.path = ""
        self.path_var.set("/")
        self.refresh_servers()

    def refresh_agents(self):
        if self.local:
            self.agents = [{"id": "local-owner-pc", "name": "This PC", "status": "online", "owner_username": "Blemm"}]
            self.agent_box["values"] = ["This PC • ONLINE"]
            self.agent_box.current(0)
            self.agent = "local-owner-pc"
            self.status.set("This PC connected • Owner access")
            self.refresh_servers()
            return

        token = self.app._remote_token()
        if not token:
            self.status.set("Developer authentication has expired.")
            messagebox.showerror(
                "Server Management",
                "Your developer session has expired. Log in again before managing servers.",
                parent=self.win,
            )
            return
        self.status.set("Loading server PCs…")
        def worker():
            try:
                rows = dev_auth.list_agents(token)
                self.win.after(0, lambda: self.apply_agents(rows))
            except Exception as exc:
                self.win.after(0, lambda err=str(exc): self._show_error(err))
        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, message):
        self.status.set(str(message))
        messagebox.showerror("Server Management", str(message), parent=self.win)

    def apply_agents(self, rows):
        self.agents = rows or []
        values = [
            str(a.get("name", "Unnamed")) + " • " +
            str(a.get("status", "offline")).upper()
            for a in self.agents
        ]
        self.agent_box["values"] = values
        if values:
            self.agent_box.current(0)
            self.agent = self.agents[0].get("id", "")
            self.refresh_servers()
            if str(self.agents[0].get("status", "")).lower() != "online":
                self.status.set("Server PC is offline — start the BlemmLauncher agent.")
        else:
            self.agent = ""
            self.server_box["values"] = ()
            self.server_var.set("")
            self.files.delete(0, "end")
            self.status.set("No paired server PCs. Pair a server PC first.")

    def refresh_servers(self):
        if self.agent_box.current() >= 0 and self.agents:
            self.agent = self.agents[self.agent_box.current()].get("id","")
        if not self.agent:
            return
        self.status.set("Loading servers…")
        self.call("status", {}, self.apply_servers)

    def apply_servers(self, result, error):
        if error:
            self.status.set(error)
            return
        self.servers = result.get("servers", []) if result else []
        names = [str(x.get("name","")) for x in self.servers]
        self.server_box["values"] = names
        if names:
            self.server_var.set(names[0] if self.server_var.get() not in names else self.server_var.get())
            self.refresh_files()
            self.status.set("Servers ready.")
        else:
            self.server_var.set("")
            self.files.delete(0,"end")
            self.status.set("No servers on this PC.")

    def server_action(self, action):
        name = self.server_var.get().strip()
        if not name:
            self._show_error("Select a Minecraft server first.")
            return
        self.status.set(action.title() + "…")
        def done(result, error):
            if error:
                self._show_error(error)
                return
            self.status.set(action.title() + " completed.")
            if action in ("start", "stop", "restart"):
                self.refresh_servers()
            elif action == "logs":
                lines = (result or {}).get("lines", [])
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", "\n".join(str(x.get("line", "")) for x in lines))
                self.file_var.set("")
                self.status.set("Console output loaded.")
        self.call(action, {"server": name}, done)

    def create_server(self):
        if not self.agent:
            self._show_error("Select an online server PC first.")
            return
        name = simpledialog.askstring("Create Server","Server name:",parent=self.win)
        if not name: return
        kind = simpledialog.askstring("Create Server",
            "Type: vanilla, paper, fabric, forge, or neoforge",
            initialvalue="paper",parent=self.win)
        if not kind: return
        version = simpledialog.askstring("Create Server","Minecraft version:",parent=self.win)
        if not version: return
        ram = simpledialog.askstring("Create Server","RAM:",initialvalue="4G",parent=self.win)
        if not ram: return
        self.status.set("Installing server…")
        self.call("create_server", {"server":name.strip(),"type":kind.strip(),
                   "version":version.strip(),"ram":ram.strip()},
                  lambda r,e: (self.status.set(e or "Server created."), self.refresh_servers()))

    def refresh_files(self):
        if not self.server_var.get():
            self.status.set("Select a Minecraft server first.")
            return
        self.status.set("Loading files…")
        self.call("files", {"server":self.server_var.get(),"path":self.path},
                  self.apply_files)

    def apply_files(self, result, error):
        if error:
            self.status.set(error); return
        self.path = str(result.get("path","")).strip("/")
        self.path_var.set("/" + self.path if self.path else "/")
        self.files.delete(0,"end")
        for item in result.get("files",[]):
            self.files.insert("end", ("[DIR] " if item.get("dir") else "[FILE] ") + str(item.get("name","")))
        self.status.set("Files loaded.")

    def selected_path(self):
        sel = self.files.curselection()
        if not sel: return None
        item = self.files.get(sel[0])
        name = item.split(" ",1)[1]
        return (self.path + "/" + name).strip("/") if self.path else name

    def open_selected(self):
        p = self.selected_path()
        if not p: return
        if self.files.get(self.files.curselection()[0]).startswith("[DIR] "):
            self.path = p
            self.refresh_files()
        else:
            self.file_var.set(p)
            self.load_file()

    def go_up(self):
        self.path = "/".join(self.path.split("/")[:-1]) if self.path else ""
        self.refresh_files()

    def load_file(self):
        p = self.file_var.get().strip()
        if not p:
            self._show_error("Enter a file path first.")
            return
        self.status.set("Loading file…")
        self.call("read_file",{"server":self.server_var.get(),"path":p},
                  lambda r,e: (self.editor.delete("1.0","end"),
                                self.editor.insert("1.0",(r or {}).get("content","")) if not e else None,
                                self.status.set(e or "File loaded.")))

    def save_file(self):
        p = self.file_var.get().strip()
        if not p:
            self._show_error("Enter a file path first.")
            return
        if not self.server_var.get().strip():
            self._show_error("Select a Minecraft server first.")
            return
        content = self.editor.get("1.0","end-1c")
        if len(content.encode()) > 5*1024*1024:
            messagebox.showerror("Server Files","Files over 5 MB cannot be edited.",parent=self.win)
            return
        self.status.set("Saving…")
        self.call("write_file",{"server":self.server_var.get(),"path":p,"content":content},
                  lambda r,e: self.status.set(e or "File saved."))

    def new_file(self):
        p=simpledialog.askstring("New File","Path relative to server root:",parent=self.win)
        if not p:return
        self.call("create_file",{"server":self.server_var.get(),"path":p},
                  lambda r,e:(self.status.set(e or "File created."),self.refresh_files()))

    def new_folder(self):
        p=simpledialog.askstring("New Folder","Folder path relative to server root:",parent=self.win)
        if not p:return
        self.call("create_folder",{"server":self.server_var.get(),"path":p},
                  lambda r,e:(self.status.set(e or "Folder created."),self.refresh_files()))

    def rename(self):
        old=self.selected_path()
        if not old:return
        new=simpledialog.askstring("Rename","New path:",initialvalue=old,parent=self.win)
        if not new:return
        self.call("rename_file",{"server":self.server_var.get(),"old":old,"new":new},
                  lambda r,e:(self.status.set(e or "Renamed."),self.refresh_files()))

    def delete_file(self):
        p=self.selected_path()
        if not p:return
        if not messagebox.askyesno("Delete","Delete "+p+"?",parent=self.win):return
        self.call("delete_file",{"server":self.server_var.get(),"path":p},
                  lambda r,e:(self.status.set(e or "Deleted."),self.refresh_files()))

    def delete_server(self):
        name=self.server_var.get()
        if not name:
            self._show_error("Select a Minecraft server first.")
            return
        if not messagebox.askyesno("Delete Server",
            "Permanently delete '"+name+"' and all of its files?",parent=self.win):return
        self.call("delete_server",{"server":name},
                  lambda r,e:(self.status.set(e or "Server deleted."),self.refresh_servers()))
