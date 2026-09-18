import os, threading, tkinter as tk
from tkinter import ttk, filedialog
from . import core

class App:
    def __init__(self, root):
        self.root = root
        root.title("BlemmLauncher"); root.geometry("420x380")
        ttk.Label(root, text="BlemmLauncher", font=("Segoe UI", 20, "bold")).pack(pady=8)
        f = ttk.Frame(root); f.pack(fill="x", padx=12)
        ttk.Label(f, text="Version:").grid(row=0, column=0)
        self.vid = ttk.Entry(f); self.vid.insert(0, "release"); self.vid.grid(row=0, column=1, sticky="we")
        ttk.Label(f, text="Name:").grid(row=1, column=0)
        self.name = ttk.Entry(f); self.name.insert(0, "Blemm"); self.name.grid(row=1, column=1, sticky="we")
        ttk.Label(f, text="RAM:").grid(row=2, column=0)
        self.ram = ttk.Combobox(f, values=["2G", "4G", "6G", "8G"]); self.ram.set("2G"); self.ram.grid(row=2, column=1)
        ttk.Label(f, text="Forge (leave blank for vanilla):").grid(row=3, column=0)
        self.forge = ttk.Entry(f); self.forge.grid(row=3, column=1, sticky="we")
        self.optifine = None
        ttk.Button(root, text="Pick OptiFine installer (optional)", command=self.pick_of).pack(pady=4)
        ttk.Button(root, text=" ▶  PLAY", command=self.play).pack(pady=8)
        self.status = ttk.Label(root, text="", wraplength=380); self.status.pack()
        f.columnconfigure(1, weight=True)

    def pick_of(self):
        p = filedialog.askopenfilename(filetypes=[("OptiFine installer", "*.jar")])
        if p: self.optifine = p

    def play(self):
        threading.Thread(target=self._play, daemon=True).start()

    def _play(self):
        try:
            vid = self.vid.get().strip()
            if self.forge.get().strip():
                vid = core.install_forge(self.forge.get().strip())
            if vid == "release": vid = core.manifest()["latest"]["release"]
            core.launch(vid, self.name.get() or "Blemm", self.ram.get(), self.optifine)
        except Exception as e:
            self.root.after(0, lambda e=e: self.status.config(text=f"Error: {e}"))

def run():
    root = tk.Tk(); App(root); root.mainloop()
