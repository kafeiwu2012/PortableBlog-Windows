"""Persistence and safety checks for tables and offline formula source."""
from html import escape
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'PortableBlog'))
from richtext import sanitize


class SpecialContentTests(unittest.TestCase):
    def test_table_roundtrip_preserves_cells_and_row_identity(self):
        body = '<table><tbody><tr><td data-row="row-ab12">甲</td><td data-row="row-ab12"><strong>乙</strong></td></tr></tbody></table>'
        clean, refs = sanitize(body)
        self.assertEqual(clean, body)
        self.assertEqual(sanitize(clean)[0], clean)
        self.assertEqual(refs, [])

    def test_table_filters_attributes_and_limits_spans(self):
        clean, _ = sanitize('<table onclick="bad()"><tr><th colspan="2">标题</th><td rowspan="999" data-row="bad&lt;row" onclick="x">值</td></tr></table>')
        self.assertIn('colspan="2"', clean)
        self.assertNotIn('rowspan', clean)
        self.assertNotIn('onclick', clean)
        self.assertNotIn('data-row', clean)

    def test_formula_source_roundtrip(self):
        for source in (r'\frac{a}{b}+\sqrt{x}', r'\int_0^\infty e^{-x^2}\,dx', r'\begin{pmatrix}a & b \\ c & d\end{pmatrix}', r'\begin{aligned}x&=1 \\ y&=2\end{aligned}'):
            body = '<div class="blog-formula" data-formula="' + escape(source, quote=True) + '">' + escape(source) + '</div>'
            self.assertEqual(sanitize(body), (body, []))
            self.assertEqual(sanitize(sanitize(body)[0])[0], body)

    def test_formula_attribute_cannot_inject_html(self):
        source = '\\text{<img src=x onerror=alert(1)>}" onclick="alert(1)'
        body = '<div class="blog-formula" data-formula="' + escape(source, quote=True) + '">safe<script>bad()</script></div>'
        clean, _ = sanitize(body)
        self.assertNotIn('<img', clean)
        self.assertNotIn('<script', clean)
        self.assertNotIn(' onclick="', clean)
        self.assertIn('&quot;', clean)

    def test_formula_source_size_is_bounded(self):
        clean, _ = sanitize('<div class="blog-formula" data-formula="' + 'x' * 8001 + '">fallback</div>')
        self.assertEqual(clean, '<div>fallback</div>')


if __name__ == '__main__':
    unittest.main()
