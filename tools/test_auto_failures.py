"""Exercises build.auto() failure paths in a temp game folder (never touches the real game)."""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

tmp = tempfile.mkdtemp()
build.GAME_DIR = tmp
build.OVERRIDE_CFG = os.path.join(tmp, "override.cfg")
build.DISABLED = os.path.join(tmp, "disabled")
build.WORK = os.path.join(tmp, "work")
build.LOCK_FILE = os.path.join(build.WORK, "build.lock")
build.LAST_FAILURE = os.path.join(build.WORK, "last_failure.txt")
popups = []
build._notify = popups.append
build.game_running = lambda: False

AUTOLOADS = [("GameFeel", "*res://Autoloads/GameFeel.gd")]
PRINTS = {"res://a.gdc": "111"}
mod = build.mod_install_dir()


def fresh_install():
    shutil.rmtree(mod, ignore_errors=True)
    os.makedirs(mod)
    open(os.path.join(mod, "patch-test.pck"), "wb").close()
    build._write_json(os.path.join(mod, "manifest.json"), {"state": build.state_of(PRINTS, AUTOLOADS), "pack": "patch-test.pck"})
    build._write_json(os.path.join(mod, "status.json"), {"ok": True})
    with open(build.OVERRIDE_CFG, "w") as f:
        f.write('[rendering]\nx=1\n\n' + build.override_block(AUTOLOADS))


def status():
    return build._read_json(os.path.join(mod, "status.json"), {})


def request(problem="game updated"):
    build._write_json(os.path.join(mod, "repair_request.json"), {"fingerprints": {"res://a.gdc": "999"}, "problem": problem})


# A. the game cannot be read -> block removed (pure vanilla), failure recorded, one popup only
fresh_install()
request()
build.inspect_game = lambda: (_ for _ in ()).throw(RuntimeError("pack key lost"))
build.auto(interactive=True, from_boot=True)
assert build.OVERRIDE_BEGIN not in build._read_override() and "[rendering]" in build._read_override()
assert status()["ok"] is False and status()["fingerprints"] == {"res://a.gdc": "999"}
assert not os.path.exists(os.path.join(mod, "repair_request.json"))
build.auto(interactive=True)
assert len(popups) == 1, popups
print("A ok: unreadable game -> vanilla, recorded, single popup")

# B. build is current but the loader still reports a problem -> recorded so the boot stops retrying
fresh_install()
request("MercenaryInstance.gd was loaded before the mod")
build.inspect_game = lambda: (None, None, PRINTS, AUTOLOADS)
build.auto(from_boot=True)
assert status()["ok"] is False and "loader inactive" in status()["message"], status()
print("B ok: current build + inactive loader -> recorded as failure")

# C. uninstall is an off switch: auto leaves everything alone
fresh_install()
build.uninstall()
assert os.path.exists(build.DISABLED) and not os.path.isdir(mod)
build.inspect_game = lambda: (_ for _ in ()).throw(AssertionError("auto must not inspect when disabled"))
build.auto()
assert build.OVERRIDE_BEGIN not in build._read_override()
os.remove(build.DISABLED)
print("C ok: uninstall stays uninstalled")

# D. rebuild fails -> previous install kept, block refreshed with the game's CURRENT autoloads, no retry
fresh_install()
new_autoloads = AUTOLOADS + [("NewService", "*res://Scripts/NewService.gd")]
new_prints = {"res://a.gdc": "222"}
build.inspect_game = lambda: (None, None, new_prints, new_autoloads)
calls = []
build.build = lambda: calls.append(1) or (_ for _ in ()).throw(RuntimeError("anchor 'wrap every slot' not found"))
build.auto(interactive=True)
assert 'NewService="*res://Scripts/NewService.gd"' in build._read_override()
assert status()["ok"] is False and os.path.exists(os.path.join(mod, "patch-test.pck"))
build.auto(interactive=True)
assert len(calls) == 1, "a known failure must not be rebuilt on every launch"
assert len(popups) == 2, popups
print("D ok: failed rebuild keeps previous install, refreshes autoloads, no retry loop")

# E. never install under a running game (it reads its mounted pack by offset); self-repair is the
#    one exception, because its game has no pack mounted
fresh_install()
build.game_running = lambda: True
build.inspect_game = lambda: (None, None, {"res://a.gdc": "333"}, AUTOLOADS)
calls.clear()
build.build = lambda: calls.append(1) or (AUTOLOADS, {"res://a.gdc": "333"}, {"features": {}})
build.auto()
assert calls == [], "the launch wrapper must not rebuild while the game runs"
try:
    build.install(AUTOLOADS)
    raise AssertionError("install must refuse while the game runs")
except build.GameRunning:
    pass
build.game_running = lambda: False
print("E ok: nothing is installed under a running game")
shutil.rmtree(tmp, ignore_errors=True)
print("auto failure-path tests passed")
