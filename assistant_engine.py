"""Provider-independent, local command parsing with explicit action proposals."""

import re
from typing import Optional, Protocol, Tuple

from models import ActionProposal, AssistantReply, ScreenElement
from screen_understanding import ScreenUnderstanding


class IntentProvider(Protocol):
    def propose(
        self,
        command: str,
        screen_context: Optional[ScreenElement],
    ) -> Optional[ActionProposal]:
        """Return an untrusted proposal; ActionExecutor must validate it."""


class AssistantEngine:
    def __init__(
        self,
        screen_understanding: ScreenUnderstanding,
        provider: Optional[IntentProvider] = None,
    ):
        self.screen_understanding = screen_understanding
        self.provider = provider

    def handle(self, command: str, cursor: Tuple[int, int]) -> AssistantReply:
        normalized = command.strip()
        if not normalized:
            return AssistantReply("Enter a command.")

        lowered = normalized.casefold()
        if lowered in {"where am i pointing", "what am i pointing at", "identify target"}:
            inspection = self.screen_understanding.inspect_at(*cursor)
            if inspection.element is None:
                details = " ".join(inspection.warnings) or "No accessible element or readable text was found."
                return AssistantReply(f"Target not identified. {details}")
            element = inspection.element
            extra = " Editable field." if element.editable else ""
            return AssistantReply(
                f"Pointing at {element.label} ({element.role}, {element.source}, "
                f"confidence {element.confidence:.0%}).{extra}"
            )

        click_match = re.fullmatch(r"(?:click|select|open)\s+(?:the\s+)?(.+)", lowered)
        if click_match:
            query = click_match.group(1).strip()
            elements, warnings = self.screen_understanding.find_by_label(query)
            actionable = tuple(
                element for element in elements
                if element.visible and element.enabled and element.clickable and element.source == "uia"
            )
            if not actionable:
                reason = "OCR can read text but cannot prove it is safe to click." if elements else "No matching accessible control was found."
                detail = " ".join(warnings)
                return AssistantReply(f"{reason} {detail}".strip())
            if len(actionable) > 1:
                choices = tuple(f"{item.label} ({item.role})" for item in actionable[:5])
                return AssistantReply("More than one control matches; specify which one.", choices=choices)
            target = actionable[0]
            x, y = target.center
            return AssistantReply(
                f"Found {target.label}; propose clicking it.",
                ActionProposal(
                    action="click",
                    x=x,
                    y=y,
                    target_label=target.label,
                ),
            )

        if lowered in {"scroll down", "scroll up"}:
            amount = -5 if lowered == "scroll down" else 5
            return AssistantReply(
                f"Propose {lowered}.",
                ActionProposal(action="scroll", amount=amount),
            )

        if lowered in {"increase volume", "volume up"}:
            return AssistantReply("Propose increasing volume.", ActionProposal(action="press_key", key="volumeup"))
        if lowered in {"decrease volume", "volume down"}:
            return AssistantReply("Propose decreasing volume.", ActionProposal(action="press_key", key="volumedown"))
        if lowered in {"mute", "mute volume"}:
            return AssistantReply("Propose muting volume.", ActionProposal(action="press_key", key="volumemute"))
        if lowered in {"go back", "back"}:
            return AssistantReply("Propose going back.", ActionProposal(action="hotkey", key="go_back"))
        if lowered in {"next tab"}:
            return AssistantReply("Propose switching to the next tab.", ActionProposal(action="hotkey", key="next_tab"))
        if lowered in {"previous tab"}:
            return AssistantReply("Propose switching to the previous tab.", ActionProposal(action="hotkey", key="previous_tab"))
        if lowered in {"maximize window", "make this window bigger"}:
            return AssistantReply("Propose maximizing the active window.", ActionProposal(action="hotkey", key="maximize"))

        type_match = re.fullmatch(r"(?:type|enter text)\s+(.+)", normalized, flags=re.IGNORECASE)
        if type_match:
            text = type_match.group(1)
            return AssistantReply(
                f"Type this text? {text!r} Confirm by entering 'confirm' in the command console.",
                ActionProposal(action="type_text", text=text, requires_confirmation=True),
            )

        if self.provider is not None:
            context = self.screen_understanding.inspect_at(*cursor).element
            proposal = self.provider.propose(normalized, context)
            if proposal is not None:
                return AssistantReply(
                    "Provider proposed an action; it is untrusted and must pass local validation.",
                    proposal,
                )
        return AssistantReply(
            "I couldn't map that to a supported safe command. Try: click <label>, "
            "where am I pointing, scroll up/down, volume up/down, go back, or type <text>."
        )
