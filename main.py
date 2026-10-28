"""Gesture-controlled mouse and local desktop-assistant entry point."""

import queue
import threading
import time
from typing import Optional, Tuple

import cv2
import mediapipe as mp
import pyautogui

from action_executor import ActionExecutor, ActionValidationError
from assistant_engine import AssistantEngine
from config import AppConfig
from cursor_controller import CursorController
from keyboard_assistant import KeyboardAssistant
from models import ActionProposal, ScreenElement
from overlay_ui import draw_assistant_overlay
from screen_understanding import ScreenUnderstanding, ScreenUnderstandingWorker
from voice_assistant import VoiceAssistant


mp_hands = mp.solutions.hands
_FINGER_TIP_PIP = (
    (mp_hands.HandLandmark.INDEX_FINGER_TIP, mp_hands.HandLandmark.INDEX_FINGER_PIP),
    (mp_hands.HandLandmark.MIDDLE_FINGER_TIP, mp_hands.HandLandmark.MIDDLE_FINGER_PIP),
    (mp_hands.HandLandmark.RING_FINGER_TIP, mp_hands.HandLandmark.RING_FINGER_PIP),
    (mp_hands.HandLandmark.PINKY_TIP, mp_hands.HandLandmark.PINKY_PIP),
)


def detect_click_gestures(landmarks) -> Tuple[bool, bool]:
    index_up = landmarks[mp_hands.HandLandmark.INDEX_FINGER_TIP].y < landmarks[mp_hands.HandLandmark.INDEX_FINGER_PIP].y
    middle_up = landmarks[mp_hands.HandLandmark.MIDDLE_FINGER_TIP].y < landmarks[mp_hands.HandLandmark.MIDDLE_FINGER_PIP].y
    ring_down = landmarks[mp_hands.HandLandmark.RING_FINGER_TIP].y > landmarks[mp_hands.HandLandmark.RING_FINGER_PIP].y
    pinky_down = landmarks[mp_hands.HandLandmark.PINKY_TIP].y > landmarks[mp_hands.HandLandmark.PINKY_PIP].y
    peace_sign = index_up and middle_up and ring_down and pinky_down
    fist = all(
        landmarks[tip].y > landmarks[pip].y
        for tip, pip in _FINGER_TIP_PIP
    )
    return peace_sign, fist


def detect_keyboard_gestures(landmarks, palm_width: float) -> Tuple[bool, bool]:
    extended = tuple(landmarks[tip].y < landmarks[pip].y for tip, pip in _FINGER_TIP_PIP)
    three_fingers = extended[0] and extended[1] and extended[2] and not extended[3]

    thumb_tip = landmarks[mp_hands.HandLandmark.THUMB_TIP]
    index_mcp = landmarks[mp_hands.HandLandmark.INDEX_FINGER_MCP]
    thumb_to_palm_distance = ((thumb_tip.x - index_mcp.x) ** 2 + (thumb_tip.y - index_mcp.y) ** 2) ** 0.5
    thumb_folded = palm_width > 0 and thumb_to_palm_distance < palm_width * 0.75
    four_finger_click = all(extended) and thumb_folded
    return three_fingers, four_finger_click


def should_move_cursor(landmarks, dragging: bool) -> bool:
    if dragging:
        return True
    extended = tuple(landmarks[tip].y < landmarks[pip].y for tip, pip in _FINGER_TIP_PIP)
    return extended[0] and not any(extended[1:])


def update_mouse_button(pinch_active: bool, is_pressed: bool) -> bool:
    if pinch_active and not is_pressed:
        pyautogui.mouseDown(button="left")
        return True
    if not pinch_active and is_pressed:
        pyautogui.mouseUp(button="left")
        return False
    return is_pressed


def update_click_gesture(gesture_active: bool, was_active: bool, button: str) -> bool:
    if gesture_active and not was_active:
        if button == "left":
            pyautogui.doubleClick(button="left", interval=0.1)
        elif button == "right":
            pyautogui.click(button="right")
        else:
            raise ValueError(f"Unsupported click button: {button}")
    return gesture_active


def update_keyboard_gesture(gesture_active: bool, was_active: bool, frame_count: int) -> Tuple[bool, int]:
    if not gesture_active:
        return False, 0
    frame_count = min(frame_count + 1, 3)
    confirmed = frame_count >= 3
    if confirmed and not was_active:
        KeyboardAssistant.open_on_screen_keyboard()
        print("Sent Win+Ctrl+O to open the Windows On-Screen Keyboard.")
    return confirmed, frame_count


def update_keyboard_click_gesture(gesture_active: bool, was_active: bool) -> bool:
    if gesture_active and not was_active:
        pyautogui.click(button="left")
    return gesture_active


class GestureDesktopAssistant:
    def __init__(self, config: AppConfig):
        self.config = config
        self.screen = ScreenUnderstanding()
        self.screen_worker = ScreenUnderstandingWorker(self.screen)
        self.engine = AssistantEngine(self.screen)
        self.executor = ActionExecutor()
        self.cursor = CursorController(config.cursor_sensitivity)
        self.voice = VoiceAssistant(config.voice_model_path, self._enqueue_command)
        self.command_queue: queue.Queue[str] = queue.Queue(maxsize=8)
        self.stop_input = threading.Event()
        self.last_cursor: Optional[Tuple[int, int]] = None
        self.cursor_still_since = time.monotonic()
        self.last_screen_request = 0.0
        self.current_target: Optional[ScreenElement] = None
        self.status = "Local assistant ready. Type a command in the console."
        self.pending_action: Optional[ActionProposal] = None
        self.left_button_pressed = False
        self.peace_sign_active = False
        self.fist_active = False
        self.keyboard_gesture_active = False
        self.keyboard_gesture_frames = 0
        self.four_finger_click_active = False
        self.previous_swipe_x: Optional[int] = None
        self.previous_swipe_y: Optional[int] = None

    def _enqueue_command(self, command: str) -> None:
        try:
            self.command_queue.put_nowait(command)
        except queue.Full:
            print("Assistant command queue is full; command discarded.")

    def _read_console_commands(self) -> None:
        while not self.stop_input.is_set():
            try:
                command = input("\nAssistant command (or 'cancel'): ")
            except EOFError:
                return
            self._enqueue_command(command)

    def _process_command(self, command: str, cursor_position: Tuple[int, int]) -> None:
        lowered = command.strip().casefold()
        if lowered in {"cancel", "cancel action", "stop"}:
            self.pending_action = None
            self.status = "Pending action cancelled."
            return

        if lowered == "confirm":
            if self.pending_action is None:
                self.status = "There is no pending action to confirm."
                return
            try:
                result = self.executor.execute(self.pending_action, confirmed=True)
            except ActionValidationError as exc:
                self.status = f"Action rejected: {exc}"
                print(self.status)
            else:
                self.status = result.message
            self.pending_action = None
            return

        try:
            reply = self.engine.handle(command, cursor_position)
        except Exception as exc:
            self.status = f"Assistant error: {exc}"
            print(self.status)
            return

        self.status = reply.message
        print(self.status)
        for choice in reply.choices:
            print(f"  - {choice}")
        if reply.proposal is None:
            return
        if reply.proposal.requires_confirmation:
            self.pending_action = reply.proposal
            return
        try:
            result = self.executor.execute(reply.proposal)
        except ActionValidationError as exc:
            self.status = f"Action rejected: {exc}"
            print(self.status)
        else:
            self.status = result.message
            print(self.status)

    def _handle_commands(self, cursor_position: Tuple[int, int]) -> None:
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                return
            if self.voice.error:
                self.status = self.voice.error
                print(self.status)
                self.voice.error = None
            self._process_command(command, cursor_position)

    def _inspect_cursor(self, position: Tuple[int, int], now: float) -> None:
        if now - self.last_screen_request < self.config.screen_analysis_interval:
            return
        self.screen_worker.submit(*position)
        self.last_screen_request = now

    def run(self) -> None:
        cap = cv2.VideoCapture(0)
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )
        drawing = mp.solutions.drawing_utils
        if not cap.isOpened():
            hands.close()
            cap.release()
            raise RuntimeError("Could not open camera. Check camera access and close other apps using it.")

        self.screen_worker.start()
        threading.Thread(
            target=self._read_console_commands,
            name="assistant-console-input",
            daemon=True,
        ).start()
        print("Gesture desktop assistant started. Press q in the camera window for emergency stop.")
        print("Commands: click <label>, where am I pointing, scroll up/down, volume up/down, go back, type <text>.")
        print("Press i to inspect, v to start/stop local push-to-talk (requires VOSK_MODEL_PATH), q to quit.")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    raise RuntimeError("Camera stopped returning frames.")

                frame = cv2.flip(frame, 1)
                results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                left_hand_seen = False
                gesture_status = "No hand"
                now = time.monotonic()

                if results.multi_hand_landmarks:
                    for hand_index, landmarks in enumerate(results.multi_hand_landmarks):
                        drawing.draw_landmarks(frame, landmarks, mp_hands.HAND_CONNECTIONS)
                        handedness = results.multi_handedness[hand_index].classification[0].label
                        points = landmarks.landmark
                        index_tip = points[mp_hands.HandLandmark.INDEX_FINGER_TIP]

                        if handedness == "Left":
                            left_hand_seen = True
                            index_mcp = points[mp_hands.HandLandmark.INDEX_FINGER_MCP]
                            pinky_mcp = points[mp_hands.HandLandmark.PINKY_MCP]
                            thumb_tip = points[mp_hands.HandLandmark.THUMB_TIP]
                            palm_width = ((index_mcp.x - pinky_mcp.x) ** 2 + (index_mcp.y - pinky_mcp.y) ** 2) ** 0.5
                            peace_sign, fist = detect_click_gestures(points)
                            three_fingers, four_finger_click = detect_keyboard_gestures(points, palm_width)
                            pinch_ratio = float("inf")
                            if palm_width > 0:
                                pinch_ratio = (
                                    ((thumb_tip.x - index_tip.x) ** 2 + (thumb_tip.y - index_tip.y) ** 2) ** 0.5
                                ) / palm_width
                            index_pinch_candidate = pinch_ratio < 0.45
                            left_pinch = pinch_ratio < (0.45 if self.left_button_pressed else 0.3)
                            self.left_button_pressed = update_mouse_button(left_pinch, self.left_button_pressed)

                            if should_move_cursor(points, self.left_button_pressed):
                                position = self.cursor.move_to_normalized(
                                    min(1.0, max(0.0, index_tip.x)),
                                    min(1.0, max(0.0, index_tip.y)),
                                )
                                if self.last_cursor is None or abs(position[0] - self.last_cursor[0]) + abs(position[1] - self.last_cursor[1]) > 6:
                                    self.cursor_still_since = now
                                self.last_cursor = position
                                gesture_status = "Dragging" if self.left_button_pressed else "Index-only cursor"
                                if now - self.cursor_still_since >= self.config.dwell_seconds:
                                    self._inspect_cursor(position, now)

                            self.peace_sign_active = update_click_gesture(
                                peace_sign and not index_pinch_candidate,
                                self.peace_sign_active,
                                "left",
                            )
                            self.fist_active = update_click_gesture(
                                fist and not index_pinch_candidate,
                                self.fist_active,
                                "right",
                            )
                            self.keyboard_gesture_active, self.keyboard_gesture_frames = update_keyboard_gesture(
                                three_fingers and not index_pinch_candidate,
                                self.keyboard_gesture_active,
                                self.keyboard_gesture_frames,
                            )
                            self.four_finger_click_active = update_keyboard_click_gesture(
                                four_finger_click and not index_pinch_candidate,
                                self.four_finger_click_active,
                            )
                            if self.keyboard_gesture_active:
                                gesture_status = "Three-finger keyboard shortcut"
                            elif self.four_finger_click_active:
                                gesture_status = "Four-finger key click"
                            elif self.peace_sign_active:
                                gesture_status = "Peace-sign double click"
                            elif self.fist_active:
                                gesture_status = "Fist right click"
                            if pinch_ratio < 0.45:
                                gesture_status = "Pinch drag" if self.left_button_pressed else "Pinch detected"

                        elif handedness == "Right":
                            x, y = int(index_tip.x * self.cursor.screen_width), int(index_tip.y * self.cursor.screen_height)
                            if self.previous_swipe_x is not None and self.previous_swipe_y is not None:
                                dx, dy = x - self.previous_swipe_x, y - self.previous_swipe_y
                                if abs(dx) > abs(dy):
                                    if dx > 50:
                                        pyautogui.press("right")
                                    elif dx < -50:
                                        pyautogui.press("left")
                                elif dy > 50:
                                    pyautogui.press("down")
                                elif dy < -50:
                                    pyautogui.press("up")
                            self.previous_swipe_x, self.previous_swipe_y = x, y
                            gesture_status = "Right-hand navigation"

                if not left_hand_seen:
                    self.left_button_pressed = update_mouse_button(False, self.left_button_pressed)
                    self.peace_sign_active = False
                    self.fist_active = False
                    self.keyboard_gesture_active = False
                    self.keyboard_gesture_frames = 0
                    self.four_finger_click_active = False
                    self.cursor_still_since = now

                inspection = self.screen_worker.latest()
                if inspection.element:
                    self.current_target = inspection.element
                self._handle_commands(pyautogui.position())
                if self.pending_action:
                    self.status = "Confirmation required; type 'confirm' or 'cancel' in the console."

                frame = draw_assistant_overlay(
                    frame,
                    gesture_status,
                    self.current_target,
                    self.status,
                    local_only=self.config.local_only,
                )
                cv2.imshow("Gesture Desktop Assistant", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("i"):
                    self._inspect_cursor(pyautogui.position(), now)
                if key == ord("v"):
                    if self.voice.listening:
                        self.voice.stop_push_to_talk()
                        self.status = "Local voice capture stopped."
                    else:
                        try:
                            self.voice.start_push_to_talk()
                            self.status = "Listening locally; press v again to stop."
                        except RuntimeError as exc:
                            self.status = str(exc)
                            print(self.status)
        finally:
            self.stop_input.set()
            self.voice.stop_push_to_talk()
            self.screen_worker.stop()
            if self.left_button_pressed:
                pyautogui.mouseUp(button="left")
            cap.release()
            hands.close()
            cv2.destroyAllWindows()


def main() -> None:
    config = AppConfig.from_environment()
    GestureDesktopAssistant(config).run()


if __name__ == "__main__":
    main()
