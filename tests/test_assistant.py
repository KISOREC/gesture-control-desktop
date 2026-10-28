import unittest
from unittest.mock import Mock, patch

from action_executor import ActionExecutor, ActionValidationError
from assistant_engine import AssistantEngine
from config import AppConfig
from models import ActionProposal, ScreenElement


class ActionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.executor = ActionExecutor(screen_size=(1000, 800))

    @patch("action_executor.pyautogui")
    def test_click_checks_bounds_and_clicks_valid_coordinate(self, mouse):
        result = self.executor.execute(ActionProposal(action="click", x=25, y=40))
        self.assertTrue(result.executed)
        mouse.moveTo.assert_called_once_with(25, 40)
        mouse.click.assert_called_once_with(x=25, y=40)

    def test_click_rejects_out_of_bounds_coordinates(self):
        with self.assertRaises(ActionValidationError):
            self.executor.execute(ActionProposal(action="click", x=1000, y=40))

    @patch("action_executor.pyautogui")
    def test_typing_requires_confirmation(self, mouse):
        proposal = ActionProposal(action="type_text", text="safe query", requires_confirmation=True)
        result = self.executor.execute(proposal)
        self.assertFalse(result.executed)
        mouse.write.assert_not_called()
        self.executor.execute(proposal, confirmed=True)
        mouse.write.assert_called_once_with("safe query", interval=0.02)

    def test_unsupported_actions_and_keys_are_rejected(self):
        with self.assertRaises(ActionValidationError):
            self.executor.execute(ActionProposal(action="run_shell", text="whoami"))
        with self.assertRaises(ActionValidationError):
            self.executor.execute(ActionProposal(action="press_key", key="arbitrary"))


class AssistantEngineTests(unittest.TestCase):
    def setUp(self):
        self.screen = Mock()
        self.engine = AssistantEngine(self.screen)

    def test_identifies_pointed_element(self):
        element = ScreenElement("Edit", "Search", (0, 0, 100, 40), "uia", 0.95, editable=True, clickable=True)
        self.screen.inspect_at.return_value = Mock(element=element, warnings=())
        reply = self.engine.handle("where am I pointing", (20, 20))
        self.assertIn("Search", reply.message)
        self.assertIn("Editable", reply.message)

    def test_click_proposal_requires_ui_automation_actionable_target(self):
        target = ScreenElement("Button", "Search", (10, 20, 110, 60), "uia", 0.95, clickable=True)
        self.screen.find_by_label.return_value = ((target,), ())
        reply = self.engine.handle("click Search", (0, 0))
        self.assertEqual(reply.proposal.action, "click")
        self.assertEqual((reply.proposal.x, reply.proposal.y), (60, 40))

    def test_ambiguous_targets_ask_for_clarification(self):
        targets = (
            ScreenElement("Button", "Search", (0, 0, 10, 10), "uia", 0.95, clickable=True),
            ScreenElement("Edit", "Search", (10, 10, 20, 20), "uia", 0.95, clickable=True),
        )
        self.screen.find_by_label.return_value = (targets, ())
        reply = self.engine.handle("click Search", (0, 0))
        self.assertIsNone(reply.proposal)
        self.assertEqual(len(reply.choices), 2)

    def test_ocr_text_is_not_clickable(self):
        text = ScreenElement("Text", "Search", (0, 0, 10, 10), "ocr", 0.9)
        self.screen.find_by_label.return_value = ((text,), ("OCR is text-only.",))
        reply = self.engine.handle("click Search", (0, 0))
        self.assertIsNone(reply.proposal)
        self.assertIn("cannot prove", reply.message)

    def test_type_text_is_a_confirmed_proposal(self):
        reply = self.engine.handle("type hello world", (0, 0))
        self.assertEqual(reply.proposal.text, "hello world")
        self.assertTrue(reply.proposal.requires_confirmation)

    def test_safe_navigation_and_unknown_command(self):
        self.assertEqual(self.engine.handle("go back", (0, 0)).proposal.key, "go_back")
        self.assertIsNone(self.engine.handle("run arbitrary command", (0, 0)).proposal)


class ConfigTests(unittest.TestCase):
    def test_invalid_cursor_sensitivity_is_reported(self):
        with patch.dict("os.environ", {"GESTURE_CURSOR_SENSITIVITY": "99"}):
            with self.assertRaises(ValueError):
                AppConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
