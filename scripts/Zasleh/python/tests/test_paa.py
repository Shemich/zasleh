import io
import os
import struct
import tempfile
import unittest
import zlib

from atb_p3d import paa

from . import paa_samples


def rows(width, height, rgb):
    stride = width * 3
    return [[tuple(rgb[y * stride + 3 * x:y * stride + 3 * x + 3]) for x in range(width)] for y in range(height)]


class Decompression(unittest.TestCase):
    def test_lzo_literals_only(self):
        self.assertEqual(paa.lzo1x_decompress(paa_samples.lzo_literals(b"abcdefgh")), b"abcdefgh")

    def test_lzo_match_that_overlaps_itself(self):
        # three literals, then "copy 6 bytes from 3 back": the pattern repeats into itself
        stream = bytes([17 + 3]) + b"abc" + bytes([(5 << 5) | (2 << 2), 0]) + b"\x11\x00\x00"
        self.assertEqual(paa.lzo1x_decompress(stream), b"abcabcabc")

    def test_lzo_long_literal_run_and_far_match(self):
        data = bytes(range(200)) * 2
        # a literal run of 200 bytes (0, then length - 18), then a match of 200 bytes from 200 back
        stream = (bytes([0, 200 - 18]) + data[:200] +
                  bytes([0x20, 167, (199 & 0x3F) << 2, 199 >> 6]) + b"\x11\x00\x00")
        self.assertEqual(paa.lzo1x_decompress(stream), data)

    def test_lzo_damaged(self):
        with self.assertRaises(paa.PaaError):
            paa.lzo1x_decompress(bytes([17 + 8]) + b"abc")

    def test_lzss(self):
        # eight literals, then a pair: 3 bytes from 8 back; then a pair reaching before the start: spaces
        stream = b"\xff" + b"abcdefgh" + b"\x00" + bytes([8, 0]) + bytes([200, 0])
        self.assertEqual(paa.lzss_decompress(stream, 14), b"abcdefgh" + b"abc" + b"   ")


class Decoding(unittest.TestCase):
    def test_mips(self):
        kind, mips = paa.read_mips(io.BytesIO(paa_samples.red_blue_paa()))
        self.assertEqual(kind, paa.DXT1)
        self.assertEqual([(m.width, m.height, m.lzo) for m in mips], [(8, 8, False), (4, 4, True)])
        self.assertEqual(paa.pick_mip(mips, None).width, 8)
        self.assertEqual(paa.pick_mip(mips, 512).width, 8)
        self.assertEqual(paa.pick_mip(mips, 4).width, 4)
        self.assertEqual(paa.pick_mip(mips, 2).width, 4)        # nothing that small: the smallest there is

    def test_dxt1(self):
        width, height, rgb = paa.decode(io.BytesIO(paa_samples.red_blue_paa()))
        self.assertEqual((width, height, len(rgb)), (8, 8, 8 * 8 * 3))
        for y, row in enumerate(rows(width, height, rgb)):
            self.assertEqual(row, [paa_samples.RED_BLUE_ROWS[y % 4]] * 8)

    def test_dxt1_compressed_mip(self):
        width, height, rgb = paa.decode(io.BytesIO(paa_samples.red_blue_paa()), 4)
        self.assertEqual((width, height), (4, 4))
        self.assertEqual([row[0] for row in rows(width, height, rgb)], paa_samples.RED_BLUE_ROWS)

    def test_dxt1_three_colour_block(self):
        # c0 <= c1: the third colour is the average, the fourth is "transparent" (black here)
        block = struct.pack("<HHBBBB", 0x001F, 0xF800, 0xAA, 0xFF, 0x00, 0x55)
        width, height, rgb = paa.decode(io.BytesIO(paa_samples.make_paa(paa.DXT1, [(4, 4, block)])))
        self.assertEqual([row[0] for row in rows(width, height, rgb)], [(127, 0, 127), (0, 0, 0), (0, 0, 255), (255, 0, 0)])

    def test_dxt5_colour_follows_the_alpha(self):
        block = b"\xff" * 8 + paa_samples.RED_BLUE_BLOCK
        width, height, rgb = paa.decode(io.BytesIO(paa_samples.make_paa(paa.DXT5, [(4, 4, block)])))
        self.assertEqual([row[0] for row in rows(width, height, rgb)], paa_samples.RED_BLUE_ROWS)

    def test_argb8888(self):
        pixels = bytes([10, 20, 30, 255, 40, 50, 60, 255])                 # blue, green, red, alpha
        packed = b"\xff" + pixels                                          # LZSS: eight literals
        width, height, rgb = paa.decode(io.BytesIO(paa_samples.make_paa(paa.ARGB8888, [(2, 1, packed + b"\x00" * 4)])))
        self.assertEqual(rows(width, height, rgb), [[(30, 20, 10), (60, 50, 40)]])

    def test_argb1555_and_4444(self):
        value = struct.pack("<H", (1 << 15) | (31 << 10) | (0 << 5) | 16)
        width, height, rgb = paa.decode(io.BytesIO(paa_samples.make_paa(paa.ARGB1555, [(1, 1, b"\x03" + value + b"\x00" * 4)])))
        self.assertEqual(rows(width, height, rgb), [[(255, 0, 132)]])
        value = struct.pack("<H", 0xF0A5)
        width, height, rgb = paa.decode(io.BytesIO(paa_samples.make_paa(paa.ARGB4444, [(1, 1, b"\x03" + value + b"\x00" * 4)])))
        self.assertEqual(rows(width, height, rgb), [[(0, 170, 85)]])

    def test_not_a_paa(self):
        for data in (b"", b"MLOD and so on", struct.pack("<HH", paa.DXT1, 0)):
            with self.assertRaises(paa.PaaError):
                paa.decode(io.BytesIO(data))


class Png(unittest.TestCase):
    def test_preview_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "hull_co.paa")
            with open(source, "wb") as stream:
                stream.write(paa_samples.red_blue_paa())
            target = os.path.join(folder, "cache", "deep", "hull_co.png")
            self.assertEqual(paa.to_png(source, target, 512), (8, 8))
            with open(target, "rb") as stream:
                data = stream.read()
            self.assertEqual(os.listdir(os.path.dirname(target)), ["hull_co.png"])     # no half-written file left
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack_from(">IIBB", data, 16), (8, 8, 8, 2))
        at = data.index(b"IDAT")
        size = struct.unpack_from(">I", data, at - 4)[0]
        raw = zlib.decompress(data[at + 4:at + 4 + size])
        self.assertEqual(len(raw), 8 * (1 + 8 * 3))
        self.assertEqual(raw[0:4], b"\x00\xff\x00\x00")                  # filter 0, then a red pixel


if __name__ == "__main__":
    unittest.main()
