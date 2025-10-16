#!/usr/bin/env python3
"""
EMU64 v1.0 - Standalone Edition
Full-featured N64 Emulator Frontend
Based on MIPS R4300i Architecture

Includes:
- Plugin system (PJ64/Zilmar-spec DLL support)
- Cheat engine
- GUI management
- Cross-platform support (Windows, macOS, Linux)

© 2025 FlamesCo & Samsoft
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import struct
import time
import threading
import random
import json
import pickle
import zlib
import os
import glob
import ctypes
import platform
from pathlib import Path
from datetime import datetime
from collections import deque

# ============================================================================
# METADATA
# ============================================================================
EMU_NAME = "EMU64"
EMU_VERSION = "1.0.0"
EMU_BUILD = "Standalone Edition"
EMU_COPYRIGHT = "© 2025 FlamesCo & Samsoft"
WINDOW_TITLE = f"{EMU_NAME} v{EMU_VERSION}"

# ============================================================================
# EMULATOR CORE PLACEHOLDER
# ============================================================================
class EmuDarkness:
    """Core placeholder for EMU64 (original EmuDarkness core)."""
    def __init__(self):
        self.cheats = CheatManager()
        self.zilmar = None
        self.memory = bytearray(8 * 1024 * 1024)  # 8MB RDRAM mock
        self.running = False

    def load_rom(self, path):
        self.rom_path = path
        print(f"[EMU64] ROM loaded: {path}")

    def run(self):
        print("[EMU64] Emulation started.")
        self.running = True

    def stop(self):
        print("[EMU64] Emulation stopped.")
        self.running = False


# ============================================================================
# CHEAT SYSTEM
# ============================================================================
class Cheat:
    def __init__(self, name, code):
        self.name = name
        self.code = code


class CheatManager:
    def __init__(self):
        self.cheats = []

    def add_cheat(self, name, code):
        self.cheats.append(Cheat(name, code))

    def remove_cheat(self, index):
        if 0 <= index < len(self.cheats):
            del self.cheats[index]

    def list_cheats(self):
        return [(c.name, c.code) for c in self.cheats]


class CheatDialog(tk.Toplevel):
    def __init__(self, parent, emulator):
        super().__init__(parent)
        self.emulator = emulator
        self.title("Cheat Codes")
        self.geometry("400x300")
        self.resizable(False, False)

        self.listbox = tk.Listbox(self)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        frame = ttk.Frame(self)
        frame.pack(fill=tk.X, padx=10)
        ttk.Button(frame, text="Add", command=self.add_cheat).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="Remove", command=self.remove_cheat).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="Close", command=self.destroy).pack(side=tk.RIGHT, padx=2)

        self.refresh_list()

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for name, code in self.emulator.cheats.list_cheats():
            self.listbox.insert(tk.END, f"{name}: {code}")

    def add_cheat(self):
        name = simpledialog.askstring("Cheat Name", "Enter name:")
        code = simpledialog.askstring("Cheat Code", "Enter code:")
        if name and code:
            self.emulator.cheats.add_cheat(name, code)
            self.refresh_list()

    def remove_cheat(self):
        selection = self.listbox.curselection()
        if selection:
            self.emulator.cheats.remove_cheat(selection[0])
            self.refresh_list()

# ============================================================================
# ZILMAR/PROJECT64 PLUGIN BRIDGE (Windows-only)
# ============================================================================
ZILMAR_TYPE_MAP = {1: "RSP", 2: "GFX", 3: "AUDIO", 4: "INPUT"}

class ZilmarPluginError(Exception):
    pass


class PLUGIN_INFO(ctypes.Structure):
    _fields_ = [
        ("Version", ctypes.c_uint16),
        ("Type", ctypes.c_uint16),
        ("Name", ctypes.c_char * 100),
        ("NormalMemory", ctypes.c_int),
        ("MemorySwapped", ctypes.c_int),
    ]


class ZilmarPlugin:
    def __init__(self, path):
        self.path = path
        self.dll = None
        self.info = None
        self._load()

    @staticmethod
    def _try_load(path):
        try:
            return ctypes.WinDLL(path)
        except OSError:
            return ctypes.CDLL(path)

    def _load(self):
        if os.name != "nt":
            raise ZilmarPluginError("Zilmar plugins are Windows-only DLLs.")
        self.dll = self._try_load(self.path)
        try:
            fn = self.dll.GetDllInfo
        except AttributeError:
            raise ZilmarPluginError("Not a zilmar plugin (GetDllInfo missing)")
        fn.argtypes = [ctypes.POINTER(PLUGIN_INFO)]
        fn.restype = None
        info = PLUGIN_INFO()
        fn(ctypes.byref(info))
        self.info = info

    @property
    def type_code(self):
        return int(self.info.Type)

    @property
    def type_name(self):
        return ZILMAR_TYPE_MAP.get(self.type_code, f"UNKNOWN({self.type_code})")

    @property
    def name(self):
        return self.info.Name.decode("ascii", errors="ignore").strip("\x00")

    def config(self, parent_hwnd=None):
        fn = getattr(self.dll, "DllConfig", None)
        if not fn:
            return False
        fn.argtypes = [ctypes.c_void_p]
        fn(ctypes.c_void_p(parent_hwnd or 0))
        return True

    def about(self, parent_hwnd=None):
        fn = getattr(self.dll, "DllAbout", None)
        if not fn:
            return False
        fn.argtypes = [ctypes.c_void_p]
        fn(ctypes.c_void_p(parent_hwnd or 0))
        return True


class ZilmarPluginManager:
    def __init__(self):
        self.plugins = {"GFX": [], "AUDIO": [], "INPUT": [], "RSP": []}
        self.selected = {"GFX": None, "AUDIO": None, "INPUT": None, "RSP": None}
        appdata = os.environ.get("APPDATA", "")
        pj64_plugin = os.path.join(appdata, "Project64", "Plugin") if appdata else ""
        self.search_paths = [str(Path.cwd() / "plugins"), pj64_plugin, str(Path.cwd())]

    def scan(self):
        self.plugins = {"GFX": [], "AUDIO": [], "INPUT": [], "RSP": []}
        if os.name != "nt":
            return self.plugins
        seen = set()
        for base in filter(None, self.search_paths):
            for dll in glob.glob(os.path.join(base, "*.dll")):
                key = dll.lower()
                if key in seen:
                    continue
                try:
                    p = ZilmarPlugin(dll)
                    self.plugins[p.type_name].append(p)
                    seen.add(key)
                except Exception:
                    pass
        for k in self.plugins:
            self.plugins[k].sort(key=lambda pl: pl.name.lower())
        return self.plugins

    def add_plugin_file(self, path):
        p = ZilmarPlugin(path)
        self.plugins[p.type_name].append(p)
        self.plugins[p.type_name].sort(key=lambda pl: pl.name.lower())
        return p


class PluginsDialog(tk.Toplevel):
    def __init__(self, parent, emulator):
        super().__init__(parent)
        self.emulator = emulator
        self.title("EMU64 Plugins (PJ64/zilmar)")
        self.geometry("720x420")
        self.resizable(False, False)
        self.mgr = self.emulator.zilmar or ZilmarPluginManager()
        self.mgr.scan()
        self._make_ui()

    def _make_ui(self):
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.columns = {}
        kinds = [("Graphics (GFX)", "GFX"), ("Audio", "AUDIO"),
                 ("Input", "INPUT"), ("RSP", "RSP")]
        for col_idx, (title, key) in enumerate(kinds):
            lf = ttk.LabelFrame(root, text=title, padding=5)
            lf.grid(row=0, column=col_idx, sticky="nsew", padx=5)
            lb = tk.Listbox(lf, height=16, exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            self.columns[key] = lb
            for p in self.mgr.plugins.get(key, []):
                lb.insert(tk.END, p.name)
            lb.bind("<<ListboxSelect>>", lambda e, k=key: self._on_select(k))

        for i in range(4):
            root.columnconfigure(i, weight=1)
        root.rowconfigure(0, weight=1)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=10, pady=(0,10))
        ttk.Button(btns, text="Add Plugin…", command=self._add_plugin).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Configure Selected", command=self._config_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="About", command=self._about_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Close", command=self._save_and_close).pack(side=tk.RIGHT, padx=4)

        note = ttk.Label(self, text="Note: PJ64/zilmar plugins are functional only on Windows.",
                         foreground="gray")
        note.pack(padx=10, pady=(0,8), anchor="w")

    def _current_hwnd(self):
        try:
            return int(self.winfo_id()) if os.name == "nt" else None
        except Exception:
            return None

    def _on_select(self, key):
        lb = self.columns[key]
        sel = lb.curselection()
        if not sel:
            return
        idx = sel[0]
        arr = self.mgr.plugins.get(key, [])
        if 0 <= idx < len(arr):
            self.mgr.selected[key] = arr[idx]

    def _add_plugin(self):
        path = filedialog.askopenfilename(title="Add PJ64/zilmar plugin DLL", filetypes=[("DLL", "*.dll")])
        if not path:
            return
        try:
            p = self.mgr.add_plugin_file(path)
            lb = self.columns[p.type_name]
            lb.insert(tk.END, p.name)
        except Exception as e:
            messagebox.showerror("Plugin Load Failed", str(e))

    def _config_selected(self):
        hwnd = self._current_hwnd()
        any_done = False
        for key, lb in self.columns.items():
            sel = lb.curselection()
            if sel:
                idx = sel[0]
                arr = self.mgr.plugins.get(key, [])
                if 0 <= idx < len(arr):
                    if arr[idx].config(hwnd):
                        any_done = True
        if not any_done:
            messagebox.showinfo("Plugins", "No configurable plugin selected or missing DllConfig().")

    def _about_selected(self):
        hwnd = self._current_hwnd()
        any_done = False
        for key, lb in self.columns.items():
            sel = lb.curselection()
            if sel:
                idx = sel[0]
                arr = self.mgr.plugins.get(key, [])
                if 0 <= idx < len(arr):
                    if arr[idx].about(hwnd):
                        any_done = True
        if not any_done:
            messagebox.showinfo("Plugins", "No plugin with DllAbout() selected.")

    def _save_and_close(self):
        self.emulator.zilmar = self.mgr
        self.destroy()


# ============================================================================
# MAIN GUI APPLICATION
# ============================================================================
class EMU64Core:
    pass  # alias for reference


class EmuDarknessGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        self.emulator = EmuDarkness()
        self.emulator.zilmar = ZilmarPluginManager() if os.name == "nt" else None

        self.create_menu()
        ttk.Label(root, text=f"{EMU_NAME} - N64 Emulator Frontend\n{EMU_COPYRIGHT}",
                  font=("Arial", 12)).pack(pady=20)

    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load ROM...", command=self.load_rom)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Cheat Codes...", command=self.show_cheats)
        options_menu.add_separator()
        options_menu.add_command(label="Plugins (PJ64/zilmar)...", command=self.show_plugins)
        menubar.add_cascade(label="Options", menu=options_menu)

    def load_rom(self):
        path = filedialog.askopenfilename(title="Open ROM", filetypes=[("N64 ROM", "*.z64 *.n64 *.v64")])
        if path:
            self.emulator.load_rom(path)
            messagebox.showinfo("ROM Loaded", f"Loaded ROM: {os.path.basename(path)}")

    def show_cheats(self):
        CheatDialog(self.root, self.emulator)

    def show_plugins(self):
        if os.name != "nt":
            messagebox.showinfo("Plugins", "PJ64/zilmar plugins are Windows-only DLLs.\nUse external cores on other platforms.")
            return
        PluginsDialog(self.root, self.emulator)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def main():
    print(f"=== {WINDOW_TITLE} ===")
    print(f"{EMU_BUILD}")
    print(f"{EMU_COPYRIGHT}")
    print("Starting emulator...\n")
    root = tk.Tk()
    app = EmuDarknessGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
