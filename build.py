"""Pick & Shiny - build / self-test / install for Eslabong (personal offline mod).

  python build.py            decompile the current game scripts, apply mod/edits.py, build dist/
  python build.py install    build, install, self-test on the real engine (rolls back on failure)
  python build.py auto       fast check; rebuild + install only if the game (or the mod) changed.
                             Used by launch.pyw (Steam launch option) and by the in-game self-repair.
  python build.py status     print what is installed and why
  python build.py uninstall  remove the mod block from override.cfg and mods/PickAndShiny
"""
import datetime
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

FROZEN = bool(getattr(sys, "frozen", False))  # running as the packaged PickAndShiny.exe
# RES: read-only program files (boot template, GDRE). ROOT: writable home (work files, logs).
RES = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.abspath(__file__))
if not FROZEN:
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    sys.path.insert(0, os.path.join(ROOT, "mod"))
from keyfind import find_key  # noqa: E402
from pck_tool import read_directory, read_file  # noqa: E402
from pck_write import write_pck  # noqa: E402
from project_binary import autoloads  # noqa: E402

import edits  # noqa: E402  (mod/edits.py: the source changes, anchored to the game's code)

BYTECODE = "ebc36a7"  # GDScript bytecode revision GDRE detected for this game (4.5.0-stable)
MOD_VERSION = "1.2.0"
MOD_FOLDER = "mods/PickAndShiny"
BOOT_NAME = "PickShinyBoot"
STEAM_APP_ID = "4560660"
OVERRIDE_BEGIN = "; >>> Pick & Shiny mod loader"
OVERRIDE_END = "; <<< Pick & Shiny mod loader"
MOD_SOURCES = ["build.py", "mod/edits.py", "mod/boot.gd.in", "tools/pck_write.py"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
INSTALLER_ID = "PickAndShiny.exe" if FROZEN else "build.py"
DEFAULT_OPTIONS = {"shiny_denominator": 2, "features": {"player_shiny": True, "slot_picker": True, "champion_trio": True}}
OPTIONS = json.loads(json.dumps(DEFAULT_OPTIONS))
# How the in-game self-repair and the Steam launch option start this program.
REPAIR_COMMAND = []


def configure(home=None, game_dir=None, gdre=None, options=None, repair_command=None):
    """Points the build at a game folder, a writable home and the tools. The defaults are the
    script setup: this folder as home, the game found through Steam."""
    global ROOT, GAME_DIR, GAME_PCK, GAME_EXE, OVERRIDE_CFG, GDRE, OPTIONS, REPAIR_COMMAND
    global DIST, WORK, SELFTEST, KEY_FILE, LOCK_FILE, LAST_GOOD, NEEDS_UPDATE, DISABLED, LAST_FAILURE, VANILLA_SWEEP
    ROOT = home or ROOT
    GAME_DIR = game_dir or GAME_DIR
    GAME_PCK = os.path.join(GAME_DIR, "eslabong.pck")
    GAME_EXE = os.path.join(GAME_DIR, "eslabong.exe")
    OVERRIDE_CFG = os.path.join(GAME_DIR, "override.cfg")
    GDRE = gdre or GDRE
    if options is not None:
        OPTIONS = options
    edits.configure(OPTIONS)
    if repair_command is not None:
        REPAIR_COMMAND = repair_command
    elif not REPAIR_COMMAND:
        REPAIR_COMMAND = [_pythonw(), os.path.join(ROOT, "build.py")]
    DIST = os.path.join(ROOT, "dist")
    WORK = os.path.join(ROOT, "work")
    SELFTEST = os.path.join(ROOT, "selftest")
    KEY_FILE = os.path.join(WORK, "key.txt")
    LOCK_FILE = os.path.join(WORK, "build.lock")
    LAST_GOOD = os.path.join(WORK, "last_good_vanilla")
    NEEDS_UPDATE = os.path.join(ROOT, "needs_update")
    DISABLED = os.path.join(ROOT, "disabled")  # written by `uninstall`; auto and the boot loader respect it
    LAST_FAILURE = os.path.join(WORK, "last_failure.txt")
    VANILLA_SWEEP = os.path.join(WORK, "vanilla_sweep.json")


def _default_game_dir():
    try:
        import steam_locate
        found = steam_locate.find_game_dirs()
        if found:
            return found[0]
    except Exception:  # noqa: BLE001
        pass
    return r"C:\Program Files (x86)\Steam\steamapps\common\Eslabong"


def _default_gdre():
    """PICKSHINY_GDRE, else gdre/gdre_tools.exe next to this script, else the original dev folder."""
    candidates = [os.environ.get("PICKSHINY_GDRE", ""),
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "gdre", "gdre_tools.exe"),
                  r"C:\Modding\GDRE Tools\gdre_tools.exe"]
    return next((c for c in candidates if c and os.path.exists(c)), candidates[1])


GAME_DIR = os.environ.get("PICKSHINY_GAME_DIR") or _default_game_dir()
GDRE = _default_gdre()


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def mod_install_dir():
    return os.path.join(GAME_DIR, *MOD_FOLDER.split("/"))


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------- game inspection

def resolve_key():
    """Stored key, else recover it from the exe (the developer may rotate it in an update)."""
    # No key ships with the mod: it is recovered from the player's own eslabong.exe and cached.
    candidates = []
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            candidates.append(f.read().strip())
    for key_hex in candidates:
        try:
            key = bytes.fromhex(key_hex)
            return key, read_directory(GAME_PCK, key)[1]
        except ValueError:
            continue
    log("stored pack key no longer works - recovering it from eslabong.exe")
    key = find_key(GAME_EXE, GAME_PCK, log=log)
    if key is None:
        raise RuntimeError("could not recover the pack encryption key from eslabong.exe")
    os.makedirs(WORK, exist_ok=True)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.hex().upper())
    return key, read_directory(GAME_PCK, key)[1]


def inspect_game():
    key, entries = resolve_key()
    by_path = {e[0]: e for e in entries}
    fingerprints = {}
    for res_path in edits.TARGETS:
        gdc = res_path[:-3] + ".gdc"
        if gdc not in by_path:
            raise RuntimeError(f"{gdc} no longer exists in the game - the mod needs an update")
        fingerprints["res://" + gdc] = hashlib.md5(read_file(GAME_PCK, key, by_path[gdc])).hexdigest()
    game_autoloads = autoloads(read_file(GAME_PCK, key, by_path["project.binary"]))
    return key, by_path, fingerprints, game_autoloads


def mod_hash():
    """Changes whenever the mod itself or the chosen options change (triggers a rebuild)."""
    h = hashlib.sha256(MOD_VERSION.encode())
    h.update(json.dumps(OPTIONS, sort_keys=True).encode())
    sources = ["mod/boot.gd.in"] if FROZEN else MOD_SOURCES
    for rel in sources:
        with open(os.path.join(RES, *rel.split("/")), "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def state_of(fingerprints, game_autoloads):
    blob = json.dumps({"f": fingerprints, "a": game_autoloads, "m": mod_hash()}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- build

def decompile_targets(key, by_path):
    """Decompiles just the scripts we patch; falls back to GDRE's bytecode auto-detection."""
    gdc_dir = os.path.join(WORK, "gdc")
    out_dir = os.path.join(WORK, "decompiled")
    for d in (gdc_dir, out_dir):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(gdc_dir)
    args = [GDRE, "--headless", "--bytecode=" + BYTECODE, f"--output={out_dir}"]
    for res_path in edits.TARGETS:
        gdc_file = os.path.join(gdc_dir, os.path.basename(res_path)[:-3] + ".gdc")
        with open(gdc_file, "wb") as f:
            f.write(read_file(GAME_PCK, key, by_path[res_path[:-3] + ".gdc"]))
        args.append("--decompile=" + gdc_file)
    subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    wanted = {p: os.path.join(out_dir, os.path.basename(p)) for p in edits.TARGETS}
    if not all(os.path.exists(p) and os.path.getsize(p) > 0 for p in wanted.values()):
        log(f"decompile with bytecode {BYTECODE} failed - using GDRE auto-detect (full script recovery)")
        full = os.path.join(WORK, "full_recovery")
        shutil.rmtree(full, ignore_errors=True)
        subprocess.run([GDRE, "--headless", f"--recover={GAME_PCK}", f"--key={key.hex().upper()}",
                        "--scripts-only", f"--output={full}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        wanted = {p: os.path.join(full, *p.split("/")) for p in edits.TARGETS}
    sources = {}
    for res_path, path in wanted.items():
        if not os.path.exists(path):
            raise RuntimeError(f"GDRE could not decompile {res_path} (new engine version? update GDRE Tools)")
        with open(path, encoding="utf-8") as f:
            sources[res_path] = f.read()
    return sources


def _record_vanilla(sources, report):
    """Keeps the last vanilla sources that patched cleanly; on breakage writes a diff to fix from."""
    broken = [f for f in report["features"].values()
              if (not f["active"] and not f.get("optional_off")) or f.get("skipped")]
    if not broken:
        shutil.rmtree(LAST_GOOD, ignore_errors=True)
        for res_path, text in sources.items():
            dest = os.path.join(LAST_GOOD, *res_path.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        shutil.rmtree(NEEDS_UPDATE, ignore_errors=True)
        return
    os.makedirs(NEEDS_UPDATE, exist_ok=True)
    diff_lines = []
    for res_path, text in sources.items():
        old_path = os.path.join(LAST_GOOD, *res_path.split("/"))
        if os.path.exists(old_path):
            with open(old_path, encoding="utf-8") as f:
                old = f.read()
            diff_lines += difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                               "last_good/" + res_path, "current/" + res_path)
        with open(os.path.join(NEEDS_UPDATE, os.path.basename(res_path)), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    with open(os.path.join(NEEDS_UPDATE, "changes.diff"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(diff_lines)
    _write_json(os.path.join(NEEDS_UPDATE, "report.json"), report)


def override_block(game_autoloads):
    """Boot loader first, then every game autoload erased + re-added so it loads after it, same order."""
    boot_path = mod_install_dir().replace("\\", "/") + "/boot.gd"
    lines = [OVERRIDE_BEGIN + " (turn the mod off with Pick & Shiny > Uninstall)", "[autoload]", ""]
    lines.append(f'{BOOT_NAME}="{boot_path}"')
    for name, path in game_autoloads:
        lines.append(f"{name}=null")
        lines.append(f'{name}="{path}"')
    lines.append(OVERRIDE_END)
    return "\n".join(lines) + "\n"


def compile_scripts(patched):
    """GDScript text -> binary tokens (.gdc) with GDRE, for the game's bytecode revision."""
    src_dir = os.path.join(WORK, "compile_src")
    out_dir = os.path.join(WORK, "compiled")
    for d in (src_dir, out_dir):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(src_dir)
    args = [GDRE, "--headless", "--bytecode=" + BYTECODE, f"--output={out_dir}"]
    for res_path, text in patched.items():
        src = os.path.join(src_dir, os.path.basename(res_path))
        with open(src, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        args.append("--compile=" + src)
    subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    compiled = {}
    for res_path in patched:
        gdc = os.path.join(out_dir, os.path.basename(res_path)[:-3] + ".gdc")
        if not os.path.exists(gdc) or os.path.getsize(gdc) < 16:
            raise RuntimeError(f"GDRE could not compile the patched {res_path}")
        with open(gdc, "rb") as f:
            data = f.read()
        if data[:4] != b"GDSC":
            raise RuntimeError(f"GDRE produced an invalid .gdc for {res_path}")
        compiled[res_path] = data
    return compiled


def _pythonw():
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def build():
    key, by_path, fingerprints, game_autoloads = inspect_game()
    sources = decompile_targets(key, by_path)
    patched, report = edits.apply_all(sources)
    _record_vanilla(sources, report)
    for fid, info in report["features"].items():
        if info["active"]:
            log(f"feature {fid}: ON" + (f" (skipped: {'; '.join(info['skipped'])})" if info["skipped"] else ""))
        else:
            log(f"feature {fid}: OFF - {info['error']}")
    if not patched:
        raise RuntimeError("no feature could be applied to this game version - see needs_update/")

    shutil.rmtree(DIST, ignore_errors=True)
    mod_dir = os.path.join(DIST, *MOD_FOLDER.split("/"))
    os.makedirs(mod_dir)
    src_dump = os.path.join(WORK, "patched")
    shutil.rmtree(src_dump, ignore_errors=True)
    for res_path, text in patched.items():
        dump = os.path.join(src_dump, *res_path.split("/"))
        os.makedirs(os.path.dirname(dump), exist_ok=True)
        with open(dump, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    # Ship the patched scripts in the game's own binary token format (.gdc) under the ORIGINAL
    # .gdc paths: the engine loads them exactly like vanilla scripts (the vanilla .remap files
    # already point there). Text scripts behind self-pointing remaps broke the CampaignService
    # autoload (2026-09-26), so no text or remap files are shipped any more.
    compiled = compile_scripts(patched)
    pck_files = [(res_path[:-3] + ".gdc", data) for res_path, data in compiled.items()]
    # A running game reads its mounted pack by file offsets, so a pack must never change under
    # it (that corrupted a session on 2026-09-26). Every build gets its own pack file name.
    digest = hashlib.sha256(b"".join(p.encode() + d for p, d in pck_files)).hexdigest()[:10]
    pack_name = f"patch-{digest}.pck"
    write_pck(os.path.join(mod_dir, pack_name), pck_files)

    shiny = report["features"].get("player_shiny", {})
    recruit_odds = shiny.get("active", False) and "recruit odds (market/scouting/rewards)" in shiny.get("applied", [])
    patched_originals = {k: v for k, v in fingerprints.items() if k[len("res://"):-4] + ".gd" in patched}
    with open(os.path.join(RES, "mod", "boot.gd.in"), encoding="utf-8") as f:  # program files, not ROOT
        boot = f.read()
    replacements = {
        "@MOD_VERSION@": MOD_VERSION,
        "@EXPECTED_ORIGINALS@": json.dumps(patched_originals, indent="\t"),
        "@SELFTEST_CONFIG@": edits.SELFTEST_CONFIG,
        "@SELFTEST_METHODS@": json.dumps(edits.selftest_methods(report)),
        "@SELFTEST_EXPECT@": json.dumps({"player_shiny": shiny.get("active", False), "recruit_odds": recruit_odds,
                                         "player_denominator": edits.PLAYER_SHINY_DENOMINATOR,
                                         "champion_trio": "champion_trio" in report["active"],
                                         "champions": edits.SELFTEST_CHAMPIONS}),
        "@OVERRIDE_BEGIN@": OVERRIDE_BEGIN,
        "@OVERRIDE_BLOCK@": json.dumps(override_block(game_autoloads)),
        "@REPAIR_COMMAND@": json.dumps([p.replace("\\", "/") for p in REPAIR_COMMAND]),
        "@MOD_HOME@": ROOT.replace("\\", "/"),
        "@PATCH_FILE@": pack_name,
    }
    for token, value in replacements.items():
        boot = boot.replace(token, value)
    leftover = [token for token in replacements if token in boot]
    if leftover:
        raise RuntimeError(f"unreplaced template tokens in boot.gd: {leftover}")
    with open(os.path.join(mod_dir, "boot.gd"), "w", encoding="utf-8", newline="\n") as f:
        f.write(boot)
    _write_json(os.path.join(mod_dir, "manifest.json"), {
        "mod_version": MOD_VERSION, "state": state_of(fingerprints, game_autoloads), "pack": pack_name,
        "built_by": INSTALLER_ID, "options": OPTIONS,
        "fingerprints": fingerprints, "features": report["features"],
        "built": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    return game_autoloads, fingerprints, report


# ---------------------------------------------------------------- install / self-test

def _strip_mod_block(text):
    begin = text.find(OVERRIDE_BEGIN)
    if begin < 0:
        return text
    end = text.find(OVERRIDE_END, begin)
    end = len(text) if end < 0 else end + len(OVERRIDE_END)
    return (text[:begin].rstrip() + "\n" + text[end:].lstrip()).strip()


def _read_override():
    if not os.path.exists(OVERRIDE_CFG):
        return ""
    with open(OVERRIDE_CFG, encoding="utf-8", errors="replace") as f:
        return f.read()


def ensure_override_block(block):
    current = _read_override()
    if OVERRIDE_BEGIN in current and block in current:
        return False
    rest = _strip_mod_block(current)
    with open(OVERRIDE_CFG, "w", encoding="utf-8", newline="\n") as f:
        f.write((rest + "\n\n" if rest else "") + block)
    return True


def game_running():
    """True if eslabong.exe is running (Windows process snapshot, no external commands)."""
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if snapshot in (None, wintypes.HANDLE(-1).value):
            return False
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        found = False
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == os.path.basename(GAME_EXE).lower():
                found = True
                break
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        kernel32.CloseHandle(snapshot)
        return found
    except Exception:  # noqa: BLE001 - not on Windows / API unavailable
        return False


class GameRunning(RuntimeError):
    pass


def install(game_autoloads, allow_running=False):
    """Adds the new build next to the old one: boot.gd names its own pack, so a running game keeps
    reading the pack it mounted. Stale packs are removed only while the game is closed (and by
    the boot loader at the next start)."""
    running = game_running()
    if running and not allow_running:
        raise GameRunning("Eslabong is running - close the game first, then install again")
    target = mod_install_dir()
    os.makedirs(target, exist_ok=True)
    source = os.path.join(DIST, *MOD_FOLDER.split("/"))
    for name in os.listdir(source):
        shutil.copy2(os.path.join(source, name), os.path.join(target, name))
    current_pack = _read_json(os.path.join(source, "manifest.json"), {}).get("pack", "")
    if not running:
        for name in os.listdir(target):
            if name.startswith("patch") and name.endswith(".pck") and name != current_pack:
                os.remove(os.path.join(target, name))
    ensure_override_block(override_block(game_autoloads))
    log(f"installed to {GAME_DIR}")


def strip_override_block():
    remaining = _strip_mod_block(_read_override())
    if remaining:
        with open(OVERRIDE_CFG, "w", encoding="utf-8", newline="\n") as f:
            f.write(remaining + "\n")
    elif os.path.exists(OVERRIDE_CFG):
        os.remove(OVERRIDE_CFG)


def remove_install():
    strip_override_block()
    shutil.rmtree(mod_install_dir(), ignore_errors=True)


def uninstall():
    """Turns the mod off for good: launch.pyw and the in-game self-repair leave it off until
    `build.py install` is run again."""
    if game_running():
        raise GameRunning("Eslabong is running - close the game first, then uninstall again")
    with open(DISABLED, "w", encoding="utf-8") as f:
        f.write("Pick & Shiny turned off by build.py uninstall. Run build.py install to turn it back on.\n")
    remove_install()
    log("uninstalled - the mod stays off until you run: python build.py install")


def _run_engine(user_arg):
    """Runs the real game engine headless with the installed boot loader. It does its work inside
    its _init() and kills the process before any game autoload (Steam, saves) runs. Godot 4.6
    release builds refuse --main-pack, so this runs from the game folder itself."""
    os.makedirs(SELFTEST, exist_ok=True)
    report = os.path.join(mod_install_dir(), "boot.log")
    engine_log = os.path.join(SELFTEST, "engine.log")
    for stale in (report, engine_log):
        if os.path.exists(stale):
            os.remove(stale)
    env = dict(os.environ, SteamAppId=STEAM_APP_ID, SteamGameId=STEAM_APP_ID)  # safety net if boot never runs
    try:
        subprocess.run([GAME_EXE, "--headless", "--log-file", engine_log, "--", user_arg],
                       cwd=GAME_DIR, env=env, timeout=900, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        log("engine did not exit in time (boot loader probably not reached)")
    text = ""
    if os.path.exists(report):
        with open(report, encoding="utf-8") as f:
            text = f.read()
        os.remove(report)
    return text


def _sweep_failures(text):
    return sorted(line[len("SWEEP-FAIL "):] for line in text.splitlines() if line.startswith("SWEEP-FAIL "))


def vanilla_sweep_baseline():
    """Scripts that already fail to compile in the unmodified game (cached per game version)."""
    key = f"{os.path.getsize(GAME_PCK)}-{int(os.path.getmtime(GAME_PCK))}"
    cache = _read_json(VANILLA_SWEEP, {})
    if cache.get("key") == key:
        return cache["failed"]
    log("compiling every game script without the mod (baseline for this game version)...")
    text = _run_engine("--pickshiny-vanilla-sweep")
    if "SWEEP compiled" not in text:
        raise RuntimeError("the vanilla compile sweep did not run")
    failed = _sweep_failures(text)
    log(next(line for line in text.splitlines() if line.startswith("SWEEP compiled")) + " (vanilla)")
    _write_json(VANILLA_SWEEP, {"key": key, "failed": failed})
    return failed


def run_selftest():
    """Patched-script checks (compile, shiny odds, champion trio) plus a compile of EVERY game
    script with the mod mounted; any script that fails only with the mod fails the self-test."""
    baseline = set(vanilla_sweep_baseline())
    text = _run_engine("--pickshiny-selftest")
    log("\n".join(line for line in text.strip().splitlines() if not line.startswith("SWEEP-FAIL "))
        or "no boot.log written - override.cfg was not honoured or boot.gd failed to compile")
    if "SWEEP compiled" not in text:
        log("the full compile sweep did not finish")
        return False
    broken = [path for path in _sweep_failures(text) if path not in baseline]
    for path in broken:
        log("breaks only with the mod: " + path)
    return "SELFTEST RESULT PASS" in text and not broken


def install_with_selftest(game_autoloads, allow_running=False):
    """Installs the new build; if the self-test fails, puts the previous install back (which then
    shows an in-game 'mod is off' notice) or uninstalls if there was none.
    allow_running is only used by the in-game self-repair, whose game has no pack mounted."""
    if game_running() and not allow_running:
        raise GameRunning("Eslabong is running - close the game first, then install again")
    backup_dir = os.path.join(WORK, "previous_install")
    shutil.rmtree(backup_dir, ignore_errors=True)
    had_previous = os.path.isdir(mod_install_dir())
    previous_override = _read_override()
    if had_previous:
        shutil.copytree(mod_install_dir(), backup_dir)
    install(game_autoloads, allow_running=allow_running)
    if run_selftest():
        log("SELFTEST PASSED")
        return True
    log("SELFTEST FAILED - rolling back")
    if had_previous:
        shutil.rmtree(mod_install_dir(), ignore_errors=True)
        shutil.copytree(backup_dir, mod_install_dir())
        # the previous loader stays inactive (fingerprints), but the block must list the game's
        # CURRENT autoloads so none is lost or loaded from a stale path
        with open(OVERRIDE_CFG, "w", encoding="utf-8", newline="\n") as f:
            f.write(_strip_mod_block(previous_override))
        ensure_override_block(override_block(game_autoloads))
    else:
        remove_install()
    return False


# ---------------------------------------------------------------- auto (launch wrapper / self-repair)

class BuildLock:
    def __enter__(self):
        os.makedirs(WORK, exist_ok=True)
        if os.path.exists(LOCK_FILE) and time.time() - os.path.getmtime(LOCK_FILE) > 900:
            os.remove(LOCK_FILE)  # stale lock from a crashed build
        try:
            self.fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            self.fd = None
        return self.fd is not None

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            os.remove(LOCK_FILE)


def _set_status(ok, message, fingerprints, state, features=None):
    _write_json(os.path.join(mod_install_dir(), "status.json"), {
        "ok": ok, "message": message, "fingerprints": fingerprints, "state": state,
        "features": features or {}, "time": datetime.datetime.now().isoformat(timespec="seconds"),
    })


def _notify(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Pick & Shiny mod", 0x40 | 0x10000)
    except Exception:  # noqa: BLE001 - notification is best effort
        pass


def _notify_once(message, interactive):
    """Pops a message only the first time a given problem is seen (not on every launch)."""
    previous = ""
    if os.path.exists(LAST_FAILURE):
        with open(LAST_FAILURE, encoding="utf-8") as f:
            previous = f.read()
    os.makedirs(WORK, exist_ok=True)
    with open(LAST_FAILURE, "w", encoding="utf-8") as f:
        f.write(message)
    if interactive and message != previous:
        _notify(message)


def _fail(reason, fingerprints, state, interactive):
    message = f"Pick & Shiny could not update itself for this game version: {reason}"
    log(message)
    if os.path.isdir(mod_install_dir()):
        _set_status(False, reason, fingerprints, state)
    _notify_once(message + "\n\nThe game starts without the mod. Details: " + os.path.join(ROOT, "auto.log"), interactive)


def auto(interactive=False, from_boot=False):
    with BuildLock() as got_lock:
        if not got_lock:
            log("another build is running - skipping")
            return
        if os.path.exists(DISABLED):
            log("mod is turned off (build.py uninstall) - leaving the game alone")
            return
        request_file = os.path.join(mod_install_dir(), "repair_request.json")
        request = _read_json(request_file, {}) if from_boot else {}
        if os.path.exists(request_file):
            os.remove(request_file)
        try:
            _, _, fingerprints, game_autoloads = inspect_game()
        except Exception as exc:  # noqa: BLE001
            # The autoload list is unknown, so no correct block can be written: run pure vanilla.
            strip_override_block()
            _fail(f"cannot read this game version ({exc})", request.get("fingerprints", {}), None, interactive)
            return
        state = state_of(fingerprints, game_autoloads)
        manifest = _read_json(os.path.join(mod_install_dir(), "manifest.json"), {})
        if manifest.get("built_by", INSTALLER_ID) != INSTALLER_ID:
            # Installed by the other setup (PickAndShiny.exe vs the Python scripts): rebuilding here
            # would make the two undo each other on every launch.
            log(f"the mod in this game is managed by {manifest['built_by']} - leaving it alone")
            return
        status = _read_json(os.path.join(mod_install_dir(), "status.json"), {})
        installed_pack = os.path.join(mod_install_dir(), str(manifest.get("pack", "patch.pck")))
        if manifest.get("state") == state and os.path.exists(installed_pack):
            if ensure_override_block(override_block(game_autoloads)):
                log("re-added the mod block to override.cfg (the game had rewritten it)")
            if request:
                # The build matches this game version, yet the loader reported a problem it cannot
                # fix (e.g. a game script loads a patched file before the mod): stop retrying.
                _fail("loader inactive although the build is current: " + str(request.get("problem", "")),
                      request.get("fingerprints", {}), state, interactive)
                return
            log("up to date")
            return
        if status.get("state") == state and not status.get("ok", True):
            ensure_override_block(override_block(game_autoloads))  # keep the game's current autoloads
            log("this game version already failed to patch - skipping (see needs_update/)")
            return
        if not from_boot and game_running():
            log("Eslabong is running - the mod will update at the next launch")
            return
        log("game or mod changed - rebuilding")
        try:
            game_autoloads, fingerprints, report = build()
            if not install_with_selftest(game_autoloads, allow_running=from_boot):
                raise RuntimeError("the self-test on the game engine failed (see auto.log)")
        except GameRunning as exc:
            log(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - reported to the user, previous install kept
            if os.path.isdir(mod_install_dir()):
                ensure_override_block(override_block(game_autoloads))
            _fail(str(exc), fingerprints, state, interactive)
            return
        off = [info["title"] for info in report["features"].values()
               if not info["active"] and not info.get("optional_off")]
        _set_status(True, "partial: " + ", ".join(off) + " unavailable" if off else "ok", fingerprints, state, report["features"])
        if off:
            _notify_once("Pick & Shiny updated for the new game version, but these parts no longer fit the game's "
                         "code and are off for now:\n- " + "\n- ".join(off), interactive)
        log("rebuilt and installed")


def full_install():
    """Build + install + self-test (the `install` command and the installer's Install button).
    Returns the feature report; raises with a readable message on failure."""
    if game_running():
        raise GameRunning("Eslabong is running - close the game first, then install again")
    autoload_list, prints, report = build()
    with BuildLock() as locked:
        if not locked:
            raise RuntimeError("another install or update is already running - try again in a minute")
        if os.path.exists(DISABLED):
            os.remove(DISABLED)
        if not install_with_selftest(autoload_list):
            raise RuntimeError("the self-test on the game engine failed, so nothing was changed (details in the log)")
        _set_status(True, "ok", prints, state_of(prints, autoload_list), report["features"])
    log("mod installed - start Eslabong from Steam as usual")
    return report


def print_status():
    manifest = _read_json(os.path.join(mod_install_dir(), "manifest.json"), {})
    status = _read_json(os.path.join(mod_install_dir(), "status.json"), {})
    print(json.dumps({"disabled": os.path.exists(DISABLED), "installed": manifest, "last_auto": status}, indent=2))


configure()


if __name__ == "__main__":
    if sys.stdout is None:  # started by pythonw (from the game's self-repair): keep a trace
        sys.stdout = sys.stderr = open(os.path.join(ROOT, "auto.log"), "a", encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd in ("install", "uninstall") and game_running():
        sys.exit("Eslabong is running - close the game first (installing under a running game corrupts it)")
    if cmd == "uninstall":
        uninstall()
    elif cmd == "status":
        print_status()
    elif cmd == "auto":
        try:
            auto(interactive="--interactive" in sys.argv, from_boot="--from-boot" in sys.argv)
        except Exception:  # noqa: BLE001 - leave a trace for pythonw runs
            import traceback
            traceback.print_exc()
            raise
    elif cmd == "install":
        try:
            full_install()
        except Exception as exc:  # noqa: BLE001
            sys.exit(str(exc))
    else:
        build()


