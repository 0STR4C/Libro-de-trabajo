import unittest
from pathlib import Path


class ContextualWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.script = (root / "app/static/app.js").read_text(encoding="utf-8")

    def test_delay_actions_use_contextual_forms(self):
        self.assertIn("dataset.type='delay_verify'", self.script)
        self.assertIn("dataset.type='delay_normalize'", self.script)
        self.assertIn('name="verification_note"', self.script)
        self.assertIn('name="resolution_note"', self.script)
        self.assertIn("'/verify'", self.script.replace("`/api/delays/${event.currentTarget.dataset.delayId}/verify`", "'/verify'"))

    def test_transfer_copy_and_standard_decision_use_modals(self):
        self.assertIn("dataset.type='transfer_duplicate'", self.script)
        self.assertIn("dataset.type='standard_decision'", self.script)
        self.assertIn("Crear copia", self.script)
        self.assertIn("La decisión y su fundamento quedarán en el historial", self.script)


if __name__ == "__main__":
    unittest.main()
