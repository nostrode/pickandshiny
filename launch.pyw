"""Steam launch wrapper for Pick & Shiny: keeps the mod in sync with the game, then starts it.

Steam > Eslabong > Properties > Launch Options (running from source; adjust both paths):
    "<python folder>\\pythonw.exe" "<this folder>\\launch.pyw" %command%
The packaged PickAndShiny.exe does the same with:  "...\\PickAndShiny.exe" launch %command%

Before every launch it runs `build.py auto`: about a second when nothing changed; after a
game update it re-decompiles, re-patches, self-tests and installs before the game starts.
Whatever happens, the game is started (without the mod if it could not be updated).
"""
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "auto.log")

if os.path.exists(LOG) and os.path.getsize(LOG) > 2_000_000:
    os.replace(LOG, LOG + ".old")
with open(LOG, "a", encoding="utf-8") as log_file:
    sys.stdout = sys.stderr = log_file
    try:
        sys.path.insert(0, HERE)
        import build

        build.log("launch wrapper: checking the mod")
        build.auto(interactive=True)
    except Exception:  # noqa: BLE001 - never block the game from starting
        traceback.print_exc()
    finally:
        sys.stdout.flush()

game_command = sys.argv[1:]
if game_command:
    sys.exit(subprocess.call(game_command))
