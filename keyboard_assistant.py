"""Windows keyboard assistance; text-entry actions require explicit confirmation."""

import pyautogui

from action_executor import ActionExecutor
from models import ActionProposal, ExecutionResult


class KeyboardAssistant:
    @staticmethod
    def open_on_screen_keyboard() -> None:
        pyautogui.hotkey("win", "ctrl", "o")

    @staticmethod
    def type_text(executor: ActionExecutor, text: str, confirmed: bool) -> ExecutionResult:
        return executor.execute(
            ActionProposal(
                action="type_text",
                text=text,
                requires_confirmation=True,
            ),
            confirmed=confirmed,
        )
