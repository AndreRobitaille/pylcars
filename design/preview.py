"""Render the actual CircuitPython UI assets and layout on the Mac for review."""
import sys
import types
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'CIRCUITPY/lib'))


class Group(list):
    def __init__(self, x=0, y=0):
        super().__init__()
        self.x, self.y = x, y


class Bitmap:
    def __init__(self, width, height, colors):
        self.width, self.height = width, height
        self.pixels = bytearray(width * height)

    def __setitem__(self, key, value):
        x, y = key
        assert 0 <= x < self.width and 0 <= y < self.height
        self.pixels[y * self.width + x] = value

    def fill(self, value):
        self.pixels[:] = bytes([value]) * len(self.pixels)


class Palette(list):
    def __init__(self, count):
        super().__init__([0] * count)
        self.transparent = set()

    def make_transparent(self, index):
        self.transparent.add(index)


class OnDiskBitmap:
    def __init__(self, path):
        self.width, self.height = map(int, subprocess.check_output(['magick', 'identify', '-format', '%w %h', path]).split())
        self.pixels = subprocess.check_output(['magick', path, '-depth', '8', 'rgb:-'])
        self.pixel_shader = None


class TileGrid:
    def __init__(self, bitmap, pixel_shader, tile_width=None, tile_height=None, default_tile=0, x=0, y=0):
        self.bitmap, self.palette = bitmap, pixel_shader
        self.width, self.height = tile_width or bitmap.width, tile_height or bitmap.height
        self.index = default_tile
        self.x, self.y = x, y


sys.modules['displayio'] = types.SimpleNamespace(Group=Group, Bitmap=Bitmap, Palette=Palette, OnDiskBitmap=OnDiskBitmap, TileGrid=TileGrid)
from lcars_ui import LCARSScreen
from pyportal_wire import HomeKitLink


def render(group, filename):
    result = bytearray(320 * 240 * 3)

    def draw(node, ox=0, oy=0):
        ox += node.x
        oy += node.y
        if isinstance(node, Group):
            for item in node:
                draw(item, ox, oy)
            return
        bitmap = node.bitmap
        cols = bitmap.width // node.width
        sx = (node.index % cols) * node.width
        sy = (node.index // cols) * node.height
        for y in range(node.height):
            for x in range(node.width):
                tx, ty = ox + x, oy + y
                if not (0 <= tx < 320 and 0 <= ty < 240):
                    continue
                index = (sy + y) * bitmap.width + sx + x
                if isinstance(bitmap, OnDiskBitmap):
                    rgb = bitmap.pixels[3 * index:3 * index + 3]
                else:
                    color_index = bitmap.pixels[index]
                    if color_index in node.palette.transparent:
                        continue
                    color = node.palette[color_index]
                    rgb = bytes((color >> 16, (color >> 8) & 255, color & 255))
                dest = (ty * 320 + tx) * 3
                result[dest:dest + 3] = rgb
    draw(group)
    subprocess.run(['magick', '-size', '320x240', '-depth', '8', 'rgb:-', str(filename)], input=result, check=True)


if __name__ == '__main__':
    display = types.SimpleNamespace(root_group=None)
    ui = LCARSScreen(display, str(ROOT / 'CIRCUITPY/lcars'))
    link = HomeKitLink(None)
    # Synthetic display-only credentials, never the board's real codes.
    link.feed(b'PYC1 STATE READY 25496837 PyPortal-ABC123 demoPass2345\nPYC1 CAPS HOLD\n', 10)
    ui.status(link, 10)
    ui.feedback.text = 'AWAITING COMMAND'
    render(ui.main, ROOT / 'design/lcars-main.png')
    ui.show_progress(1, .65)
    ui.feedback.text = 'BUTTON 1 / HOLDING'
    render(ui.main, ROOT / 'design/lcars-hold.png')
    ui.show_setup(True)
    render(ui.setup, ROOT / 'design/lcars-setup.png')
    for state in ('BOOT', 'NO_WIFI', 'CONNECTING', 'PAIR', 'WAIT_HOME', 'READY', 'SETUP', 'FAULT'):
        link.state = state
        ui.status(link, 10)
    for point, expected in (((100, 135, 1), 1), ((240, 135, 1), 2), ((32, 180, 1), 3), ((65, 135, 1), 0)):
        ui.show_setup(False)
        assert ui.target(point) == expected
    ui.show_setup(True)
    assert ui.target((150, 185, 1)) == 4
    print('Both pages, hold feedback, all link states, and touch targets rendered successfully.')
