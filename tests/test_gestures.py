import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main


def make_landmarks(extended):
    landmarks = [SimpleNamespace(x=0.5, y=0.5) for _ in range(21)]
    finger_pairs = (
        (main.mp_hands.HandLandmark.INDEX_FINGER_TIP, main.mp_hands.HandLandmark.INDEX_FINGER_PIP),
        (main.mp_hands.HandLandmark.MIDDLE_FINGER_TIP, main.mp_hands.HandLandmark.MIDDLE_FINGER_PIP),
        (main.mp_hands.HandLandmark.RING_FINGER_TIP, main.mp_hands.HandLandmark.RING_FINGER_PIP),
        (main.mp_hands.HandLandmark.PINKY_TIP, main.mp_hands.HandLandmark.PINKY_PIP),
    )
    for index, (tip, pip) in enumerate(finger_pairs):
        landmarks[pip] = SimpleNamespace(x=0.5, y=0.5)
        landmarks[tip] = SimpleNamespace(x=0.5, y=0.3 if index in extended else 0.7)
    landmarks[main.mp_hands.HandLandmark.INDEX_FINGER_MCP] = SimpleNamespace(x=0.45, y=0.55)
    landmarks[main.mp_hands.HandLandmark.PINKY_MCP] = SimpleNamespace(x=0.65, y=0.55)
    landmarks[main.mp_hands.HandLandmark.THUMB_TIP] = SimpleNamespace(x=0.48, y=0.53)
    return landmarks


class GestureTests(unittest.TestCase):
    def test_index_only_moves_cursor_and_multifinger_poses_do_not(self):
        self.assertTrue(main.should_move_cursor(make_landmarks({0}), False))
        self.assertFalse(main.should_move_cursor(make_landmarks({0, 1}), False))
        self.assertFalse(main.should_move_cursor(make_landmarks({0, 1, 2}), False))
        self.assertFalse(main.should_move_cursor(make_landmarks({0, 1, 2, 3}), False))
        self.assertTrue(main.should_move_cursor(make_landmarks(set()), True))

    def test_three_fingers_triggers_keyboard_and_four_fingers_click(self):
        three = make_landmarks({0, 1, 2})
        four = make_landmarks({0, 1, 2, 3})
        self.assertEqual(main.detect_keyboard_gestures(three, 0.2), (True, False))
        self.assertEqual(main.detect_keyboard_gestures(four, 0.2), (False, True))

    @patch("main.KeyboardAssistant.open_on_screen_keyboard")
    def test_keyboard_shortcut_debounces_after_three_frames(self, open_keyboard):
        active, count = False, 0
        for _ in range(2):
            active, count = main.update_keyboard_gesture(True, active, count)
            self.assertFalse(active)
        active, count = main.update_keyboard_gesture(True, active, count)
        self.assertTrue(active)
        open_keyboard.assert_called_once_with()
        active, count = main.update_keyboard_gesture(True, active, count)
        open_keyboard.assert_called_once_with()
        active, count = main.update_keyboard_gesture(False, active, count)
        self.assertFalse(active)
        self.assertEqual(count, 0)

    @patch("main.pyautogui")
    def test_click_and_drag_transitions_do_not_repeat_while_held(self, mouse):
        self.assertTrue(main.update_mouse_button(True, False))
        self.assertTrue(main.update_mouse_button(True, True))
        self.assertFalse(main.update_mouse_button(False, True))
        mouse.mouseDown.assert_called_once_with(button="left")
        mouse.mouseUp.assert_called_once_with(button="left")

        self.assertTrue(main.update_keyboard_click_gesture(True, False))
        self.assertTrue(main.update_keyboard_click_gesture(True, True))
        mouse.click.assert_called_once_with(button="left")

    @patch("main.pyautogui")
    def test_peace_double_click_and_fist_right_click_remain_distinct(self, mouse):
        main.update_click_gesture(True, False, "left")
        main.update_click_gesture(True, False, "right")
        mouse.doubleClick.assert_called_once_with(button="left", interval=0.1)
        mouse.click.assert_called_once_with(button="right")


if __name__ == "__main__":
    unittest.main()
