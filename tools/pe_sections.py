"""Minimal PE section table reader + locate a byte string: python pe_sections.py <exe> [hexneedle]"""
import struct
import sys


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + opt_size
    out = []
    for i in range(count):
        s = table + 40 * i
        name = data[s:s + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr, raw_size, raw_ptr = struct.unpack_from("<IIII", data, s + 8)
        out.append((name, raw_ptr, raw_size, vaddr, vsize))
    return out


if __name__ == "__main__":
    blob = open(sys.argv[1], "rb").read()
    for name, ptr, size, va, vs in sections(blob):
        print(f"{name:10} raw={ptr:#x}+{size:#x}")
    if len(sys.argv) > 2:
        needle = bytes.fromhex(sys.argv[2])
        at = blob.find(needle)
        where = [n for n, p, s, _, _ in sections(blob) if p <= at < p + s]
        print("needle at", hex(at), where, "align16" if at % 16 == 0 else f"mod16={at % 16}")
