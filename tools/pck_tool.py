"""Minimal Godot 4.x PCK reader (pack format 2/3) with AES-256-CFB decryption.

Usage:
  python pck_tool.py list    <pck> <key_hex> <out_list.txt>
  python pck_tool.py extract <pck> <key_hex> <out_dir> <glob> [<glob> ...]
"""
import fnmatch
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pylib"))
from Crypto.Cipher import AES  # noqa: E402

PACK_DIR_ENCRYPTED = 1 << 0
PACK_REL_FILEBASE = 1 << 1
PACK_FILE_ENCRYPTED = 1 << 0
PACK_FILE_REMOVAL = 1 << 1


def decrypt_block(f, key, with_magic):
    """Reads a FileAccessEncrypted stream at the current position and returns plaintext."""
    if with_magic:
        magic = f.read(4)
        if magic != b"GDEC":
            raise ValueError(f"bad encrypted magic {magic!r}")
    md5 = f.read(16)
    length = struct.unpack("<Q", f.read(8))[0]
    iv = f.read(16)
    ds = length + (-length % 16)
    data = f.read(ds)
    plain = AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).decrypt(data)[:length]
    if hashlib.md5(plain).digest() != md5:
        raise ValueError("MD5 mismatch - wrong key or corrupt data")
    return plain


def read_directory(pck_path, key):
    with open(pck_path, "rb") as f:
        magic, fmt, vmaj, vmin, vpat, flags, file_base = struct.unpack("<4sIIIIIQ", f.read(32))
        if magic != b"GDPC":
            raise ValueError("not a PCK")
        start = 0
        if fmt == 3 or (fmt == 2 and flags & PACK_REL_FILEBASE):
            file_base += start
        if fmt == 3:
            dir_ofs = struct.unpack("<Q", f.read(8))[0] + start
            f.seek(dir_ofs)
        else:
            f.read(16 * 4)
        # Godot 4.5+ stores the file count in plaintext ahead of the encrypted directory.
        count = struct.unpack("<I", f.read(4))[0]
        if flags & PACK_DIR_ENCRYPTED:
            raw = decrypt_block(f, key, with_magic=False)
        else:
            raw = f.read()
    entries = []
    pos = 0
    for _ in range(count):
        sl = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        path = raw[pos:pos + sl].split(b"\0", 1)[0].decode("utf-8")
        pos += sl
        ofs, size = struct.unpack_from("<QQ", raw, pos)
        pos += 16
        md5 = raw[pos:pos + 16]
        pos += 16
        fflags = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        entries.append((path, file_base + ofs, size, md5, fflags))
    return (fmt, vmaj, vmin, vpat, flags), entries


def read_file(pck_path, key, entry):
    path, ofs, size, md5, fflags = entry
    with open(pck_path, "rb") as f:
        f.seek(ofs)
        if fflags & PACK_FILE_ENCRYPTED:
            return decrypt_block(f, key, with_magic=True)
        data = f.read(size)
    if hashlib.md5(data).digest() != md5 and any(md5):
        raise ValueError(f"MD5 mismatch for {path}")
    return data


def norm(path):
    return path[len("res://"):] if path.startswith("res://") else path


def main():
    cmd, pck, key_hex = sys.argv[1], sys.argv[2], sys.argv[3]
    key = bytes.fromhex(key_hex)
    header, entries = read_directory(pck, key)
    print("header (fmt, major, minor, patch, flags):", header, "files:", len(entries))
    if cmd == "list":
        with open(sys.argv[4], "w", encoding="utf-8") as out:
            for path, ofs, size, md5, fflags in entries:
                out.write(f"{norm(path)}\t{size}\t{'E' if fflags & PACK_FILE_ENCRYPTED else '-'}\n")
        print("wrote", sys.argv[4])
    elif cmd == "extract":
        out_dir, globs = sys.argv[4], sys.argv[5:]
        n = 0
        for e in entries:
            rel = norm(e[0])
            if not any(fnmatch.fnmatch(rel, g) for g in globs):
                continue
            dest = os.path.join(out_dir, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(read_file(pck, key, e))
            n += 1
        print("extracted", n, "files to", out_dir)


if __name__ == "__main__":
    main()
