"""Smoothed cursor mapping for normalized hand coordinates."""

from typing import Optional, Tuple

import pyautogui


class CursorController:
    def __init__(self, sensitivity: float = 1.0, screen_size: Optional[Tuple[int, int]] = None):
        self.screen_width, self.screen_height = screen_size or pyautogui.size()
        self.sensitivity = sensitivity
        self._position: Optional[Tuple[float, float]] = None
        self._smoothing = min(0.85, max(0.2, 0.35 * sensitivity))

    def move_to_normalized(self, x: float, y: float) -> Tuple[int, int]:
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ValueError("Normalized cursor coordinates must be between 0 and 1.")

        target = (
            x * (self.screen_width - 1),
            y * (self.screen_height - 1),
        )
        if self._position is None:
            self._position = target
        else:
            self._position = tuple(
                old + (new - old) * self._smoothing
                for old, new in zip(self._position, target)
            )
        position = (round(self._position[0]), round(self._position[1]))
        pyautogui.moveTo(*position)
        return position
