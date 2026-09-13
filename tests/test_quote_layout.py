import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QuoteLayoutRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "app" / "static" / "quotes.css").read_text(encoding="utf-8")
        cls.index = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    def test_quote_result_does_not_reuse_sidebar_element(self):
        self.assertIn('<section class="quote-result"', self.javascript)
        self.assertNotIn('<aside class="quote-result"', self.javascript)

    def test_map_has_non_collapsible_height_and_drag_handle(self):
        self.assertIn("min-height:400px", self.styles)
        self.assertIn("quote-map-handle", self.styles)
        self.assertIn("bindQuoteMapResize", self.javascript)
        self.assertNotIn("toggleQuoteMapSize", self.javascript)

    def test_regional_delay_score_starts_neighbor_sum_at_zero(self):
        self.assertIn("reduce((sum,n)=>sum+(counts[n]||0)*.7,0)", self.javascript)

    def test_quote_columns_wrap_instead_of_being_crushed(self):
        self.assertIn(".quote-layout{display:flex;flex-wrap:wrap", self.styles)

    def test_hidden_mobile_distance_is_disabled_and_defaults_to_zero(self):
        self.assertIn("${includeMobile?'required':'disabled'}", self.javascript)
        self.assertIn("input.disabled=!checked", self.javascript)
        self.assertIn("body.manual_mobile_km=0", self.javascript)

    def test_editing_quote_inputs_invalidates_old_result(self):
        self.assertIn("state.quoteResult=null;saveQuoteDraft()", self.javascript)

    def test_structured_api_errors_are_rendered_as_text(self):
        self.assertIn("function readableError", self.javascript)
        self.assertIn("readableError(payload?.detail,generic)", self.javascript)

    def test_route_failure_offers_manual_distance_contingency(self):
        self.assertIn("state.quoteFallbackAvailable=!body.manual_distance", self.javascript)
        self.assertIn("Pasar a distancia manual", self.javascript)

    def test_breakdown_closes_with_the_final_total(self):
        self.assertIn('class="quote-line quote-grand-total"><span>Total</span>', self.javascript)
        self.assertIn("money(r.total_price)", self.javascript)

    def test_route_endpoints_have_distinct_markers(self):
        self.assertIn("fillColor:'#7dd3fc'", self.javascript)
        self.assertIn("fillColor:'#ef4444'", self.javascript)
        self.assertIn("transferPoints[transferPoints.length-1]", self.javascript)
        self.assertNotIn("bounds[bounds.length-1]", self.javascript)

    def test_manual_toll_quantity_is_conditional_and_integer_only(self):
        self.assertIn('id="include-tolls"', self.javascript)
        self.assertIn('name="manual_toll_count" type="number" min="1" max="100" step="1"', self.javascript)
        self.assertIn("function toggleQuoteTolls", self.javascript)
        self.assertIn("input.required=checked;input.disabled=!checked", self.javascript)

    def test_tariff_editor_and_currency_display_support_cents(self):
        self.assertIn("minimumFractionDigits:2", self.javascript)
        self.assertIn('type="number" min="0" step="0.01" inputmode="decimal"', self.javascript)

    def test_quote_history_has_pagination_and_filters(self):
        self.assertIn("/api/quotes/history?", self.javascript)
        self.assertIn("function setQuoteHistoryPage", self.javascript)
        self.assertIn("quoteHistoryCoverage", self.javascript)
        self.assertIn("quoteHistoryFilterParams", self.javascript)
        self.assertIn("Descargar esta vista", self.javascript)

    def test_quote_menu_icon_is_a_linear_clipboard_dollar_and_pen(self):
        quote_button = self.index.split('<button data-page="quotes">', 1)[1].split('</button>', 1)[0]
        self.assertIn('stroke="currentColor" stroke-width="2" fill="none"', quote_button)
        self.assertIn('stroke-linecap="round" stroke-linejoin="round"', quote_button)
        self.assertIn('<rect x="8" y="2" width="6" height="4" rx="1"/>', quote_button)
        self.assertIn('<path d="M11 9v8"/>', quote_button)
        self.assertIn('<path d="m14 20 1-3 5.8-5.8', quote_button)
        self.assertNotIn('<circle cx="12" cy="12" r="10"/>', quote_button)


if __name__ == "__main__":
    unittest.main()
