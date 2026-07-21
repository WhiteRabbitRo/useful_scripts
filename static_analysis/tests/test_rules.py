import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sa.rules import CustomRuleStrategy, RuleLoader
from sa.strategies import AnalysisContext


class TestRules(unittest.TestCase):
    def test_strcpy_in_code_detected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as fh:
            fh.write('void f(char *d, char *s) { strcpy(d, s); }\n')
            path = fh.name

        try:
            loader = RuleLoader(None)
            strategy = CustomRuleStrategy(loader)
            ctx = AnalysisContext(includes=[], defines=[], project_root=os.getcwd())
            findings = strategy.run([path], ctx)
            rule_ids = {f.rule_id for f in findings}
            self.assertIn("dangerous-strcpy", rule_ids)
        finally:
            os.unlink(path)

    def test_strcpy_in_comment_ignored(self):
        with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as fh:
            fh.write('/* strcpy(d, s); */\nvoid f() {}\n')
            path = fh.name

        try:
            loader = RuleLoader(None)
            strategy = CustomRuleStrategy(loader)
            ctx = AnalysisContext(includes=[], defines=[], project_root=os.getcwd())
            findings = strategy.run([path], ctx)
            rule_ids = {f.rule_id for f in findings}
            self.assertNotIn("dangerous-strcpy", rule_ids)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
