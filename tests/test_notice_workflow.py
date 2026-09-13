import unittest

from app.local_server import notice_duplicate_reason, notice_update_permissions


class NoticeWorkflowPermissionTests(unittest.TestCase):
    def setUp(self):
        self.current = {"status": "PENDIENTE", "managed_by": None, "comments": None}

    def test_assignment_is_independent(self):
        self.assertEqual(
            notice_update_permissions(self.current, {"managed_by": "Operador"}),
            {"notices.assign"},
        )

    def test_comment_is_independent(self):
        self.assertEqual(
            notice_update_permissions(self.current, {"comments": "Seguimiento"}),
            {"notices.comment"},
        )

    def test_open_status_and_close_require_different_permissions(self):
        self.assertEqual(
            notice_update_permissions(self.current, {"status": "EN_GESTION"}),
            {"notices.change_status"},
        )
        self.assertEqual(
            notice_update_permissions(self.current, {"status": "RESUELTO"}),
            {"notices.close"},
        )
        self.assertEqual(
            notice_update_permissions(self.current, {"status": "RESUELTO", "comments": "Solucionado"}),
            {"notices.close"},
        )

    def test_assignment_and_status_require_both_permissions(self):
        self.assertEqual(
            notice_update_permissions(
                self.current,
                {"status": "EN_GESTION", "managed_by": "Operador"},
            ),
            {"notices.assign", "notices.change_status"},
        )

    def test_unknown_status_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Estado de aviso inválido"):
            notice_update_permissions(self.current, {"status": "INVENTADO"})

    def test_duplicate_matches_normalized_task_number(self):
        existing = {"task_number": " T-123 ", "phone": None, "notice_type": "Consulta"}
        candidate = {"task_number": "t-123", "phone": None, "notice_type": "Otro"}
        self.assertEqual(notice_duplicate_reason(existing, candidate), "Mismo número de tarea")

    def test_duplicate_matches_phone_and_reason(self):
        existing = {"task_number": None, "phone": "099 123 456", "notice_type": "Reclamo"}
        candidate = {"task_number": None, "phone": "099-123-456", "notice_type": "reclamo"}
        self.assertEqual(notice_duplicate_reason(existing, candidate), "Mismo teléfono y motivo")

    def test_same_phone_with_different_reason_is_not_duplicate(self):
        existing = {"task_number": None, "phone": "099123456", "notice_type": "Reclamo"}
        candidate = {"task_number": None, "phone": "099123456", "notice_type": "Coordinación"}
        self.assertEqual(notice_duplicate_reason(existing, candidate), "")


if __name__ == "__main__":
    unittest.main()
