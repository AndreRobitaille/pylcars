"""Small, bounded UART protocol for the HomeKit coprocessor."""

STATES = ("BOOT", "NO_WIFI", "CONNECTING", "PAIR", "WAIT_HOME", "READY", "SETUP")


def _ascii_alnum(value):
    # CircuitPython does not provide str.isalnum() on the PyPortal.
    for char in value:
        if not ("0" <= char <= "9" or "A" <= char <= "Z" or "a" <= char <= "z"):
            return False
    return bool(value)


class HomeKitLink:
    def __init__(self, uart):
        self.uart = uart
        self.state = "BOOT"
        self.last_seen = -999.0
        self.pairing_code = ""
        self.ap_ssid = ""
        self.ap_password = ""
        self.error = ""
        self.sequence = 0
        self.replies = []
        self.buffer = bytearray()
        self.discard = False
        self.caps_seen = -999.0

    def fresh(self, now):
        return now - self.last_seen < 5.0

    def ready(self, now):
        return self.fresh(now) and self.state == "READY"

    def send(self, command):
        payload = ("PYC1 " + command + "\n").encode()
        if self.uart.write(payload) != len(payload):
            raise OSError("UART write incomplete")

    def can_hold(self, now):
        return self.fresh(now) and now - self.caps_seen < 5.0

    def press(self, button, event=0):
        if button not in (1, 2):
            raise ValueError("Unknown button")
        if event not in (0, 2):
            raise ValueError("Unknown press type")
        self.sequence = self.sequence % 4294967295 + 1
        self.send("%s %d %d" % ("HOLD" if event == 2 else "PRESS", self.sequence, button))
        return self.sequence

    def take_reply(self, sequence):
        for i, item in enumerate(self.replies):
            if item[1] == sequence:
                return self.replies.pop(i)[0]
        return None

    def receive(self, now):
        available = self.uart.in_waiting
        if available:
            self.feed(self.uart.read(min(available, 512)) or b"", now)

    def feed(self, data, now):
        for byte in data:
            if byte == 13:
                continue
            if byte == 10:
                if not self.discard and self.buffer:
                    try:
                        self._line(self.buffer.decode(), now)
                    except (UnicodeError, ValueError):
                        pass
                self.buffer = bytearray()
                self.discard = False
            elif not self.discard:
                if byte < 32 or byte > 126 or len(self.buffer) >= 192:
                    self.buffer = bytearray()
                    self.discard = True
                else:
                    self.buffer.append(byte)

    def _line(self, line, now):
        parts = line.split()
        if len(parts) < 3 or parts[0] != "PYC1":
            return
        if parts == ["PYC1", "CAPS", "HOLD"]:
            self.caps_seen = now
        elif parts[1] == "STATE" and len(parts) == 6:
            _, _, state, code, ssid, password = parts
            if (state not in STATES or len(code) != 8 or not code.isdigit()
                    or not ssid.startswith("PyPortal-") or len(ssid) > 24
                    or len(password) != 12 or not _ascii_alnum(password)):
                return
            self.state = state
            self.pairing_code = code
            self.ap_ssid = ssid
            self.ap_password = password
            self.last_seen = now
        elif parts[1] in ("ACK", "ERROR", "OFFLINE") and len(parts) == 3:
            if not parts[2].isdigit() or len(parts[2]) > 10:
                return
            seq = int(parts[2])
            if 0 < seq <= 4294967295:
                self.replies.append((parts[1], seq))
                self.replies = self.replies[-4:]
        elif parts[1] == "FATAL" and len(parts) == 3:
            self.state = "FAULT"
            self.error = parts[2]
            self.last_seen = now
