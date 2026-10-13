"""Tiny .paa files made by hand, for the tests"""

import struct

# one DXT1 block: red and blue, a row of each of the four colours
RED_BLUE_BLOCK = struct.pack("<HHBBBB", 0xF800, 0x001F, 0x00, 0x55, 0xAA, 0xFF)
RED_BLUE_ROWS = [(255, 0, 0), (0, 0, 255), (170, 0, 85), (85, 0, 170)]


def lzo_literals(data: bytes) -> bytes:
    """An LZO1X stream that holds the data as one literal run (up to 238 bytes)"""
    assert 4 <= len(data) <= 238
    return bytes([17 + len(data)]) + data + b"\x11\x00\x00"


def make_paa(kind: int, mips, tags=()) -> bytes:
    """mips: (width, height, data) or (width, height, data, True) for LZO-compressed DXT data"""
    out = struct.pack("<H", kind)
    for name, body in tags:
        out += b"GGAT" + name[::-1] + struct.pack("<I", len(body)) + body
    out += struct.pack("<H", 0)                         # no palette
    for mip in mips:
        width, height, data = mip[:3]
        if len(mip) > 3 and mip[3]:
            data = lzo_literals(data)
            width |= 0x8000
        out += struct.pack("<HH", width, height) + struct.pack("<I", len(data))[:3] + data
    return out + b"\x00" * 6


def red_blue_paa() -> bytes:
    """DXT1, 8 x 8 (four blocks) with a 4 x 4 mipmap that's LZO-compressed"""
    return make_paa(0xFF01, [(8, 8, RED_BLUE_BLOCK * 4), (4, 4, RED_BLUE_BLOCK, True)],
                    tags=[(b"AVGC", b"\x00" * 4), (b"OFFS", b"\x00" * 64)])
