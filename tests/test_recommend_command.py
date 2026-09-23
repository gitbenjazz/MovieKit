from __future__ import annotations

from contextlib import ExitStack, closing, redirect_stderr, redirect_stdout
import csv
from io import StringIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from moviekit import cli
from moviekit.config import MovieKitConfig
from moviekit.database_repository import DatabaseRepository
from moviekit.movie_repository import MovieRepository
from moviekit.recommendation_service import (
    InvalidYearRange,
    top_recommended_unwatched_movies,
)
from moviekit.sync_service import SyncService


class RecommendWorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.csv = MovieRepository(
            movies_path=str(self.root / "movies.csv"),
            watched_path=str(self.root / "watched.csv"),
            watched_1001_path=str(self.root / "watched1001.csv"),
            unwatched_1001_path=str(self.root / "unwatched1001.csv"),
        )
        # Deliberately not chronological: preserve the existing candidate order.
        self.titles = ["Modern (2000)", "Boundary (1970)", "Old (1969)", "Last (1999)"]
        self.write_csv(self.csv.movies_path, ["title", "link"], [
            [title, f"https://letterboxd.com/film/{title.split()[0].lower()}/"]
            for title in self.titles
        ])
        self.write_watched([])
        self.db = DatabaseRepository(self.root / "movies.db")
        self.sync_service = SyncService(self.csv, self.db)
        self.sync_service.sync()
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.search = stack.enter_context(patch(
            "moviekit.recommendation_service.search_movie", return_value=1
        ))
        self.prime = stack.enter_context(patch(
            "moviekit.recommendation_service.has_prime", return_value=True
        ))
        stack.enter_context(patch("moviekit.recommendation_service.time.sleep"))
        stack.enter_context(patch(
            "moviekit.recommendation_service.load_tmdb_api_key", return_value="test-key"
        ))

    @staticmethod
    def write_csv(path, header, rows):
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)

    def write_watched(self, rows):
        self.write_csv(self.csv.watched_path,
                       ["Date", "Name", "Year", "Letterboxd URI"], rows)

    def recommend(self, **kwargs):
        return top_recommended_unwatched_movies(
            repository=self.csv, verbose=False, **kwargs
        )

    def run_cli(self, arguments):
        stdout, stderr = StringIO(), StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["moviekit", *arguments]))
            for module in ("movie_repository", "recommendation_service"):
                stack.enter_context(patch(
                    f"moviekit.{module}.MovieRepository", return_value=self.csv
                ))
            stack.enter_context(patch(
                "moviekit.config.load_config",
                return_value=MovieKitConfig(database_path=str(self.db.database_path)),
            ))
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = cli.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_default_recommendations_still_require_prime_availability(self):
        self.prime.side_effect = [False, True, False, True]
        self.assertEqual(self.recommend(), [self.titles[1], self.titles[3]])

    def test_year_filters_before_provider_lookup_and_limit(self):
        cases = [
            ({}, self.titles),
            ({"from_year": 1970}, [self.titles[i] for i in (0, 1, 3)]),
            ({"to_year": 1999}, [self.titles[i] for i in (1, 2, 3)]),
            ({"from_year": 1970, "to_year": 1999}, [self.titles[i] for i in (1, 3)]),
            ({"from_year": 1970, "to_year": 1970}, [self.titles[1]]),
            ({"from_year": 2100}, []),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                self.search.reset_mock()
                self.assertEqual(self.recommend(**filters), expected)
                self.assertEqual([call.args[0] for call in self.search.call_args_list], expected)
        self.assertEqual(self.recommend(from_year=1970, to_year=1999, limit=1),
                         [self.titles[1]])

    def test_invalid_range_rejected_before_reading_candidates_or_network(self):
        with patch.object(self.csv, "load_unwatched_1001") as load:
            with self.assertRaises(InvalidYearRange):
                self.recommend(from_year=2000, to_year=1970)
        load.assert_not_called()
        self.search.assert_not_called()
        self.prime.assert_not_called()

    def test_cli_year_options_and_default_behavior(self):
        cases = [
            ([], self.titles),
            (["--from-year", "1970"], [self.titles[i] for i in (0, 1, 3)]),
            (["--to-year", "1999"], [self.titles[i] for i in (1, 2, 3)]),
            (["--from-year", "1970", "--to-year", "1999"],
             [self.titles[i] for i in (1, 3)]),
        ]
        for options, expected in cases:
            with self.subTest(options=options):
                code, output, error = self.run_cli(["recommend", *options])
                self.assertEqual(code, 0)
                self.assertEqual(error, "")
                self.assertEqual(output.split("========== TOP 10 ==========")[1].split(),
                                 "\n".join(expected).split())

    def test_cli_invalid_range_has_nonzero_exit_and_no_network(self):
        code, output, error = self.run_cli([
            "recommend", "--from-year", "2000", "--to-year", "1970"
        ])
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("--from-year must be less than or equal to --to-year", error)
        self.search.assert_not_called()

    def test_cli_noninteger_year_rejected(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            cli.build_parser().parse_args(["recommend", "--from-year", "recent"])
        self.assertEqual(error.exception.code, 2)

    def test_fresh_import_excludes_watched_and_reimports_idempotently(self):
        self.write_watched([
            ["2026-09-01", "Old", 1969, "https://boxd.it/old"],
        ])
        self.run_cli(["sync"])
        self.assertEqual(self.recommend(), [self.titles[i] for i in (0, 1, 3)])
        self.write_watched([
            ["2026-09-01", "Old", 1969, "https://boxd.it/old"],
            ["2026-09-22", "Boundary", 1970, "https://boxd.it/boundary"],
            ["2026-09-22", "Outside", 2025, "https://boxd.it/outside"],
        ])
        snapshots = []
        for _ in range(2):
            code, output, error = self.run_cli(["sync"])
            self.assertEqual((code, error), (0, ""))
            self.assertIn("SQLite watched history imported: 2", output)
            self.assertIn("SQLite watched history skipped: 1", output)
            self.assertEqual(self.recommend(), [self.titles[i] for i in (0, 3)])
            self.assertEqual(self.recommend(from_year=1970, to_year=1999),
                             [self.titles[3]])
            self.assertEqual({m.title for m in self.db.get_unwatched_movies()},
                             {"modern", "last"})
            with closing(sqlite3.connect(self.db.database_path)) as connection:
                snapshots.append((
                    connection.execute("SELECT id, title, year, letterboxd_url FROM movies ORDER BY id").fetchall(),
                    connection.execute(
                        "SELECT movie_id, watched_date, letterboxd_uri FROM watched ORDER BY movie_id"
                    ).fetchall(),
                    Path(self.csv.unwatched_1001_path).read_bytes(),
                ))
            self.assertEqual(len(snapshots[-1][0]), 4)
            self.assertEqual(len(snapshots[-1][1]), 2)
        self.assertEqual(snapshots[0], snapshots[1])
        code, output, _ = self.run_cli(["recommend"])
        self.assertEqual(code, 0)
        self.assertNotIn("Boundary", output)
        self.assertNotIn("Outside", output)


if __name__ == "__main__":
    unittest.main()
