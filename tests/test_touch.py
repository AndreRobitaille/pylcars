import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CIRCUITPY' / 'lib'))
from pyportal_touch import TouchGesture


class GestureTests(unittest.TestCase):
    def test_tap_waits_for_release(self):
        g = TouchGesture()
        self.assertIsNone(g.update(1, True, 0))
        self.assertIsNone(g.update(0, False, .05))
        self.assertEqual(g.update(0, False, .13), (1, 0))
        self.assertIsNone(g.update(0, False, .2))

    def test_hold_sends_once_without_tap(self):
        g = TouchGesture()
        g.update(2, True, 0)
        self.assertIsNone(g.update(2, True, .79))
        self.assertEqual(g.update(2, True, .81), (2, 2))
        self.assertIsNone(g.update(2, True, 3))
        self.assertIsNone(g.update(0, False, 3.2))

    def test_release_before_threshold_does_not_become_hold(self):
        g = TouchGesture()
        g.update(1, True, 0)
        g.update(1, True, .75)
        self.assertIsNone(g.update(0, False, .8))
        self.assertEqual(g.update(0, False, .9), (1, 0))

    def test_brief_contact_loss_does_not_duplicate(self):
        g = TouchGesture()
        g.update(1, True, 0)
        self.assertIsNone(g.update(0, False, .04))
        self.assertIsNone(g.update(1, True, .07))
        self.assertEqual(g.update(1, True, .81), (1, 2))
        self.assertIsNone(g.update(0, False, 1))

    def test_drag_between_buttons_cancels(self):
        g = TouchGesture()
        g.update(1, True, 0)
        g.update(2, True, .2)
        self.assertIsNone(g.update(2, True, 1))
        self.assertIsNone(g.update(0, False, 1.2))

    def test_drag_from_background_and_page_changes_cancel(self):
        g = TouchGesture()
        g.update(0, True, 0)
        g.update(1, True, .2)
        self.assertIsNone(g.update(0, False, .4))
        g.update(1, True, 1)
        g.cancel()
        self.assertIsNone(g.update(0, False, 2))

    def test_setup_control_is_only_a_tap(self):
        g = TouchGesture()
        g.update(3, True, 0)
        self.assertIsNone(g.update(3, True, 2))
        self.assertEqual(g.update(0, False, 2.2), (3, 0))


if __name__ == '__main__':
    unittest.main()
