"""
Unit tests for interactive DOM methods in nova_browser.py
"""
import unittest
import nova_browser

class TestNovaBrowserInteractive(unittest.TestCase):
    def test_scroll_js_generation(self):
        js_down = nova_browser.build_scroll_js("down")
        self.assertIn("window.scrollBy", js_down)
        
        js_top = nova_browser.build_scroll_js("top")
        self.assertIn("window.scrollTo(0, 0)", js_top)

    def test_click_js_generation(self):
        js = nova_browser.build_click_js("button.submit")
        self.assertIn("document.querySelector", js)
        self.assertIn(".click()", js)

    def test_type_js_generation(self):
        js = nova_browser.build_type_js("input[type=text]", "hello world")
        self.assertIn("hello world", js)
        self.assertIn("dispatchEvent", js)

if __name__ == "__main__":
    unittest.main()
