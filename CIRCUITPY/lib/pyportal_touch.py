"""Debounced taps and holds for the resistive touchscreen."""


class TouchGesture:
    def __init__(self, hold_seconds=0.8, release_seconds=0.12):
        self.hold_seconds = hold_seconds
        self.release_seconds = release_seconds
        self.active = False
        self.button = 0
        self.started = 0.0
        self.last_touch = 0.0
        self.sent = False
        self.cancelled = False

    def cancel(self):
        # Require a full release before accepting a touch on a new page.
        if self.active:
            self.cancelled = True

    def progress(self, now):
        if not self.active or self.cancelled or self.button not in (1, 2):
            return 0.0
        return min(1.0, max(0.0, (now - self.started) / self.hold_seconds))

    def update(self, button, touching, now):
        if touching:
            if not self.active:
                self.active = True
                self.button = button
                self.started = now
                self.sent = False
                self.cancelled = button == 0
            elif button != self.button:
                self.cancelled = True
            self.last_touch = now
            if (not self.cancelled and not self.sent and self.button in (1, 2)
                    and now - self.started >= self.hold_seconds):
                self.sent = True
                return (self.button, 2)
        elif self.active and now - self.last_touch >= self.release_seconds:
            self.active = False
            if not self.sent and not self.cancelled:
                self.sent = True
                return (self.button, 0)
        return None
