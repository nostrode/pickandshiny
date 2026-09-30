"""Checks install/uninstall keep the game's own override.cfg settings (Settings.gd writes [rendering])."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

tmp = tempfile.mkdtemp()
build.OVERRIDE_CFG = os.path.join(tmp, "override.cfg")
build.GAME_DIR = tmp
build.DISABLED = os.path.join(tmp, "disabled")  # never touch the real off-switch
os.makedirs(os.path.join(build.DIST, *build.MOD_FOLDER.split("/")), exist_ok=True)
fake_autoloads = [("GameFeel", "*res://Autoloads/GameFeel.gd"), ("Settings", "*res://Scripts/Autoloads/Settings.gd")]
rendering = '[rendering]\n\nrenderer/rendering_method="mobile"\nrendering_device/driver.windows="d3d12"\n'


def read():
    with open(build.OVERRIDE_CFG, encoding="utf-8") as f:
        return f.read()


# 1. game wrote [rendering] first, then the mod installs
with open(build.OVERRIDE_CFG, "w") as f:
    f.write(rendering)
build.install(fake_autoloads)
text = read()
assert text.startswith("[rendering]") and text.count(build.OVERRIDE_BEGIN) == 1 and text.count("[autoload]") == 1, text

# 2. reinstall does not duplicate the block
build.install(fake_autoloads)
assert read().count(build.OVERRIDE_BEGIN) == 1 and read().count("[autoload]") == 1

# 3. uninstall keeps [rendering], removes only the mod block
build.uninstall()
text = read()
assert build.OVERRIDE_BEGIN not in text and "[autoload]" not in text and "renderer/rendering_method" in text, text

# 4. uninstall with nothing else left deletes the file
build.install(fake_autoloads)
with open(build.OVERRIDE_CFG, "w") as f:
    f.write(build.override_block(fake_autoloads))
build.uninstall()
assert not os.path.exists(build.OVERRIDE_CFG)
print("override.cfg merge tests passed")
