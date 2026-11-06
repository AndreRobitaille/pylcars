"""Native 320x240 LCARS display. No external computer required."""
import struct
import displayio

GOLD = 0xFFCC66
PEACH = 0xFFCC99
LILAC = 0xCC99CC
BLUE = 0x9999CC
WHITE = 0xFFF4E5
ORANGE = 0xFF9966


class AtlasFont:
    def __init__(self, path):
        with open(path, 'rb') as source:
            width, height, self.cellw, self.cellh = struct.unpack('<HHBB', source.read(6))
            self.advances = source.read(95)
            self.bitmap = displayio.Bitmap(width, height, 2)
            pixel = 0
            while True:
                chunk = source.read(256)
                if not chunk:
                    break
                for byte in chunk:
                    for bit in range(7, -1, -1):
                        if byte & (1 << bit):
                            self.bitmap[pixel % width, pixel // width] = 1
                        pixel += 1


class Text(displayio.Group):
    def __init__(self, font, value, x, y, color=PEACH, max_width=228, center=False):
        super().__init__(x=x, y=y)
        self.font = font
        self.palette = displayio.Palette(2)
        self.palette.make_transparent(0)
        self.palette[1] = color
        self.max_width = max_width
        self.center = center
        self._text = None
        self.text = value

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        if value == self._text:
            return
        self._text = value
        while len(self):
            self.pop()
        glyphs = []
        width = 0
        for char in value:
            index = ord(char) - 32
            if not 0 <= index < 95:
                index = ord('?') - 32
            advance = self.font.advances[index]
            if width + advance > self.max_width:
                break
            glyphs.append((index, width))
            width += advance
        offset = -width // 2 if self.center else 0
        for index, position in glyphs:
            self.append(displayio.TileGrid(
                self.font.bitmap, pixel_shader=self.palette,
                tile_width=self.font.cellw, tile_height=self.font.cellh,
                default_tile=index, x=offset + position, y=0))

    @property
    def color(self):
        return self.palette[1]

    @color.setter
    def color(self, value):
        self.palette[1] = value


class LCARSScreen:
    def __init__(self, display, asset_root='/lcars'):
        self.display = display
        self.small = AtlasFont(asset_root + '/antonio12.bin')
        self.medium = AtlasFont(asset_root + '/antonio16.bin')
        self.large = AtlasFont(asset_root + '/antonio24.bin')
        self.main = displayio.Group()
        self.setup = displayio.Group()
        for group, name in ((self.main, 'main'), (self.setup, 'setup')):
            bitmap = displayio.OnDiskBitmap(asset_root + '/' + name + '.bmp')
            group.append(displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader))
        self.network = self.add(self.main, self.small, 'HOME LINK / STARTING', 76, 83, BLUE)
        self.feedback = self.add(self.main, self.small, 'AWAITING CONNECTION', 76, 188, PEACH)
        self.hint = self.add(self.main, self.small, 'TAP TO COMMAND', 76, 202, BLUE)
        self.pairing = self.add(self.setup, self.large, 'WAITING', 76, 62, WHITE)
        self.ssid = self.add(self.setup, self.medium, 'WAITING', 76, 99, PEACH)
        self.password = self.add(self.setup, self.medium, 'WAITING', 76, 131, PEACH)
        self.setup_button = self.add(self.setup, self.medium, 'START WI-FI SETUP', 190, 173, 0, center=True)
        self.setup_status = self.add(self.setup, self.small, 'STARTING', 76, 202, BLUE)
        self.progress_bitmap = displayio.Bitmap(110, 3, 2)
        palette = displayio.Palette(2)
        palette.make_transparent(0)
        palette[1] = WHITE
        self.progress_tile = displayio.TileGrid(self.progress_bitmap, pixel_shader=palette, x=76, y=171)
        self.main.append(self.progress_tile)
        self.progress_pixels = -1
        self.showing_setup = False
        self.display.root_group = self.main

    def add(self, group, font, value, x, y, color, center=False):
        item = Text(font, value, x, y, color=color, center=center)
        group.append(item)
        return item

    def show_setup(self, value):
        self.showing_setup = value
        self.display.root_group = self.setup if value else self.main

    def target(self, point):
        if point is None:
            return 0
        x, y, _ = point
        if 8 <= x < 58 and 162 <= y < 202:
            return 3
        if self.showing_setup:
            return 4 if 76 <= x < 304 and 170 <= y < 202 else 0
        if (76 <= x < 186 and 109 <= y < 170) or (8 <= x < 58 and 78 <= y < 115):
            return 1
        if (194 <= x < 304 and 109 <= y < 170) or (8 <= x < 58 and 120 <= y < 157):
            return 2
        return 0

    def show_progress(self, button, fraction):
        pixels = int(fraction * 110) if button in (1, 2) else 0
        self.progress_tile.x = 76 if button == 1 else 194
        if pixels != self.progress_pixels:
            self.progress_bitmap.fill(0)
            for x in range(pixels):
                for y in range(3):
                    self.progress_bitmap[x, y] = 1
            self.progress_pixels = pixels

    def status(self, link, now):
        fresh = link.fresh(now)
        messages = {
            'BOOT': 'HOME LINK / STARTING',
            'NO_WIFI': 'HOME LINK / CONFIGURE WI-FI',
            'CONNECTING': 'HOME LINK / CONNECTING',
            'PAIR': 'HOME LINK / PAIR IN APPLE HOME',
            'WAIT_HOME': 'HOME LINK / WAITING FOR HUB',
            'READY': 'HOME LINK / ONLINE',
            'SETUP': 'WI-FI SETUP / JOIN NETWORK',
            'FAULT': 'HOME LINK / CONTROLLER ERROR',
        }
        message = messages.get(link.state, 'HOME LINK / WAITING') if fresh else 'HOME LINK / NO RESPONSE'
        self.network.text = message
        self.network.color = PEACH if link.ready(now) else ORANGE
        self.setup_status.text = message
        self.hint.text = 'TAP / HOLD 0.8 SEC FOR LONG PRESS' if link.can_hold(now) else 'LONG PRESS / FIRMWARE UPDATE NEEDED'
        if link.pairing_code:
            code = link.pairing_code
            self.pairing.text = code[:3] + '-' + code[3:5] + '-' + code[5:]
            self.ssid.text = link.ap_ssid
            self.password.text = link.ap_password
        self.setup_button.text = 'EXIT WI-FI SETUP' if fresh and link.state == 'SETUP' else 'START WI-FI SETUP'
