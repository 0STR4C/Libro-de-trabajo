import unittest
from pathlib import Path


class DelayLayoutRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.script=(root/"app"/"static"/"app.js").read_text(encoding="utf-8")
        cls.index=(root/"app"/"static"/"index.html").read_text(encoding="utf-8")
        cls.dashboard_styles=(root/"app"/"static"/"dashboard.css").read_text(encoding="utf-8")

    def test_dashboard_only_maps_verified_delays(self):
        self.assertIn("distributions.delays_by_department",self.script)
        self.assertNotIn("api('/api/delays'),api('/api/notices'),api('/api/transfers')",self.script)
        self.assertIn("delays_need_review",self.script)

    def test_arrival_guidance_has_service_zone_and_review_states(self):
        self.assertIn("state.standardService",self.script)
        self.assertIn("state.standardZone",self.script)
        self.assertIn("delays_needing_review",self.script)
        self.assertIn("No informes un tiempo todavía",self.script)
        self.assertIn("No usar sin confirmar",self.script)
        self.assertIn("/api/settings/standards-coverage",self.script)
        self.assertIn("prestaciones sin referencia utilizable",self.script)
        self.assertIn("review_interval_days",self.script)
        self.assertIn("Responsable",self.script)

    def test_delay_actions_require_verification_evidence(self):
        self.assertIn("verification_note",self.script)
        self.assertIn("resolution_note",self.script)
        self.assertIn("/verify",self.script)

    def test_arrival_cards_wrap_actions_without_page_overflow(self):
        self.assertIn("tw-flex-wrap",self.script)
        self.assertIn("tw-max-w-full",self.script)
        self.assertIn(".standard-actions{display:flex!important",self.dashboard_styles)
        self.assertIn("flex-wrap:wrap",self.dashboard_styles)
        self.assertIn(".standards-layout>*{min-width:0",self.dashboard_styles)

    def test_asset_versions_deliver_the_new_interface(self):
        self.assertIn('/app.js?v=57',self.index)
        self.assertIn('/dashboard.css?v=7',self.index)
        self.assertIn('/styles.css?v=28',self.index)

    def test_dashboard_exposes_delay_control_metrics(self):
        self.assertIn("d.delay_metrics",self.script)
        self.assertIn("definitions_version",self.script)
        self.assertIn("Vencen en 30 min",self.script)
        self.assertIn("Resolución promedio",self.script)
        self.assertIn("/api/operational-alerts",self.script)
        self.assertIn("Cierres con evidencia",self.script)

    def test_filtered_delay_view_and_export_share_scope(self):
        self.assertIn("params.set('scope','current')",self.script)
        self.assertIn("params.set('scope','review')",self.script)
        self.assertIn("api(`/api/delays?${reportParams}`)",self.script)

    def test_audit_view_exposes_filters_and_structured_changes(self):
        self.assertIn("auditFilterParams",self.script)
        self.assertIn("auditChangeSummary",self.script)
        self.assertIn("ID de usuario",self.script)

    def test_history_coverage_and_approval_are_available(self):
        self.assertIn("openDelayHistory",self.script)
        self.assertIn("openStandardHistory",self.script)
        self.assertIn("/api/standards/proposals",self.script)
        self.assertIn("decideStandard",self.script)
        self.assertIn("openZoneCoverageForm",self.script)


if __name__=="__main__":
    unittest.main()
