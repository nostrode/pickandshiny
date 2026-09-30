"""Checks build.game_running() against a process that is certainly running (explorer.exe)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

print("eslabong.exe running:", build.game_running())
real_exe = build.GAME_EXE
build.GAME_EXE = r"C:\Windows\explorer.exe"
assert build.game_running(), "explorer.exe must be detected"
build.GAME_EXE = r"C:\nowhere\surely_not_running_12345.exe"
assert not build.game_running()
build.GAME_EXE = real_exe
print("process detection works")
