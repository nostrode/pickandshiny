"""Compares two GDScript 4.5 binary token files (.gdc): identifiers, constants, tokens."""
import struct
import sys
from compression import zstd


def load(path):
    raw = open(path, "rb").read()
    assert raw[:4] == b"GDSC", path
    version, size = struct.unpack_from("<II", raw, 4)
    body = zstd.decompress(raw[12:]) if size else raw[12:]
    ident_count, const_count, line_count, token_count = struct.unpack_from("<IIII", body, 0)
    pos = 16
    idents = []
    for _ in range(ident_count):
        n = struct.unpack_from("<I", body, pos)[0]
        pos += 4
        chars = bytes(b ^ 0xB6 for b in body[pos:pos + 4 * n])
        idents.append(chars.decode("utf-32-le", "replace"))
        pos += 4 * n
    return {"version": version, "idents": idents, "consts_blob_start": pos, "body": body,
            "counts": (ident_count, const_count, line_count, token_count)}


a, b = load(sys.argv[1]), load(sys.argv[2])
print("version", a["version"], b["version"])
print("counts (identifiers, constants, lines, tokens)", a["counts"], b["counts"])
sa, sb = set(a["idents"]), set(b["idents"])
print("identifiers only in original:", sorted(sa - sb)[:40])
print("identifiers only in recompiled:", sorted(sb - sa)[:40])
ba, bb = a["body"][a["consts_blob_start"]:], b["body"][b["consts_blob_start"]:]
diffs = [i for i in range(min(len(ba), len(bb))) if ba[i] != bb[i]]
print("after identifiers: len", len(ba), len(bb), "differing bytes:", len(diffs))
regions = []
for i in diffs:
    if regions and i - regions[-1][1] <= 16:
        regions[-1][1] = i
    else:
        regions.append([i, i])
for start, end in regions[:40]:
    print(f"@{start}: orig {ba[start - 12:end + 12].hex(' ')}")
    print(f"{' ' * len(str(start))}  recmp {bb[start - 12:end + 12].hex(' ')}")
    if ba[start - 4:start - 2] == b"\x03\x00":
        print("   float64:", struct.unpack_from("<d", ba, start - (start - 0) % 1 - 0 if False else start - 1)[0] if False else "")
