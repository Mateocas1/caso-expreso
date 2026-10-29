import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

from expreso_bridge.__main__ import EXIT_CANNOT_RUN, main

EXPORT = Path(__file__).resolve().parent.parent / "kit" / "remitos_2026-09-30.json"


class CannotRunTest(unittest.TestCase):
    def run_cli(self, argv, environ):
        stderr = StringIO()
        with mock.patch.dict(os.environ, environ, clear=True), redirect_stderr(stderr):
            return main(argv), stderr.getvalue()

    def test_unreadable_export_is_reported_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as scratch:
            broken_export = Path(scratch) / "broken.json"
            broken_export.write_text("{not json", encoding="utf-8")
            for export in [Path(scratch) / "missing.json", broken_export]:
                with self.subTest(export=export.name):
                    exit_code, stderr = self.run_cli(
                        ["upload", str(export)], {"EXPRESO_API_KEY": "key"}
                    )
                    self.assertEqual(exit_code, EXIT_CANNOT_RUN)
                    self.assertIn("No se pudo leer el export", stderr)

    def test_missing_api_key_stops_before_calling_the_api(self):
        exit_code, stderr = self.run_cli(["upload", str(EXPORT)], {})

        self.assertEqual(exit_code, EXIT_CANNOT_RUN)
        self.assertIn("EXPRESO_API_KEY", stderr)


if __name__ == "__main__":
    unittest.main()
