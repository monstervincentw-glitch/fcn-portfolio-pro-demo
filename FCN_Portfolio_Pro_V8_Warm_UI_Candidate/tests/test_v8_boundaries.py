"""Offline regression checks. Does not claim Streamlit/browser integration coverage."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class PresentationOnly(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        return None if node.module == 'warm_theme' else node

    def visit_Expr(self, node):
        call = node.value
        if isinstance(call, ast.Call):
            if isinstance(call.func, ast.Name) and call.func.id == 'login_intro':
                return None
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                if call.func.value.id == 'st' and call.func.attr in ('title', 'caption', 'markdown'):
                    return None
        return self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'form_submit_button' and node.args:
            node.args[0] = ast.Constant(value='SUBMIT_LABEL')
        return self.generic_visit(node)


def auth_ast_hash(source):
    tree = PresentationOnly().visit(ast.parse(source))
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()


def business_calls(source):
    targets = {'TrialInputs', 'parse_symbols', 'parse_month', 'choose_available_series',
               'simulate_history', 'currency_summary', 'validate_masked_portfolio',
               'summarize_portfolio', 'rank_quality_issues', 'product_group'}
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in targets:
                out.append(ast.dump(node, include_attributes=False))
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in {'READER', 'SheetsReader'}:
                out.append(ast.dump(node, include_attributes=False))
    return sorted(out)


class V8Boundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / 'tests' / 'v8_baseline.json').read_text(encoding='utf-8'))

    def test_data_calculation_and_dependency_files_are_byte_identical(self):
        for name, digest in self.manifest['protected_files'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)

    def test_entire_login_module_identical_after_removing_allowlisted_presentation(self):
        self.assertEqual(auth_ast_hash((ROOT / 'site_login.py').read_text(encoding='utf-8')), self.manifest['auth_ast_sha256'])

    def test_app_calls_existing_calculators_and_readers_with_same_arguments(self):
        self.assertEqual(business_calls((ROOT / 'streamlit_app.py').read_text(encoding='utf-8')), self.manifest['business_calls'])

    def test_no_secrets_or_credentials_in_deployment(self):
        self.assertFalse((ROOT / '.streamlit' / 'secrets.toml').exists())
        for path in ROOT.rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.toml', '.json'}:
                self.assertNotIn('-----BEGIN ' + 'PRIVATE KEY-----', path.read_text(encoding='utf-8'), str(path))

    def test_dynamic_status_text_is_html_escaped(self):
        from warm_theme import status_card
        captured=[]
        fake=types.SimpleNamespace(markdown=lambda value, **kwargs: captured.append(value))
        with patch.dict(sys.modules, {'streamlit':fake}):
            status_card('<script>alert(1)</script>', 'USD', '<img src=x onerror=alert(1)>')
        self.assertNotIn('<script>', captured[0])
        self.assertNotIn('<img', captured[0])
        self.assertIn('&lt;script&gt;', captured[0])

    def test_user_selected_asset_is_packaged_unchanged(self):
        from warm_theme import hero_uri
        self.assertEqual(hashlib.sha256((ROOT / 'assets/shiba-login.png').read_bytes()).hexdigest(), self.manifest['hero_sha256'])
        self.assertTrue(hero_uri().startswith('data:image/png;base64,'))

    def test_primary_text_and_button_contrast(self):
        def luminance(color):
            values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
        for fg,bg in [('#403529','#FAF6EF'),('#756653','#FFFCF7'),('#FFFFFF','#946328')]:
            a,b=sorted([luminance(fg),luminance(bg)])
            self.assertGreaterEqual((b+.05)/(a+.05),4.5)


if __name__ == '__main__':
    unittest.main()
