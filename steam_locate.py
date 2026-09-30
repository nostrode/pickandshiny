"""Finds the Eslabong install folder through Steam (registry + every Steam library)."""
import os
import re

APP_ID = "4560660"
GAME_FOLDER = "Eslabong"


def _steam_roots():
    roots = []
    try:
        import winreg
        for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    roots.append(os.path.normpath(winreg.QueryValueEx(handle, value)[0]))
            except OSError:
                continue
    except ImportError:
        pass
    roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", r"C:\Steam"]
    seen, unique = set(), []
    for root in roots:
        if root.lower() not in seen and os.path.isdir(root):
            seen.add(root.lower())
            unique.append(root)
    return unique


def _libraries(steam_root):
    libraries = [steam_root]
    vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, encoding="utf-8", errors="replace") as f:
            for match in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                libraries.append(os.path.normpath(match.group(1).replace("\\\\", "\\")))
    except OSError:
        pass
    return libraries


def _install_dir_name(library):
    manifest = os.path.join(library, "steamapps", f"appmanifest_{APP_ID}.acf")
    try:
        with open(manifest, encoding="utf-8", errors="replace") as f:
            match = re.search(r'"installdir"\s+"([^"]+)"', f.read())
            if match:
                return match.group(1)
    except OSError:
        pass
    return GAME_FOLDER


def is_game_dir(path):
    return bool(path) and os.path.isfile(os.path.join(path, "eslabong.exe")) \
        and os.path.isfile(os.path.join(path, "eslabong.pck"))


def find_game_dirs():
    found = []
    for root in _steam_roots():
        for library in _libraries(root):
            candidate = os.path.join(library, "steamapps", "common", _install_dir_name(library))
            if is_game_dir(candidate) and os.path.normcase(candidate) not in map(os.path.normcase, found):
                found.append(candidate)
    return found


if __name__ == "__main__":
    print(find_game_dirs())
