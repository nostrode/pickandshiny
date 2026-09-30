"""Reads string settings (e.g. the autoload list) from a Godot 4 project.binary (ECFG) file."""
import struct

VARIANT_STRING = 4


def read_settings(data):
    if data[:4] != b"ECFG":
        raise ValueError("not a project.binary")
    count = struct.unpack_from("<I", data, 4)[0]
    pos = 8
    out = []
    for _ in range(count):
        name_len = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        name = data[pos:pos + name_len].decode("utf-8")
        pos += name_len
        value_len = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        raw = data[pos:pos + value_len]
        pos += value_len
        value = None
        if len(raw) >= 8 and struct.unpack_from("<I", raw, 0)[0] & 0xFF == VARIANT_STRING:
            slen = struct.unpack_from("<I", raw, 4)[0]
            value = raw[8:8 + slen].decode("utf-8")
        out.append((name, value))
    return out


def autoloads(data):
    return [(n[len("autoload/"):], v) for n, v in read_settings(data) if n.startswith("autoload/")]
