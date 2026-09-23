from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from moviekit import cli
from moviekit.config import MovieKitConfig


class PersonalCommandTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.export = self.root / "export"
        self.export.mkdir()
        (self.export / "watched.csv").write_text(
            "Date,Name,Year,Letterboxd URI\n2026-09-01,Example,2020,https://boxd.it/example\n"
        )

    def run_cli(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with patch("sys.argv", ["moviekit", "personal", *args]), patch(
            "moviekit.config.load_config",
            return_value=MovieKitConfig(database_path=str(self.root / "movies.db")),
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_sync_and_status_through_real_application_service(self):
        for _ in range(2):
            code, output, error = self.run_cli("sync", "--source", str(self.export), "--username", "Example")
            self.assertEqual((code, error), (0, ""))
            self.assertIn("Movies processed: 1", output)
            self.assertIn("Watch events (account total): 1", output)
            self.assertIn("Unmatched movies: 1", output)
        self.assertIn("Records inserted: 0", output)
        code, output, error = self.run_cli("status", "--username", "example")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Movies: 1", output)
        self.assertIn("Last sync: completed", output)

    def test_missing_account_is_clear(self):
        code, output, _ = self.run_cli("status", "--username", "missing")
        self.assertEqual(code, 0)
        self.assertIn("No personal library found", output)

    def test_bad_source_and_bad_username_fail_cleanly(self):
        for source, username in [(str(self.root / "missing"), "user"), (str(self.export), "bad/user")]:
            code, _, error = self.run_cli("sync", "--source", source, "--username", username)
            self.assertEqual(code, 1)
            self.assertIn("Personal sync failed", error)
            self.assertNotIn("Traceback", error)

    def test_skipped_rows_produce_partial_success_report_and_nonzero_status(self):
        with (self.export / "watched.csv").open("a") as handle:
            handle.write("2026-09-01,,2020,https://boxd.it/bad\n")
        code, output, error = self.run_cli("sync", "--source", str(self.export), "--username", "example")
        self.assertEqual(code, 1)
        self.assertIn("Movies processed: 1", output)
        self.assertIn("Skipped rows: 1", output)
        self.assertIn("watched.csv:3", error)

    def test_source_and_username_are_explicit(self):
        for args in [["personal"], ["personal", "sync"], ["personal", "status"]]:
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
                cli.build_parser().parse_args(args)
            self.assertEqual(raised.exception.code, 2)
