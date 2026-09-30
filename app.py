"""Pick & Shiny - installer/updater for the Eslabong mod (PickAndShiny.exe).

No arguments: opens the installer window.
  PickAndShiny.exe launch <game command...>   Steam launch option: update the mod, then start the game
  PickAndShiny.exe auto [--from-boot]         update check (used by the in-game self-repair)
  PickAndShiny.exe install | uninstall | status
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import traceback

FROZEN = bool(getattr(sys, "frozen", False))
APP_NAME = "PickAndShiny"
EXE_NAME = APP_NAME + ".exe"
PROGRAM_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
HOME = os.environ.get("PICKSHINY_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
INSTALLED_APP = os.path.join(HOME, "app")
CONFIG = os.path.join(HOME, "config.json")
LOG_FILE = os.path.join(HOME, "auto.log")
import build  # noqa: E402
import steam_locate  # noqa: E402

DEV_GDRE = build._default_gdre()  # running from source: PICKSHINY_GDRE or ./gdre


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    options = json.loads(json.dumps(build.DEFAULT_OPTIONS))
    options.update({k: v for k, v in cfg.get("options", {}).items() if k != "features"})
    options["features"].update(cfg.get("options", {}).get("features", {}))
    cfg["options"] = options
    return cfg


def save_config(cfg):
    os.makedirs(HOME, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def installed_command():
    """How the game and Steam start this program after installation."""
    if FROZEN:
        return [os.path.join(INSTALLED_APP, EXE_NAME)]
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return [pythonw if os.path.exists(pythonw) else sys.executable, os.path.abspath(__file__)]


def launch_option_text():
    command = installed_command()
    return " ".join(f'"{part}"' for part in command) + " launch %command%"


def gdre_path():
    for base in (INSTALLED_APP, PROGRAM_DIR):
        candidate = os.path.join(base, "gdre", "gdre_tools.exe")
        if os.path.exists(candidate):
            return candidate
    return DEV_GDRE


def setup_build(cfg):
    game_dir = cfg.get("game_dir", "")
    if not steam_locate.is_game_dir(game_dir):
        raise RuntimeError("Eslabong was not found - choose the game folder (the one with eslabong.exe)")
    build.configure(home=HOME, game_dir=game_dir, gdre=gdre_path(), options=cfg["options"],
                    repair_command=installed_command())


def ensure_installed_copy():
    """Copies the program to %LOCALAPPDATA%\\PickAndShiny\\app, so the game's self-repair and
    the Steam launch option keep working after the downloaded folder is deleted."""
    if not FROZEN or os.path.normcase(PROGRAM_DIR) == os.path.normcase(INSTALLED_APP):
        return
    os.makedirs(INSTALLED_APP, exist_ok=True)
    shutil.copytree(PROGRAM_DIR, INSTALLED_APP, dirs_exist_ok=True)
    build.log(f"program copied to {INSTALLED_APP}")


def installed_state(cfg):
    game_dir = cfg.get("game_dir", "")
    mod_dir = os.path.join(game_dir, *build.MOD_FOLDER.split("/"))
    manifest = build._read_json(os.path.join(mod_dir, "manifest.json"), {})
    status = build._read_json(os.path.join(mod_dir, "status.json"), {})
    return manifest, status


# ---------------------------------------------------------------- command line (Steam, game)

def _log_to_file():
    os.makedirs(HOME, exist_ok=True)
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 2_000_000:
        os.replace(LOG_FILE, LOG_FILE + ".old")
    handle = open(LOG_FILE, "a", encoding="utf-8")
    sys.stdout = sys.stderr = handle


def run_cli(args):
    if sys.stdout is None or args[0] in ("launch", "auto"):
        _log_to_file()
    cfg = load_config()
    command = args[0]
    if command == "launch":
        game_command = args[1:]
        if not cfg.get("game_dir") and game_command:
            cfg["game_dir"] = os.path.dirname(game_command[0])
        try:
            build.log("launch: checking the mod")
            setup_build(cfg)
            build.auto(interactive=True)
        except Exception:  # noqa: BLE001 - the game must start no matter what
            traceback.print_exc()
        sys.stdout.flush()
        if game_command:
            sys.exit(subprocess.call(game_command))
        return
    setup_build(cfg)
    if command == "auto":
        build.auto(interactive=False, from_boot="--from-boot" in args)
    elif command == "install":
        ensure_installed_copy()
        build.full_install()
    elif command == "uninstall":
        build.uninstall()
    elif command == "status":
        manifest, status = installed_state(cfg)
        print(json.dumps({"config": cfg, "installed": manifest, "last_update": status}, indent=2))
    else:
        raise SystemExit(__doc__)


# ---------------------------------------------------------------- installer window

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass

    cfg = load_config()
    if not steam_locate.is_game_dir(cfg.get("game_dir", "")):
        found = steam_locate.find_game_dirs()
        cfg["game_dir"] = found[0] if found else ""

    root = tk.Tk()
    root.title("Pick & Shiny - Eslabong mod")
    root.minsize(640, 560)
    pad = {"padx": 10, "pady": 4}
    lines = queue.Queue()

    class QueueWriter:
        def write(self, text):
            lines.put(text)

        def flush(self):
            pass

    game_var = tk.StringVar(value=cfg.get("game_dir", ""))
    shiny_on = tk.BooleanVar(value=cfg["options"]["features"].get("player_shiny", True))
    shiny_den = tk.StringVar(value=str(cfg["options"].get("shiny_denominator", 2)))
    picker_on = tk.BooleanVar(value=cfg["options"]["features"].get("slot_picker", True))
    trio_on = tk.BooleanVar(value=cfg["options"]["features"].get("champion_trio", True))
    status_var = tk.StringVar()

    game_box = ttk.LabelFrame(root, text="Game folder")
    game_box.pack(fill="x", **pad)
    ttk.Entry(game_box, textvariable=game_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)

    def browse():
        chosen = filedialog.askdirectory(title="Choose the Eslabong folder (with eslabong.exe)")
        if chosen:
            game_var.set(os.path.normpath(chosen))
            refresh_status()

    ttk.Button(game_box, text="Browse...", command=browse).pack(side="left", padx=6)

    options_box = ttk.LabelFrame(root, text="Options")
    options_box.pack(fill="x", **pad)
    shiny_row = ttk.Frame(options_box)
    shiny_row.pack(fill="x", padx=6, pady=3)
    ttk.Checkbutton(shiny_row, text="Shiny chance for your own fighters: 1 in", variable=shiny_on,
                    command=lambda: update_option_states()).pack(side="left")
    shiny_spin = ttk.Spinbox(shiny_row, from_=1, to=5000, width=6, textvariable=shiny_den)
    shiny_spin.pack(side="left", padx=4)
    ttk.Label(shiny_row, text="(AI teams keep the normal 1 in 5000)").pack(side="left")
    ttk.Checkbutton(options_box, variable=picker_on, command=lambda: update_option_states(),
                    text="Starter picker: \u25c0 Reroll \u25b6 under every starting fighter (Random and Champion Mode)"
                    ).pack(anchor="w", padx=6, pady=3)
    trio_check = ttk.Checkbutton(options_box, variable=trio_on,
                                 text="Champion Mode starts with 3 champions (needs the starter picker)")
    trio_check.pack(anchor="w", padx=6, pady=3)

    def update_option_states():
        shiny_spin.configure(state="normal" if shiny_on.get() else "disabled")
        trio_check.configure(state="normal" if picker_on.get() else "disabled")

    update_option_states()

    buttons = ttk.Frame(root)
    buttons.pack(fill="x", **pad)
    install_button = ttk.Button(buttons, text="Install / Update")
    uninstall_button = ttk.Button(buttons, text="Uninstall")
    install_button.pack(side="left", padx=(0, 6))
    uninstall_button.pack(side="left")
    ttk.Button(buttons, text="Open log folder", command=lambda: os.startfile(HOME) if os.path.isdir(HOME) else None
               ).pack(side="right")
    ttk.Label(root, textvariable=status_var, wraplength=600, justify="left").pack(fill="x", **pad)

    log_box = ScrolledText(root, height=12, state="disabled", font=("Consolas", 9))
    log_box.pack(fill="both", expand=True, **pad)

    steam_box = ttk.LabelFrame(root, text="Optional: Steam launch option (updates the mod before the game starts)")
    steam_box.pack(fill="x", **pad)
    launch_var = tk.StringVar(value=launch_option_text())
    ttk.Entry(steam_box, textvariable=launch_var, state="readonly").pack(side="left", fill="x", expand=True, padx=6, pady=6)

    def copy_launch_option():
        root.clipboard_clear()
        root.clipboard_append(launch_var.get())
        status_var.set("Copied. In Steam: right-click Eslabong > Properties > General > Launch Options, paste.")

    ttk.Button(steam_box, text="Copy", command=copy_launch_option).pack(side="left", padx=6)
    ttk.Label(root, foreground="#666", wraplength=600, justify="left",
              text="Without the launch option the mod still repairs itself after a game update: the first start "
                   "after an update shows a note, then restart the game once. For offline single-player - please "
                   "don't take modded teams into online modes.").pack(fill="x", **pad)

    def append_log(text):
        log_box.configure(state="normal")
        log_box.insert("end", text)
        log_box.see("end")
        log_box.configure(state="disabled")

    def pump():
        try:
            while True:
                append_log(lines.get_nowait())
        except queue.Empty:
            pass
        root.after(100, pump)

    def current_cfg():
        try:
            denominator = max(1, min(5000, int(shiny_den.get())))
        except ValueError:
            denominator = 2
        return {"game_dir": game_var.get().strip(),
                "options": {"shiny_denominator": denominator,
                            "features": {"player_shiny": shiny_on.get(), "slot_picker": picker_on.get(),
                                         "champion_trio": trio_on.get() and picker_on.get()}}}

    def refresh_status():
        chosen = current_cfg()
        if not steam_locate.is_game_dir(chosen["game_dir"]):
            status_var.set("Choose the Eslabong game folder (the folder that contains eslabong.exe).")
            return
        manifest, last = installed_state(chosen)
        if not manifest:
            status_var.set("Eslabong found. The mod is not installed yet.")
            return
        on = [info["title"] for info in manifest.get("features", {}).values() if info.get("active")]
        text = f"Installed (version {manifest.get('mod_version', '?')}, built {manifest.get('built', '?')}): " + (", ".join(on) or "no features")
        if last and not last.get("ok", True):
            text += f"\nLast update problem: {last.get('message', '')}"
        status_var.set(text)

    def run_task(label, task, done_message):
        chosen = current_cfg()
        if not steam_locate.is_game_dir(chosen["game_dir"]):
            messagebox.showerror("Pick & Shiny", "Choose the Eslabong game folder first (it contains eslabong.exe).")
            return
        if build.game_running():
            messagebox.showwarning("Pick & Shiny", "Eslabong is running. Close the game first, then try again.")
            return
        save_config(chosen)
        install_button.configure(state="disabled")
        uninstall_button.configure(state="disabled")
        status_var.set(label + " - this takes about a minute (the game is started invisibly to test the mod)...")
        writer = QueueWriter()

        def worker():
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = writer
            error = None
            try:
                setup_build(chosen)
                task()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                error = str(exc)
                traceback.print_exc()
            finally:
                sys.stdout, sys.stderr = old_out, old_err
            root.after(0, lambda: finish(error))

        def finish(error):
            install_button.configure(state="normal")
            uninstall_button.configure(state="normal")
            refresh_status()
            if error:
                messagebox.showerror("Pick & Shiny", error)
            else:
                messagebox.showinfo("Pick & Shiny", done_message)

        threading.Thread(target=worker, daemon=True).start()

    def install():
        def task():
            ensure_installed_copy()
            report = build.full_install()
            off = [f"{info['title']}: {info['error']}" for info in report["features"].values()
                   if not info["active"] and not info.get("optional_off")]
            for line in off:
                build.log("not available for this game version - " + line)
        run_task("Installing", task, "Pick & Shiny is installed. Start Eslabong from Steam as usual.")

    def uninstall():
        if not messagebox.askyesno("Pick & Shiny", "Remove the mod from Eslabong?\n\nYour saves are not touched. "
                                   "If you set the Steam launch option you can leave it (it just starts the game) "
                                   "or remove it in Steam."):
            return
        run_task("Removing", build.uninstall, "The mod is removed. Eslabong is back to normal.")

    install_button.configure(command=install)
    uninstall_button.configure(command=uninstall)
    game_var.trace_add("write", lambda *_: refresh_status())
    refresh_status()
    pump()
    root.mainloop()


def main():
    args = sys.argv[1:]
    if not args:
        run_gui()
        return
    try:
        run_cli(args)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - windowed exe: leave a trace
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
