"""Validate and execute a deliberately small allowlist of desktop actions."""

from typing import FrozenSet, Optional, Tuple

import pyautogui

from models import ActionProposal, ExecutionResult


class ActionValidationError(ValueError):
    """Raised when a proposed desktop action is not safe or valid."""


class ActionExecutor:
    _KEYS: FrozenSet[str] = frozenset({
        "enter", "esc", "tab", "backspace", "delete", "space",
        "up", "down", "left", "right", "home", "end", "volumeup",
        "volumedown", "volumemute",
    })
    _HOTKEYS = {
        "go_back": ("alt", "left"),
        "next_tab": ("ctrl", "tab"),
        "previous_tab": ("ctrl", "shift", "tab"),
        "maximize": ("win", "up"),
    }

    def __init__(self, screen_size: Optional[Tuple[int, int]] = None):
        self.screen_size = screen_size or pyautogui.size()

    def execute(
        self,
        proposal: ActionProposal,
        confirmed: bool = False,
    ) -> ExecutionResult:
        if proposal.requires_confirmation and not confirmed:
            return ExecutionResult(False, "Confirmation is required before this action.")

        action = proposal.action
        if action in {"click", "double_click", "right_click"}:
            x, y = self._validate_point(proposal.x, proposal.y)
            pyautogui.moveTo(x, y)
            if action == "click":
                pyautogui.click(x=x, y=y)
            elif action == "double_click":
                pyautogui.doubleClick(x=x, y=y, interval=0.1)
            else:
                pyautogui.click(x=x, y=y, button="right")
            return ExecutionResult(True, f"{action.replace('_', ' ').title()} at {proposal.target_label or 'target'}.")

        if action == "scroll":
            if proposal.amount not in {-10, -5, 5, 10}:
                raise ActionValidationError("Scroll amount must be one of -10, -5, 5, or 10.")
            pyautogui.scroll(proposal.amount)
            return ExecutionResult(True, "Scrolled.")

        if action == "press_key":
            key = (proposal.key or "").lower()
            if key not in self._KEYS:
                raise ActionValidationError(f"Key is not allowlisted: {key!r}.")
            pyautogui.press(key)
            return ExecutionResult(True, f"Pressed {key}.")

        if action == "hotkey":
            chord = self._HOTKEYS.get(proposal.key or "")
            if chord is None:
                raise ActionValidationError("Hotkey is not allowlisted.")
            pyautogui.hotkey(*chord)
            return ExecutionResult(True, f"Executed {proposal.key.replace('_', ' ')}.")

        if action == "type_text":
            if not proposal.text:
                raise ActionValidationError("Text to type must not be empty.")
            if len(proposal.text) > 500:
                raise ActionValidationError("Text entry is limited to 500 characters.")
            pyautogui.write(proposal.text, interval=0.02)
            return ExecutionResult(True, "Typed the confirmed text.")

        raise ActionValidationError(f"Action is not allowlisted: {action!r}.")

    def _validate_point(self, x: Optional[int], y: Optional[int]) -> Tuple[int, int]:
        width, height = self.screen_size
        if x is None or y is None:
            raise ActionValidationError("A screen coordinate is required.")
        if not (0 <= x < width and 0 <= y < height):
            raise ActionValidationError("Screen coordinate is outside the display bounds.")
        return x, y
