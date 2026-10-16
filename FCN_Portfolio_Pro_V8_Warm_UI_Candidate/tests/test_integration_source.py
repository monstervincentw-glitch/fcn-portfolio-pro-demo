from pathlib import Path
import unittest

class AppLayoutGuard(unittest.TestCase):
    def test_chart_layer_keeps_stock_colors_separate_from_barriers(self):
        content=(Path(__file__).parent.parent/'streamlit_app.py').read_text()
        self.assertIn("build_stock_chart(chart_view, settings, selected_stocks)", content)
        self.assertIn("from chart_render import build_stock_chart", content)
        self.assertIn('"🧪 虛擬試打"',content)
    def test_sheet_gate_still_before_page_dispatch(self):
        content=(Path(__file__).parent.parent/'streamlit_app.py').read_text()
        self.assertLess(content.index('gate(section("site_login")'),content.index('page = st.radio('))
    def test_virtual_trial_never_writes_ledger(self):
        content=(Path(__file__).parent.parent/'virtual_trial.py').read_text()
        self.assertNotIn('spreadsheets.values.update',content)
        self.assertNotIn('AuthorizedSession',content)

if __name__=='__main__':unittest.main()
