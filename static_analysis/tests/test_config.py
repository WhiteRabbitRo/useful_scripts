import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sa.config import load_config


class TestConfig(unittest.TestCase):
    def test_cli_overrides_rc(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc_path = os.path.join(tmp, ".analyzerrc.json")
            with open(rc_path, "w", encoding="utf-8") as fh:
                json.dump({"source_dirs": ["src"], "verbose": False, "jobs": 2}, fh)

            cfg = load_config(
                tmp,
                rc_path,
                {"source_dirs": ["other"], "verbose": True, "jobs": None},
            )

            self.assertEqual(cfg.source_dirs, ["other"])
            self.assertTrue(cfg.verbose)
            self.assertEqual(cfg.jobs, 2)

    def test_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(tmp, None, {})
            self.assertEqual(cfg.cppcheck_platform, "unix64")
            self.assertEqual(cfg.outdir, "Debug")


if __name__ == "__main__":
    unittest.main()
