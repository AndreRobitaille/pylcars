"""Rebuild the 320x240 LCARS assets with ImageMagick and the bundled OFL font."""
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'CIRCUITPY/lcars'
FONT = ROOT / 'design/Antonio.ttf'
OUT.mkdir(parents=True, exist_ok=True)

BLACK = '#000000'
GOLD = '#ffcc66'
PEACH = '#ffcc99'
LILAC = '#cc99cc'
BLUE = '#9999cc'
ORANGE = '#ff9966'
CREAM = '#f5ddc6'


def make_background(name, setup=False):
    shapes = [f'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="black"/>']
    text = []

    def rect(x, y, w, h, color, r=0):
        shapes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{color}"/>')

    def label(x, baseline, value, size, color):
        text.append((x, baseline, value, size, color))

    # Large asymmetrical elbows and segmented bars, rather than card panels.
    shapes.append(f'<path d="M8 73 V34 Q8 8 34 8 H119 V27 H74 Q58 27 58 43 V73 Z" fill="{GOLD}"/>')
    rect(124, 8, 24, 19, LILAC)
    rect(153, 8, 18, 19, ORANGE)
    label(183, 24, 'LCARS / ENVIRONMENT', 14, PEACH)
    label(19, 64, '47-01', 14, BLACK)
    rect(8, 78, 50, 37, LILAC)
    rect(8, 120, 50, 37, BLUE)
    rect(8, 162, 50, 40, PEACH)
    label(35, 106, '01', 18, BLACK)
    label(35, 148, '02', 18, BLACK)
    label(19 if setup else 15, 190, 'BACK' if setup else 'SETUP', 13, BLACK)
    shapes.append(f'<path d="M8 207 H58 Q58 218 70 218 H140 V234 H34 Q8 234 8 208 Z" fill="{GOLD}"/>')
    rect(145, 218, 55, 16, LILAC)
    rect(205, 218, 56, 16, BLUE)
    rect(266, 218, 46, 16, ORANGE, 8)
    label(76, 231, 'CONTROL', 11, BLACK)
    label(155, 231, '1701-D', 11, BLACK)
    label(218, 231, '047', 11, BLACK)
    label(277, 231, '03', 11, BLACK)

    if not setup:
        label(76, 48, 'MAIN BEDROOM', 14, GOLD)
        label(76, 76, 'NIGHTSTAND LAMP', 24, CREAM)
        rect(76, 109, 110, 61, PEACH, 30)
        rect(194, 109, 110, 61, LILAC, 30)
        label(115, 151, 'ON', 34, BLACK)
        label(227, 151, 'OFF', 34, BLACK)
        label(79, 184, '01 / ACTIVATE', 11, PEACH)
        label(197, 184, '02 / DEACTIVATE', 11, LILAC)
    else:
        label(76, 46, 'COMMUNICATIONS / SETUP', 15, GOLD)
        label(76, 61, 'APPLE HOME PAIRING CODE', 11, BLUE)
        label(76, 99, 'WI-FI SETUP NETWORK', 11, BLUE)
        label(76, 131, 'NETWORK PASSWORD', 11, BLUE)
        label(76, 162, 'SETUP PAGE / 192.168.4.1', 11, PEACH)
        rect(76, 170, 228, 32, PEACH, 16)
    shapes.append('</svg>')
    svg = ROOT / 'design' / (name + '.svg')
    svg.write_text(''.join(shapes))
    args = ['magick', '-background', 'black', str(svg), '-font', str(FONT)]
    for x, y, value, size, color in text:
        args += ['-pointsize', str(size), '-fill', color, '-draw', f"text {x},{y} '{value}'"]
    args += ['-type', 'TrueColor', '-depth', '8', 'BMP3:' + str(OUT / (name + '.bmp'))]
    subprocess.run(args, check=True)


def make_font(size, cellw, cellh):
    # All 95 printable ASCII glyphs retain a common baseline. Glyphs share one
    # one-bit atlas in RAM; advance widths keep Antonio's condensed proportions.
    cols, rows = 16, 6
    width, height = cols * cellw, rows * cellh
    pixels = bytearray(width * height)
    advances = bytearray()
    for index, code in enumerate(range(32, 127)):
        escaped = chr(code).replace('\\', '\\\\').replace("'", "\\'")
        raw = subprocess.check_output([
            'magick', '-size', f'{cellw}x{cellh}', 'xc:black', '-font', str(FONT),
            '-pointsize', str(size), '-fill', 'white',
            '-draw', "text 0,%d '%s'" % (size + 2, escaped),
            '-threshold', '45%', '-depth', '8', 'gray:-'])
        assert len(raw) == cellw * cellh
        occupied = [x for x in range(cellw) if any(raw[y * cellw + x] for y in range(cellh))]
        advance = max(occupied) + 2 if occupied else max(3, size // 4)
        assert advance <= cellw, (size, chr(code), advance)
        advances.append(advance)
        gx, gy = (index % cols) * cellw, (index // cols) * cellh
        for y in range(cellh):
            for x in range(cellw):
                pixels[(gy + y) * width + gx + x] = bool(raw[y * cellw + x])
    packed = bytearray(math.ceil(len(pixels) / 8))
    for i, on in enumerate(pixels):
        if on:
            packed[i // 8] |= 1 << (7 - i % 8)
    payload = struct.pack('<HHBB', width, height, cellw, cellh) + advances + packed
    (OUT / ('antonio%d.bin' % size)).write_bytes(payload)


if __name__ == '__main__':
    make_background('main')
    make_background('setup', True)
    make_font(12, 16, 18)
    make_font(16, 20, 24)
    make_font(24, 28, 32)
    print('LCARS backgrounds and three compact Antonio font atlases built.')
