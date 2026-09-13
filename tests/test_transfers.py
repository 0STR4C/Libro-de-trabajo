import unittest
from datetime import date, time

from app.transfers import clean_transfer, normalized_status, validate_transition


class TransferRulesTests(unittest.TestCase):
    def payload(self, **changes):
        value = {
            "task_number": " 12345 ",
            "transfer_type": "Traslado Directo",
            "scheduled_date": "2026-09-12",
            "scheduled_time": "09:30",
            "origin": " Montevideo ",
            "destination": " Pando ",
            "provider": " Auxiliador Uno ",
            "responsible": " Coordinación ",
            "comments": " Sin novedad ",
        }
        value.update(changes)
        return value

    def test_clean_transfer_normalizes_fields(self):
        result = clean_transfer(self.payload())
        self.assertEqual(result["task_number"], "12345")
        self.assertEqual(result["scheduled_date"], date(2026, 9, 12))
        self.assertEqual(result["scheduled_time"], time(9, 30))
        self.assertEqual(result["responsible"], "Coordinación")

    def test_invalid_type_and_same_route_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "catálogo"):
            clean_transfer(self.payload(transfer_type="Inventado"))
        with self.assertRaisesRegex(ValueError, "diferentes"):
            clean_transfer(self.payload(origin="PÁNDO", destination="pando"))

    def test_legacy_statuses_are_normalized(self):
        self.assertEqual(normalized_status("PENDIENTE"), "SIN_ASIGNAR")
        self.assertEqual(normalized_status("CONFIRMADO"), "ASIGNADO")
        self.assertEqual(normalized_status("COMPLETADO"), "FINALIZADO")

    def test_assignment_requires_provider_and_responsible(self):
        current = {"status": "SIN_ASIGNAR", "provider": None, "responsible": None}
        with self.assertRaisesRegex(ValueError, "prestador y responsable"):
            validate_transition(current, {"status": "ASIGNADO"})
        result = validate_transition(current, {"status": "ASIGNADO", "provider": "Auxilio", "responsible": "Ana"})
        self.assertEqual(result["status"], "ASIGNADO")

    def test_completion_and_cancellation_require_note(self):
        current = {"status": "EN_CURSO", "provider": "Auxilio", "responsible": "Ana"}
        with self.assertRaisesRegex(ValueError, "resultado"):
            validate_transition(current, {"status": "FINALIZADO"})
        with self.assertRaisesRegex(ValueError, "motivo"):
            validate_transition(current, {"status": "CANCELADO"})

    def test_terminal_states_cannot_be_reopened(self):
        with self.assertRaisesRegex(ValueError, "No se puede"):
            validate_transition({"status": "FINALIZADO"}, {"status": "ASIGNADO"})


if __name__ == "__main__":
    unittest.main()
