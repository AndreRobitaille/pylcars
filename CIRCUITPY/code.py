# PyPortal LCARS controller 0.3.0. Runs on the two onboard processors.
# Confirmations describe sent commands, not the lamp's actual state.
import time
import board
import busio
import digitalio
import adafruit_touchscreen
from pyportal_wire import HomeKitLink
from pyportal_touch import TouchGesture
from lcars_ui import LCARSScreen

display = board.DISPLAY
display.rotation = 0
display.brightness = 0.8
ui = LCARSScreen(display)
touch = adafruit_touchscreen.Touchscreen(
    board.TOUCH_XL, board.TOUCH_XR, board.TOUCH_YD, board.TOUCH_YU,
    calibration=((5200, 59000), (5800, 57000)), size=(320, 240))
gesture = TouchGesture()

esp_cs = digitalio.DigitalInOut(board.ESP_CS)
esp_cs.switch_to_output(value=True)
esp_boot = digitalio.DigitalInOut(board.ESP_GPIO0)
esp_boot.switch_to_output(value=True)
esp_reset = digitalio.DigitalInOut(board.ESP_RESET)
esp_reset.switch_to_output(value=False)
uart = busio.UART(board.ESP_TX, board.ESP_RX, baudrate=115200,
                  timeout=0, receiver_buffer_size=2048)
link = HomeKitLink(uart)
time.sleep(0.1)
esp_reset.value = True

pending = None
last_query = -10.0
last_screen_update = -10.0
previous_state = 'BOOT'
print('PyPortal LCARS controller 0.3.0. Setup codes appear only on the screen.')

while True:
    now = time.monotonic()
    link.receive(now)
    if now - last_query >= 2:
        try:
            link.send('STATUS')
        except OSError:
            ui.feedback.text = 'CONTROLLER NOT RESPONDING'
        last_query = now

    if now - last_screen_update >= 0.2:
        ui.status(link, now)
        if link.state != previous_state:
            if link.state in ('SETUP', 'PAIR'):
                ui.show_setup(True)
                gesture.cancel()
            elif link.state == 'READY':
                ui.show_setup(False)
                gesture.cancel()
                ui.feedback.text = 'AWAITING COMMAND'
            previous_state = link.state
        last_screen_update = now

    if pending:
        sequence, description, started = pending
        reply = link.take_reply(sequence)
        if reply:
            ui.feedback.text = description + ' / SENT' if reply == 'ACK' else 'NOT SENT / CHECK HOME LINK'
            pending = None
        elif now - started > 3:
            ui.feedback.text = 'NO CONFIRMATION / TRY AGAIN'
            pending = None

    point = touch.touch_point
    action = gesture.update(ui.target(point), point is not None, now)
    ui.show_progress(gesture.button, gesture.progress(now))
    if action:
        button, event = action
        if button == 3:
            ui.show_setup(not ui.showing_setup)
        elif button == 4:
            if link.fresh(now):
                try:
                    link.send('EXIT' if link.state == 'SETUP' else 'SETUP')
                    ui.setup_status.text = 'PLEASE WAIT'
                except OSError:
                    ui.setup_status.text = 'CONTROLLER NOT RESPONDING'
        elif button in (1, 2):
            if not link.ready(now):
                ui.feedback.text = 'CONNECT APPLE HOME FIRST'
            elif pending:
                ui.feedback.text = 'AWAITING CONFIRMATION'
            elif event == 2 and not link.can_hold(now):
                ui.feedback.text = 'LONG PRESS / UPDATE REQUIRED'
            else:
                try:
                    sequence = link.press(button, event)
                    description = ('BUTTON %d HOLD' % button) if event == 2 else ('ON COMMAND' if button == 1 else 'OFF COMMAND')
                    pending = (sequence, description, now)
                    ui.feedback.text = description + ' / SENDING'
                except OSError:
                    ui.feedback.text = 'COMMAND NOT SENT'
    time.sleep(0.02)
