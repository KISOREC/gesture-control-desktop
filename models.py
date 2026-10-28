"""Shared data models for screen context and validated desktop actions."""

from dataclasses import dataclass
from typing import Optional, Tuple


Rectangle = Tuple[int, int, int, int]


@dataclass(frozen=True)
class ScreenElement:
    role: str
    label: str
    bounds: Rectangle
    source: str
    confidence: float
    enabled: bool = True
    visible: bool = True
    editable: bool = False
    clickable: bool = False
    draggable: bool = False
    scrollable: bool = False

    @property
    def center(self) -> Tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    def contains(self, x: int, y: int) -> bool:
        left, top, right, bottom = self.bounds
        return left <= x <= right and top <= y <= bottom


@dataclass(frozen=True)
class ScreenInspection:
    element: Optional[ScreenElement]
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionProposal:
    action: str
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    amount: Optional[int] = None
    target_label: Optional[str] = None
    requires_confirmation: bool = False


@dataclass(frozen=True)
class AssistantReply:
    message: str
    proposal: Optional[ActionProposal] = None
    choices: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionResult:
    executed: bool
    message: str
