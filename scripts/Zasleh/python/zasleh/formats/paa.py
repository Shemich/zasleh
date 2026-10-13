"""Reading Arma .paa textures, as far as a preview needs it"""

from __future__ import annotations

import os
import struct
import zlib
from typing import BinaryIO, List, Optional, Tuple

DXT1, DXT2, DXT3, DXT4, DXT5 = 0xFF01, 0xFF02, 0xFF03, 0xFF04, 0xFF05
ARGB4444, ARGB1555, AI88, ARGB8888 = 0x4444, 0x1555, 0x8080, 0x8888
_DXT = (DXT1, DXT2, DXT3, DXT4, DXT5)
_BYTES_PER_PIXEL = {ARGB4444: 2, ARGB1555: 2, AI88: 2, ARGB8888: 4}
KIND_NAMES = {DXT1: "DXT1", DXT2: "DXT2", DXT3: "DXT3", DXT4: "DXT4", DXT5: "DXT5",
              ARGB4444: "ARGB4444", ARGB1555: "ARGB1555", AI88: "AI88", ARGB8888: "ARGB8888"}


class PaaError(Exception):
    """The file isn't a .paa this module can read"""


class Mip:
    __slots__ = ("width", "height", "offset", "size", "lzo")

    def __init__(self, width: int, height: int, offset: int, size: int, lzo: bool):
        self.width, self.height, self.offset, self.size, self.lzo = width, height, offset, size, lzo


def read_mips(stream: BinaryIO) -> Tuple[int, List[Mip]]:
    """(type of the texture, its mipmaps - largest first)"""
    stream.seek(0)
    head = stream.read(2)
    if len(head) < 2:
        raise PaaError("the file is empty")
    kind = struct.unpack("<H", head)[0]
    if kind not in KIND_NAMES:
        raise PaaError("unknown texture type 0x%04X" % kind)
    at = 2
    while True:
        stream.seek(at)
        tag = stream.read(12)
        if len(tag) < 12 or tag[:4] != b"GGAT":
            break
        at += 12 + struct.unpack_from("<I", tag, 8)[0]
    stream.seek(at)
    count = stream.read(2)
    if len(count) < 2:
        raise PaaError("the file ends before the mipmaps")
    at += 2 + 3 * struct.unpack("<H", count)[0]
    mips: List[Mip] = []
    while True:
        stream.seek(at)
        entry = stream.read(7)
        if len(entry) < 7:
            break
        width, height = struct.unpack_from("<HH", entry, 0)
        if width == 0 or height == 0:
            break
        size = entry[4] | (entry[5] << 8) | (entry[6] << 16)
        lzo = kind in _DXT and bool(width & 0x8000)
        mips.append(Mip(width & 0x7FFF, height, at + 7, size, lzo))
        at += 7 + size
    if not mips:
        raise PaaError("the file has no mipmaps")
    return kind, mips


# Decompression

def lzo1x_decompress(src: bytes) -> bytes:
    """LZO1X, as in minilzo's lzo1x_decompress"""
    out = bytearray()

    def match(distance: int, length: int) -> None:
        start = len(out) - distance
        if start < 0:
            raise PaaError("damaged LZO data")
        if distance >= length:
            out.extend(out[start:start + length])
        else:                               # the match runs into what it's writing
            chunk = bytes(out[start:])
            out.extend((chunk * (length // distance + 1))[:length])

    try:
        ip = 0
        t = src[0]
        state = 0                           # 0 top, 1 after a literal run
        if t > 17:
            ip = 1
            t -= 17
            if t < 4:
                state = 4
            else:
                out += src[ip:ip + t]
                ip += t
                state = 1
        while True:
            if state == 0:
                t = src[ip]
                ip += 1
                if t >= 16:
                    state = 2
                else:
                    if t == 0:
                        while src[ip] == 0:
                            t += 255
                            ip += 1
                        t += 15 + src[ip]
                        ip += 1
                    out += src[ip:ip + t + 3]
                    ip += t + 3
                    state = 1
            if state == 1:
                t = src[ip]
                ip += 1
                if t >= 16:
                    state = 2
                else:
                    match(0x0801 + (t >> 2) + (src[ip] << 2), 3)
                    ip += 1
                    state = 3
            if state == 2:
                if t >= 64:
                    match(1 + ((t >> 2) & 7) + (src[ip] << 3), (t >> 5) + 1)
                    ip += 1
                elif t >= 32:
                    t &= 31
                    if t == 0:
                        while src[ip] == 0:
                            t += 255
                            ip += 1
                        t += 31 + src[ip]
                        ip += 1
                    match(1 + (src[ip] >> 2) + (src[ip + 1] << 6), t + 2)
                    ip += 2
                elif t >= 16:
                    distance = (t & 8) << 11
                    t &= 7
                    if t == 0:
                        while src[ip] == 0:
                            t += 255
                            ip += 1
                        t += 7 + src[ip]
                        ip += 1
                    distance += (src[ip] >> 2) + (src[ip + 1] << 6)
                    ip += 2
                    if distance == 0:
                        break               # end of the stream
                    match(distance + 0x4000, t + 2)
                else:
                    match(1 + (t >> 2) + (src[ip] << 2), 2)
                    ip += 1
                state = 3
            if state == 3:
                t = src[ip - 2] & 3
                state = 4 if t else 0
            if state == 4:
                out += src[ip:ip + t]
                ip += t
                t = src[ip]
                ip += 1
                state = 2
    except IndexError:
        raise PaaError("damaged LZO data")
    return bytes(out)


def lzss_decompress(src: bytes, expected: int) -> bytes:
    """The LZSS of Bohemia's file formats: flag bytes, then literals or (offset"""
    out = bytearray()
    ip = 0
    try:
        while len(out) < expected:
            flags = src[ip]
            ip += 1
            for bit in range(8):
                if len(out) >= expected:
                    break
                if flags & (1 << bit):
                    out.append(src[ip])
                    ip += 1
                    continue
                first, second = src[ip], src[ip + 1]
                ip += 2
                position = len(out) - (first | ((second & 0xF0) << 4))
                length = min((second & 0x0F) + 3, expected - len(out))
                for k in range(length):
                    out.append(out[position + k] if position + k >= 0 else 0x20)
    except IndexError:
        raise PaaError("damaged LZSS data")
    return bytes(out)


# Pixels

def _rgb565(value: int) -> Tuple[int, int, int]:
    red, green, blue = value >> 11, (value >> 5) & 0x3F, value & 0x1F
    return (red << 3) | (red >> 2), (green << 2) | (green >> 4), (blue << 3) | (blue >> 2)


def _dxt_rgb(data: bytes, width: int, height: int, block_size: int) -> bytes:
    """The colour of DXT blocks as RGB rows"""
    blocks_wide, blocks_high = (width + 3) // 4, (height + 3) // 4
    if len(data) < blocks_wide * blocks_high * block_size:
        raise PaaError("the mipmap is shorter than its size says")
    skip = block_size - 8
    four_colours = block_size == 16
    palettes: dict = {}
    quads: dict = {}
    unpack = struct.unpack_from
    rows: List[bytes] = []
    offset = skip
    row_bytes = width * 3
    for _block_row in range(blocks_high):
        lines: Tuple[List[bytes], List[bytes], List[bytes], List[bytes]] = ([], [], [], [])
        for _block in range(blocks_wide):
            c0, c1, b0, b1, b2, b3 = unpack("<HHBBBB", data, offset)
            offset += block_size
            key = (c0 << 16) | c1
            palette = palettes.get(key)
            if palette is None:
                r0, g0, b_0 = _rgb565(c0)
                r1, g1, b_1 = _rgb565(c1)
                if four_colours or c0 > c1:
                    third = bytes(((2 * r0 + r1 + 1) // 3, (2 * g0 + g1 + 1) // 3, (2 * b_0 + b_1 + 1) // 3))
                    fourth = bytes(((r0 + 2 * r1 + 1) // 3, (g0 + 2 * g1 + 1) // 3, (b_0 + 2 * b_1 + 1) // 3))
                else:                       # three colours and "transparent", shown black
                    third = bytes(((r0 + r1) // 2, (g0 + g1) // 2, (b_0 + b_1) // 2))
                    fourth = b"\x00\x00\x00"
                palette = palettes[key] = (bytes((r0, g0, b_0)), bytes((r1, g1, b_1)), third, fourth)
            for line, bits in zip(lines, (b0, b1, b2, b3)):
                quad_key = (key << 8) | bits
                quad = quads.get(quad_key)
                if quad is None:
                    quad = quads[quad_key] = (palette[bits & 3] + palette[(bits >> 2) & 3] +
                                              palette[(bits >> 4) & 3] + palette[bits >> 6])
                line.append(quad)
        for line in lines:
            if len(rows) < height:
                rows.append(b"".join(line)[:row_bytes])
    return b"".join(rows)


def _plain_rgb(kind: int, data: bytes, width: int, height: int) -> bytes:
    count = width * height
    if len(data) < count * _BYTES_PER_PIXEL[kind]:
        raise PaaError("the mipmap is shorter than its size says")
    out = bytearray(count * 3)
    if kind == ARGB8888:                    # stored blue, green, red, alpha
        out[0::3] = data[2:count * 4:4]
        out[1::3] = data[1:count * 4:4]
        out[2::3] = data[0:count * 4:4]
    elif kind == AI88:                      # luminance, alpha
        grey = data[0:count * 2:2]
        out[0::3] = grey
        out[1::3] = grey
        out[2::3] = grey
    else:
        values = struct.unpack_from("<%dH" % count, data, 0)
        if kind == ARGB4444:
            out[0::3] = bytes(((v >> 8) & 0xF) * 17 for v in values)
            out[1::3] = bytes(((v >> 4) & 0xF) * 17 for v in values)
            out[2::3] = bytes((v & 0xF) * 17 for v in values)
        else:                               # ARGB1555
            five = [(i << 3) | (i >> 2) for i in range(32)]
            out[0::3] = bytes(five[(v >> 10) & 0x1F] for v in values)
            out[1::3] = bytes(five[(v >> 5) & 0x1F] for v in values)
            out[2::3] = bytes(five[v & 0x1F] for v in values)
    return bytes(out)


def pick_mip(mips: List[Mip], max_size: Optional[int]) -> Mip:
    """The largest mipmap no bigger than max_size on its longer side"""
    if max_size is None:
        return mips[0]
    for mip in mips:
        if max(mip.width, mip.height) <= max_size:
            return mip
    return mips[-1]


def decode(stream: BinaryIO, max_size: Optional[int] = None) -> Tuple[int, int, bytes]:
    """(width, height, RGB bytes) of the mipmap that fits max_size"""
    kind, mips = read_mips(stream)
    mip = pick_mip(mips, max_size)
    stream.seek(mip.offset)
    data = stream.read(mip.size)
    if len(data) < mip.size:
        raise PaaError("the file ends inside a mipmap")
    if kind in _DXT:
        if mip.lzo:
            data = lzo1x_decompress(data)
        return mip.width, mip.height, _dxt_rgb(data, mip.width, mip.height, 8 if kind == DXT1 else 16)
    data = lzss_decompress(data, mip.width * mip.height * _BYTES_PER_PIXEL[kind])
    return mip.width, mip.height, _plain_rgb(kind, data, mip.width, mip.height)


def write_png(path: str, width: int, height: int, rgb: bytes) -> None:
    """An 8-bit RGB .png"""
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(name: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body) & 0xFFFFFFFF)

    content = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
               chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b""))
    temporary = path + ".part"
    with open(temporary, "wb") as stream:
        stream.write(content)
    os.replace(temporary, path)


def to_png(paa_path: str, png_path: str, max_size: Optional[int] = 512) -> Tuple[int, int]:
    """Write a preview of a .paa as a .png"""
    with open(paa_path, "rb") as stream:
        width, height, rgb = decode(stream, max_size)
    folder = os.path.dirname(png_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    write_png(png_path, width, height, rgb)
    return width, height
