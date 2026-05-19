import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "quant_app"


class FrontendStructureTests(unittest.TestCase):
    def test_report_page_uses_report_specific_script(self):
        report_html = (APP_DIR / "report.html").read_text(encoding="utf-8")

        self.assertIn('src="./report.js', report_html)
        self.assertNotIn('src="./app.js', report_html)

    def test_workbench_page_uses_workbench_script(self):
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('src="./app.js', index_html)

    def test_no_unused_global_utils_script_is_left_behind(self):
        self.assertFalse((APP_DIR / "utils.js").exists())


if __name__ == "__main__":
    unittest.main()
