"""Copies the publishable files (explicit allowlist) into a git checkout and scans them.

  python export_repo.py <checkout folder>

Never exported: decompiled game code, extracted game files, the recovered pack key, saves,
logs, build output and third-party binaries.
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ALLOWLIST = [
    "README.md", "requirements.txt", ".gitignore",
    "app.py", "build.py", "steam_locate.py", "launch.pyw", "export_repo.py",
    "mod/edits.py", "mod/boot.gd.in",
    "tools/pck_tool.py", "tools/pck_write.py", "tools/project_binary.py", "tools/keyfind.py",
    "tools/pe_sections.py", "tools/inspect_pck.py", "tools/gdc_diff.py", "tools/cmp_packs.py",
    "tools/test_degradation.py", "tools/test_override.py", "tools/test_auto_failures.py",
    "tools/test_game_running.py",
    "installer/make_installer.py", "installer/README.txt", "installer/THIRD-PARTY-NOTICES.txt",
]
# Anything that looks like a 256-bit key, a user profile path or an e-mail address.
FORBIDDEN = [re.compile(r"\b[0-9A-Fa-f]{64}\b"), re.compile(r"(?i)users[\\/]+\w+"),
             re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")]
FORBIDDEN_WORDS = [w.lower() for w in (os.environ.get("USERNAME", ""), os.environ.get("COMPUTERNAME", "")) if w]


def main():
    target = sys.argv[1]
    problems = []
    for rel in ALLOWLIST:
        src = os.path.join(ROOT, *rel.split("/"))
        dest = os.path.join(target, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        with open(src, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for pattern in FORBIDDEN:
            for match in pattern.finditer(text):
                if "noreply" not in match.group(0) and "example" not in match.group(0):
                    problems.append(f"{rel}: {match.group(0)[:40]}")
        problems += [f"{rel}: contains '{w}'" for w in FORBIDDEN_WORDS if w in text.lower()]
    for problem in problems:
        print("CHECK:", problem)
    print(f"exported {len(ALLOWLIST)} files to {target}; {len(problems)} findings")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
