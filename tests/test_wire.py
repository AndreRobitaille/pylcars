import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CIRCUITPY' / 'lib'))
from pyportal_wire import HomeKitLink


class UART:
    def __init__(self):
        self.sent = []

    def write(self, data):
        self.sent.append(data)
        return len(data)


class CircuitPythonString(str):
    """Reproduce the missing method reported by the real PyPortal."""
    def split(self):
        return [CircuitPythonString(value) for value in super().split()]

    def isalnum(self):
        raise AttributeError("'str' object has no attribute 'isalnum'")


class WireTests(unittest.TestCase):
    def setUp(self):
        self.uart = UART()
        self.link = HomeKitLink(self.uart)

    def test_ready_requires_recent_complete_valid_status(self):
        packet = b'PYC1 STATE READY 25496837 PyPortal-ABC123 abcdefgh2345\n'
        self.link.feed(packet[:20], 10)
        self.assertFalse(self.link.ready(10))
        self.link.feed(packet[20:], 10)
        self.assertTrue(self.link.ready(14.9))
        self.assertFalse(self.link.ready(15))
        self.link.feed(b'PYC1 STATE READY INVALID PyPortal-ABC123 abcdefgh2345\n', 20)
        self.assertFalse(self.link.ready(20))

    def test_noise_and_oversized_frames_do_not_create_events(self):
        self.link.feed(b'x' * 250 + b'PYC1 ACK 1\n', 1)
        self.assertIsNone(self.link.take_reply(1))
        self.link.feed(b'\x00PYC1 ACK 1\nPYC1 ACK 2\r\n', 2)
        self.assertIsNone(self.link.take_reply(1))
        self.assertEqual(self.link.take_reply(2), 'ACK')

    def test_status_parses_without_optional_string_method(self):
        line = CircuitPythonString('PYC1 STATE SETUP 25496837 PyPortal-ABC123 aB3dE6gH9jK2')
        self.link._line(line, 10)
        self.assertEqual(self.link.state, 'SETUP')
        self.assertEqual(self.link.ap_password, 'aB3dE6gH9jK2')
        self.assertTrue(self.link.fresh(10))

    def test_invalid_password_does_not_update_status(self):
        for password in ('', 'short', 'aB3dE6gH9jK2X', 'aB3dE6gH9jK!', 'aB3dE6gH9jK_', 'aB3dE6gH9jKé'):
            with self.subTest(password=password):
                self.link.feed(('PYC1 STATE SETUP 25496837 PyPortal-ABC123 ' + password + '\n').encode(), 10)
                self.assertEqual(self.link.state, 'BOOT')
                self.assertFalse(self.link.fresh(10))
                self.assertEqual(self.link.ap_password, '')

    def test_reply_is_matched_once_and_does_not_imply_connection(self):
        self.link.feed(b'PYC1 ACK 25\nPYC1 OFFLINE 26\n', 5)
        self.assertIsNone(self.link.take_reply(24))
        self.assertEqual(self.link.take_reply(25), 'ACK')
        self.assertIsNone(self.link.take_reply(25))
        self.assertEqual(self.link.take_reply(26), 'OFFLINE')
        self.assertFalse(self.link.ready(5))

    def test_button_ids_and_sequence_wrap(self):
        self.assertEqual(self.link.press(1), 1)
        self.assertEqual(self.uart.sent[-1], b'PYC1 PRESS 1 1\n')
        with self.assertRaises(ValueError):
            self.link.press(0)
        self.link.sequence = 4294967295
        self.assertEqual(self.link.press(2), 1)

    def test_hold_capability_expires_and_uses_distinct_command(self):
        self.assertFalse(self.link.can_hold(10))
        self.link.feed(b'PYC1 STATE READY 25496837 PyPortal-ABC123 abcdefgh2345\nPYC1 CAPS HOLD\n', 10)
        self.assertTrue(self.link.can_hold(14.9))
        self.assertFalse(self.link.can_hold(15))
        self.assertEqual(self.link.press(2, 2), 1)
        self.assertEqual(self.uart.sent[-1], b'PYC1 HOLD 1 2\n')
        with self.assertRaises(ValueError):
            self.link.press(1, 1)


if __name__ == '__main__':
    unittest.main()
