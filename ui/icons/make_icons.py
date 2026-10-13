"""Draws the toolbar icon: a cube seen from a corner. Run it to make the .bmp files anew.

3ds Max takes an icon as two pictures per size: <name>_24i.bmp / <name>_16i.bmp (colour) and
<name>_24a.bmp / <name>_16a.bmp (mask, white where the icon is).
"""
import math
import os
import struct
import sys

NAME = "zasleh"
EDGE = (44, 52, 28)
TOP, LEFT, RIGHT = (206, 220, 138), (142, 162, 84), (96, 116, 58)
SAMPLES = 6             # per pixel and axis


def inside(polygon, x, y):
    hit = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        if (ay > y) != (by > y) and x < ax + (bx - ax) * (y - ay) / (by - ay):
            hit = not hit
    return hit


def draw(width, height):
    """(rgb rows, mask rows), top row first"""
    cx, cy = width / 2.0, height / 2.0
    radius = min(width, height) / 2.0 - 0.5

    def corner(turn, scale=1.0, origin=(cx, cy)):
        angle = math.radians(90 - 60 * turn)
        return origin[0] + radius * scale * math.cos(angle), origin[1] - radius * scale * math.sin(angle)

    hexagon = [corner(i) for i in range(6)]
    gap = 0.9 / radius                                  # the dark line between the faces
    shapes = []
    for colour, turns in ((TOP, (5, 0, 1)), (RIGHT, (1, 2, 3)), (LEFT, (3, 4, 5))):
        middle = corner(turns[1], 0.5)
        centre = (cx + (middle[0] - cx) * gap * 1.2, cy + (middle[1] - cy) * gap * 1.2)
        face = [centre] + [corner(t, 1.0 - gap, centre) for t in turns]
        shapes.append((colour, face))
    rgb, mask = [], []
    for row in range(height):
        rgb_row, mask_row = [], []
        for column in range(width):
            total, covered = [0, 0, 0], 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x, y = column + (sx + 0.5) / SAMPLES, row + (sy + 0.5) / SAMPLES
                    if not inside(hexagon, x, y):
                        continue
                    covered += 1
                    colour = next((c for c, face in shapes if inside(face, x, y)), EDGE)
                    for i in range(3):
                        total[i] += colour[i]
            rgb_row.append(tuple(int(round(t / covered)) for t in total) if covered else (0, 0, 0))
            mask_row.append(int(round(255.0 * covered / SAMPLES ** 2)))
        rgb.append(rgb_row)
        mask.append(mask_row)
    return rgb, mask


def write_bmp(path, rows):
    height, width = len(rows), len(rows[0])
    pad = (4 - width * 3 % 4) % 4
    body = b"".join(b"".join(bytes((b, g, r)) for r, g, b in row) + bytes(pad) for row in reversed(rows))
    with open(path, "wb") as stream:
        stream.write(b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54))
        stream.write(struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(body), 2835, 2835, 0, 0))
        stream.write(body)


def main(folder):
    for label, (width, height) in (("24", (24, 24)), ("16", (16, 15))):
        rgb, mask = draw(width, height)
        write_bmp(os.path.join(folder, "%s_%si.bmp" % (NAME, label)), rgb)
        write_bmp(os.path.join(folder, "%s_%sa.bmp" % (NAME, label)), [[(v, v, v) for v in row] for row in mask])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))
