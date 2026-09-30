"""Writes an unencrypted Godot 4.x resource pack (format 3), readable by Godot 4.5/4.6."""
import hashlib
import struct

ALIGN = 16


def _pad(n, align=ALIGN):
    return (-n) % align


def write_pck(out_path, files, godot_version=(4, 6, 0)):
    """files: list of (res_path_without_prefix, bytes)."""
    header = struct.pack("<4sIIIII", b"GDPC", 3, *godot_version, 2)  # flags: PACK_REL_FILEBASE
    header_len = len(header) + 8 + 8 + 16 * 4
    file_base = header_len + _pad(header_len)

    blob = bytearray()
    entries = []
    for path, data in files:
        entries.append((path, len(blob), len(data), hashlib.md5(data).digest()))
        blob += data
        blob += b"\0" * _pad(len(blob))

    directory = bytearray()
    for path, ofs, size, md5 in entries:
        p = path.encode("utf-8")
        p += b"\0" * _pad(len(p), 4)
        directory += struct.pack("<I", len(p)) + p
        directory += struct.pack("<QQ", ofs, size) + md5 + struct.pack("<I", 0)

    dir_offset = file_base + len(blob)
    with open(out_path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<QQ", file_base, dir_offset))
        f.write(b"\0" * (16 * 4))
        f.write(b"\0" * (file_base - header_len))
        f.write(blob)
        f.write(struct.pack("<I", len(entries)))
        f.write(directory)
