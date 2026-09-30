"""Recovers a Godot 4 PCK encryption key from the game executable.

Godot compiles the key into the export template as a 32-byte array in the .data section.
Each candidate is checked cheaply against the first block of the encrypted pack directory
(it must decrypt to a sane path length + path text), then confirmed with the full MD5.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pylib"))
from Crypto.Cipher import AES  # noqa: E402
from pck_tool import read_directory  # noqa: E402
from pe_sections import sections  # noqa: E402


def _encrypted_directory_head(pck_path):
    with open(pck_path, "rb") as f:
        head = f.read(40)
        fmt = struct.unpack_from("<I", head, 4)[0]
        if fmt != 3:
            raise ValueError("key search supports pack format 3 (Godot 4.5+) only")
        f.seek(struct.unpack_from("<Q", head, 32)[0] + 4)  # skip the plaintext file count
        f.read(16 + 8)  # md5 + length
        iv = f.read(16)
        cipher = f.read(16)
    return iv, cipher


def _plausible(plain):
    path_len = struct.unpack_from("<I", plain, 0)[0]
    if not 4 <= path_len <= 1024:
        return False
    return all(32 <= b < 127 for b in plain[4:16])


def find_key(exe_path, pck_path, log=print):
    iv, cipher = _encrypted_directory_head(pck_path)
    with open(exe_path, "rb") as f:
        blob = f.read()
    ranges = [(p, s) for n, p, s, _, _ in sections(blob) if n in (".data", ".rdata")]
    for step in (16, 1):  # the array is normally 16-byte aligned; fall back to every offset
        for ptr, size in ranges:
            for off in range(ptr, ptr + size - 32, step):
                key = blob[off:off + 32]
                if len(set(key)) < 20:  # real keys are random bytes
                    continue
                keystream = AES.new(key, AES.MODE_ECB).encrypt(iv)
                plain = bytes(a ^ b for a, b in zip(cipher, keystream))
                if not _plausible(plain):
                    continue
                try:
                    read_directory(pck_path, key)  # full MD5 verification
                except ValueError:
                    continue
                log(f"recovered pack key at exe offset {off:#x}")
                return key
    return None


if __name__ == "__main__":
    found = find_key(sys.argv[1], sys.argv[2])
    print(found.hex().upper() if found else "no key found")
