"""Builds the shareable installer: installer/PickAndShiny-<version>.zip

  python installer/make_installer.py

Contents: PickAndShiny.exe (+ its Python runtime), GDRE Tools, README and license notices.
No game files and no encryption key: the mod is built on the player's PC from their own game.
"""
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYDEPS = os.path.join(HERE, "pydeps")
BUILD_DIR = os.path.join(HERE, "build")
OUT = os.path.join(BUILD_DIR, "dist", "PickAndShiny")
GDRE_FILES = ["gdre_tools.exe", "gdre_tools.pck", "GodotMonoDecompNativeAOT.dll"]

sys.path.insert(0, ROOT)
import build  # noqa: E402  (for MOD_VERSION and the GDRE location)

# GDRE Tools 2.6.4 for Windows (https://github.com/GDRETools/gdsdecomp/releases): PICKSHINY_GDRE
# or a gdre/ folder next to build.py.
GDRE_SRC = os.path.dirname(build._default_gdre())


def main():
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "PickAndShiny",
        "--distpath", os.path.join(BUILD_DIR, "dist"), "--workpath", os.path.join(BUILD_DIR, "work"),
        "--specpath", BUILD_DIR,
        "--paths", ROOT, "--paths", os.path.join(ROOT, "tools"), "--paths", os.path.join(ROOT, "mod"),
        "--paths", os.path.join(ROOT, "tools", "pylib"),
        "--add-data", os.path.join(ROOT, "mod", "boot.gd.in") + os.pathsep + "mod",
        "--hidden-import", "edits", "--hidden-import", "steam_locate",
        os.path.join(ROOT, "app.py"),
    ]
    env = dict(os.environ, PYTHONPATH=PYDEPS)
    subprocess.run(command, check=True, env=env)

    gdre_dir = os.path.join(OUT, "gdre")
    os.makedirs(gdre_dir, exist_ok=True)
    for name in GDRE_FILES:
        shutil.copy2(os.path.join(GDRE_SRC, name), gdre_dir)
    for name in ("README.txt", "THIRD-PARTY-NOTICES.txt"):
        shutil.copy2(os.path.join(HERE, name), OUT)

    archive = os.path.join(HERE, f"PickAndShiny-{build.MOD_VERSION}.zip")
    if os.path.exists(archive):
        os.remove(archive)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for folder, _, files in os.walk(OUT):
            for name in files:
                path = os.path.join(folder, name)
                zf.write(path, os.path.join("PickAndShiny", os.path.relpath(path, OUT)))
    print(f"installer: {archive} ({os.path.getsize(archive) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
