import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sa.models import Finding, Severity
from sa.report import ReportGenerator


class TestReport(unittest.TestCase):
    def test_json_output(self):
        findings = [
            Finding(
                tool="custom-rules",
                rule_id="dangerous-strcpy",
                message="test",
                file="main.c",
                line=10,
                severity=Severity.ERROR,
            )
        ]
        report = ReportGenerator(findings, {"custom-rules": 0.1})
        data = json.loads(report.to_json())
        self.assertEqual(len(data["findings"]), 1)
        self.assertEqual(data["findings"][0]["rule_id"], "dangerous-strcpy")
        self.assertEqual(data["summary"]["ERROR"], 1)

    def test_sarif_contains_results(self):
        findings = [
            Finding(
                tool="secret-scanner",
                rule_id="aws-access-key",
                message="secret",
                file="config.c",
                line=1,
                severity=Severity.CRITICAL,
            )
        ]
        report = ReportGenerator(findings, {})
        sarif = json.loads(report.to_sarif())
        self.assertEqual(len(sarif["runs"][0]["results"]), 1)


if __name__ == "__main__":
    unittest.main()
