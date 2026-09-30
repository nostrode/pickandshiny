"""Dumps every entry of an unencrypted pack: raw path bytes, offset, size and a content preview."""
import struct
import sys

path = sys.argv[1]
with open(path, "rb") as f:
    data = f.read()
magic, fmt, vmaj, vmin, vpat, flags, file_base, dir_ofs = struct.unpack_from("<4sIIIIIQQ", data, 0)
print(f"{magic} fmt={fmt} godot={vmaj}.{vmin}.{vpat} flags={flags} file_base={file_base} dir={dir_ofs} size={len(data)}")
pos = dir_ofs
count = struct.unpack_from("<I", data, pos)[0]
pos += 4
for _ in range(count):
    sl = struct.unpack_from("<I", data, pos)[0]
    raw = data[pos + 4:pos + 4 + sl]
    pos += 4 + sl
    ofs, size = struct.unpack_from("<QQ", data, pos)
    pos += 16 + 16 + 4
    start = file_base + ofs
    blob = data[start:start + size]
    preview = blob[:70] if size < 200 else blob[:40] + b" ... " + blob[-30:]
    print(f"{raw!r} ofs={ofs} abs={start} size={size} end={start + size} nul_in_content={b'\\0' in blob}\n    {preview!r}")
