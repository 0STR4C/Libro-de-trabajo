import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NoticeLayoutRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    def test_attention_views_are_visible(self):
        for label in ("Sin responsable", "Asignados a mí", "En espera"):
            self.assertIn(label, self.javascript)
        self.assertIn("notice-focus-cards", self.javascript)

    def test_open_notices_are_sorted_by_action_need(self):
        self.assertIn("function noticeSort", self.javascript)
        self.assertIn("!r.managed_by?0", self.javascript)
        self.assertIn("rows=[...rows].sort(noticeSort)", self.javascript)

    def test_responsible_and_age_are_explicit(self):
        self.assertIn("['Antigüedad',r=>noticeAge(r)]", self.javascript)
        self.assertIn("['Responsable',r=>noticeOwner(r)]", self.javascript)
        self.assertIn("Te corresponde", self.javascript)

    def test_assignment_uses_active_notice_users(self):
        self.assertIn("/api/notices/assignees", self.javascript)
        self.assertIn("openNoticeAssignment", self.javascript)
        self.assertIn("Solo aparecen usuarios activos", self.javascript)

    def test_attention_rows_have_distinct_styles(self):
        self.assertIn(".notice-unassigned td", self.styles)
        self.assertIn(".notice-own td", self.styles)
        self.assertIn(".notice-waiting td", self.styles)

    def test_duplicate_warning_allows_review_or_confirmed_creation(self):
        self.assertIn("/api/notices/duplicates?", self.javascript)
        self.assertIn("Posible aviso duplicado", self.javascript)
        self.assertIn("Ver aviso existente", self.javascript)
        self.assertIn("pending.allow_duplicate=true", self.javascript)

    def test_notice_history_is_available_from_each_row(self):
        self.assertIn("openNoticeHistory", self.javascript)
        self.assertIn("/api/notices/${id}/history", self.javascript)
        self.assertIn("notice-timeline", self.javascript)
        self.assertIn(".notice-timeline article", self.styles)

    def test_notice_creation_is_guided_and_can_self_assign(self):
        self.assertIn("¿Qué necesita saber o hacer el equipo?", self.javascript)
        self.assertIn("Asignármelo al guardar", self.javascript)
        self.assertIn('name="managed_by" value="${esc(currentUser)}"', self.javascript)

    def test_closure_requires_a_result(self):
        self.assertIn("openNoticeClosure", self.javascript)
        self.assertIn("Resultado o motivo del cierre", self.javascript)
        self.assertIn('name="comments" minlength="2"', self.javascript)


if __name__ == "__main__":
    unittest.main()
