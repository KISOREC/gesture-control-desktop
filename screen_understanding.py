"""On-demand, local screen inspection using Windows UI Automation and OCR."""

import queue
import threading
from typing import List, Optional, Tuple

import pyautogui

from models import ScreenElement, ScreenInspection


class ScreenUnderstanding:
    _CLICKABLE_ROLES = {
        "Button", "Hyperlink", "TabItem", "MenuItem", "CheckBox",
        "RadioButton", "ComboBox", "ListItem", "TreeItem",
    }
    _EDITABLE_ROLES = {"Edit", "Document"}
    _SCROLLABLE_ROLES = {"Pane", "Document", "List", "Tree", "DataGrid"}

    def inspect_at(self, x: int, y: int) -> ScreenInspection:
        warnings: List[str] = []
        width, height = pyautogui.size()
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError("Inspection point is outside the display bounds.")

        try:
            from pywinauto import Desktop

            wrapper = Desktop(backend="uia").from_point(x, y)
            element = self._from_wrapper(wrapper)
            if element is not None and element.role != "Window":
                return ScreenInspection(element, tuple(warnings))
            if element is not None:
                warnings.append("UI Automation found the containing window but no specific child element.")
        except Exception as exc:
            warnings.append(f"Windows UI Automation unavailable at this point: {exc}")

        element, ocr_warnings = self._ocr_at(x, y)
        warnings.extend(ocr_warnings)
        return ScreenInspection(element, tuple(warnings))

    def find_by_label(self, query: str) -> Tuple[Tuple[ScreenElement, ...], Tuple[str, ...]]:
        normalized_query = query.casefold().strip()
        if not normalized_query:
            raise ValueError("Search query must not be empty.")

        warnings: List[str] = []
        elements: List[ScreenElement] = []
        try:
            from pywinauto import Desktop

            window = Desktop(backend="uia").get_active()
            for wrapper in window.descendants():
                element = self._from_wrapper(wrapper)
                if element and normalized_query in element.label.casefold():
                    elements.append(element)
        except Exception as exc:
            warnings.append(f"Windows UI Automation search failed: {exc}")

        if not elements:
            ocr_elements, ocr_warnings = self._ocr_search(normalized_query)
            elements.extend(ocr_elements)
            warnings.extend(ocr_warnings)

        unique = {}
        for element in elements:
            unique[(element.role, element.label, element.bounds)] = element
        return tuple(unique.values()), tuple(warnings)

    @staticmethod
    def _from_wrapper(wrapper) -> ScreenElement:
        info = wrapper.element_info
        rectangle = info.rectangle
        bounds = (int(rectangle.left), int(rectangle.top), int(rectangle.right), int(rectangle.bottom))
        role = str(info.control_type or "Unknown")
        label = str(info.name or "").strip() or role
        enabled = bool(info.enabled)
        visible = bool(info.visible)
        editable = role in ScreenUnderstanding._EDITABLE_ROLES
        clickable = role in ScreenUnderstanding._CLICKABLE_ROLES or editable
        return ScreenElement(
            role=role,
            label=label,
            bounds=bounds,
            source="uia",
            confidence=0.95,
            enabled=enabled,
            visible=visible,
            editable=editable,
            clickable=clickable,
            draggable=role in {"Thumb", "TitleBar", "Slider"},
            scrollable=role in ScreenUnderstanding._SCROLLABLE_ROLES,
        )

    @staticmethod
    def _ocr_data():
        import pytesseract
        from pytesseract import Output

        image = pyautogui.screenshot()
        return pytesseract.image_to_data(image, output_type=Output.DICT)

    def _ocr_at(self, x: int, y: int):
        warnings: List[str] = []
        try:
            data = self._ocr_data()
        except Exception as exc:
            return None, (f"OCR fallback unavailable: {exc}",)

        matches = []
        for index, text in enumerate(data["text"]):
            text = text.strip()
            if not text:
                continue
            left, top = int(data["left"][index]), int(data["top"][index])
            right = left + int(data["width"][index])
            bottom = top + int(data["height"][index])
            if left <= x <= right and top <= y <= bottom:
                confidence = max(0.0, min(1.0, float(data["conf"][index]) / 100.0))
                matches.append(ScreenElement(
                    role="Text",
                    label=text,
                    bounds=(left, top, right, bottom),
                    source="ocr",
                    confidence=confidence,
                ))
        if matches:
            warnings.append("OCR reads text only; it cannot confirm that the text is editable or clickable.")
            return max(matches, key=lambda item: item.confidence), tuple(warnings)
        return None, tuple(warnings)

    def _ocr_search(self, query: str):
        warnings: List[str] = []
        try:
            data = self._ocr_data()
        except Exception as exc:
            return (), (f"OCR search fallback unavailable: {exc}",)

        found = []
        for index, text in enumerate(data["text"]):
            text = text.strip()
            if text and query in text.casefold():
                left, top = int(data["left"][index]), int(data["top"][index])
                right = left + int(data["width"][index])
                bottom = top + int(data["height"][index])
                confidence = max(0.0, min(1.0, float(data["conf"][index]) / 100.0))
                found.append(ScreenElement(
                    role="Text",
                    label=text,
                    bounds=(left, top, right, bottom),
                    source="ocr",
                    confidence=confidence,
                ))
        if found:
            warnings.append("OCR matches are text-only and cannot be clicked safely without UI Automation metadata.")
        return tuple(found), tuple(warnings)


class ScreenUnderstandingWorker:
    """Run on-demand UI Automation/OCR away from the gesture and cursor loop."""

    def __init__(self, screen_understanding: Optional[ScreenUnderstanding] = None):
        self.screen_understanding = screen_understanding or ScreenUnderstanding()
        self._requests = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._latest = ScreenInspection(None)
        self._stopping = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="screen-understanding",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def submit(self, x: int, y: int) -> None:
        request = (x, y)
        try:
            self._requests.put_nowait(request)
        except queue.Full:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                pass
            self._requests.put_nowait(request)

    def latest(self) -> ScreenInspection:
        with self._lock:
            return self._latest

    def stop(self) -> None:
        self._stopping.set()
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                request = self._requests.get(timeout=0.2)
            except queue.Empty:
                continue
            if request is None:
                return
            try:
                inspection = self.screen_understanding.inspect_at(*request)
            except Exception as exc:
                inspection = ScreenInspection(None, (f"Screen inspection failed: {exc}",))
            with self._lock:
                self._latest = inspection
