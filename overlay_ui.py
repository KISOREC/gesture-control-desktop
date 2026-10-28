"""Compact, local-only assistant status overlay drawn on the camera preview."""

from typing import Optional

import cv2
import numpy as np

from models import ScreenElement


def draw_assistant_overlay(
    frame: np.ndarray,
    gesture: str,
    target: Optional[ScreenElement],
    status: str,
    local_only: bool = True,
) -> np.ndarray:
    height, width = frame.shape[:2]
    panel_height = min(112, height)
    panel = frame[height - panel_height:height, 0:width]
    shade = np.zeros_like(panel)
    cv2.addWeighted(panel, 0.3, shade, 0.7, 0, panel)

    target_text = "No target inspected"
    if target is not None:
        target_text = f"Target: {target.label[:70]} ({target.role}, {target.confidence:.0%})"
    lines = (
        f"Gesture: {gesture[:70]}",
        target_text,
        f"Assistant: {status[:90]} | {'LOCAL ONLY' if local_only else 'NETWORK DISABLED'}",
        "Keys: I inspect target | T type command | V push-to-talk | Q emergency stop/quit",
    )
    for index, text in enumerate(lines):
        cv2.putText(
            frame,
            text,
            (10, height - panel_height + 24 + index * 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (100, 255, 220),
            1,
            cv2.LINE_AA,
        )
    return frame
