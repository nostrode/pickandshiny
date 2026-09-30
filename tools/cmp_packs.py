"""Compares the files inside two unencrypted patch packs: python cmp_packs.py a.pck b.pck"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pck_tool import read_directory, read_file  # noqa: E402


def contents(path):
    _, entries = read_directory(path, b"\0" * 32)
    return {e[0]: read_file(path, b"\0" * 32, e) for e in entries}


a, b = contents(sys.argv[1]), contents(sys.argv[2])
for name in sorted(set(a) | set(b)):
    same = a.get(name) == b.get(name)
    print(f"{'same' if same else 'DIFF'} {name} {hashlib.md5(a.get(name, b'')).hexdigest()[:8]} {hashlib.md5(b.get(name, b'')).hexdigest()[:8]}")
