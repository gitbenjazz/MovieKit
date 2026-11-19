from __future__ import annotations

import csv
from contextlib import redirect_stderr, redirect_stdout
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
from moviekit.collection_import_service import CollectionImportService
from moviekit.collection_repository import CollectionNotFoundError, CollectionRepository
from moviekit.config import MovieKitConfig
from moviekit.database_repository import DatabaseRepository
from moviekit.models import MovieRecord, WatchedRecord
from moviekit.recommendation_service import recommend_unwatched_movies


class CollectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "movies.db"
        self.canonical = DatabaseRepository(self.path)
        self.canonical.save_movies([
            MovieRecord("Alpha", 2000, "https://letterboxd.com/film/alpha/", tmdb_id=1),
            MovieRecord("Beta", 2001, "https://letterboxd.com/film/beta/", tmdb_id=2),
            MovieRecord("Twin", 2002, "https://letterboxd.com/film/twin-one/", tmdb_id=3),
            MovieRecord("Twin", 2002, "https://letterboxd.com/film/twin-two/", tmdb_id=4),
        ])
        self.collections = CollectionRepository(self.path)
        self.source = self.root / "edition.csv"
        self.write_source([
            (1, "Alpha", 2000, "source_transcription_only_not_independently_verified", ""),
            (2, "Beta", 2001, "needs_review", "Title requires review"),
            (3, "Twin", 2002, "source_transcription_only_not_independently_verified", ""),
            (4, "Toy Story Trilogy", 1995, "needs_review", "Grouped trilogy"),
            (5, "", 1963, "needs_review", "Missing title"),
            (6, "Absent", 2003, "source_transcription_only_not_independently_verified", ""),
        ])

    def write_source(self, rows):
        with self.source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["edition_entry_number", "title", "year", "source_url", "verification_status", "review_reason"])
            writer.writerows((number, title, year, "https://example.test/2013", status, reason)
                             for number, title, year, status, reason in rows)

    def importer(self):
        return CollectionImportService(self.collections, self.canonical)

    def test_import_preserves_editorial_audit_data_and_canonical_rows(self):
        before = len(self.canonical.get_all_movies())
        result = self.importer().import_2013(self.source)
        self.assertEqual(before, len(self.canonical.get_all_movies()))
        self.assertEqual((result.editorial_entries, result.inserted, result.updated), (6, 6, 0))
        self.assertEqual((result.matched, result.recommendable), (2, 1))
        self.assertEqual((result.unresolved, result.ambiguous, result.grouped, result.empty_title), (1, 1, 1, 1))
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT editorial_entry_number, source_title, verification_status, editorial_group, match_state "
                "FROM collection_entries ORDER BY editorial_entry_number"
            ).fetchall()
        self.assertEqual(rows[3], (4, "Toy Story Trilogy", "needs_review", "Toy Story Trilogy", "grouped"))
        self.assertEqual(rows[4], (5, "", "needs_review", None, "empty"))
        self.assertEqual(rows[2][-1], "ambiguous")

    def test_import_is_idempotent_and_collection_membership_is_safe(self):
        self.importer().import_2013(self.source)
        repeat = self.importer().import_2013(self.source)
        self.assertEqual((repeat.inserted, repeat.updated), (0, 6))
        alpha = self.canonical.get_movie_by_tmdb_id(1).id
        beta = self.canonical.get_movie_by_tmdb_id(2).id
        canonical = {m.id for m in self.canonical.get_all_movies()}
        self.assertEqual(self.collections.canonical_ids("1001-2013"), {alpha})
        self.assertEqual(self.collections.canonical_ids("intersection"), {alpha})
        self.assertEqual(self.collections.canonical_ids("all"), canonical)
        self.assertIn(beta, canonical)
        self.assertNotIn(beta, self.collections.canonical_ids("1001-2013"))
        with self.assertRaises(CollectionNotFoundError):
            CollectionRepository(self.root / "other.db").canonical_ids("1001-2013")
        with self.assertRaises(ValueError):
            self.collections.canonical_ids("unknown")

    def test_explicit_tmdb_identity_is_used_without_fuzzy_title_matching(self):
        self.source.write_text(
            "edition_entry_number,title,year,source_url,verification_status,tmdb_id\n"
            "1,Unrelated source spelling,1999,https://example.test/2013,source_transcription_only_not_independently_verified,1\n"
        )
        result = self.importer().import_2013(self.source)
        alpha = self.canonical.get_movie_by_tmdb_id(1).id
        self.assertEqual((result.matched, result.recommendable), (1, 1))
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT canonical_movie_id, match_method FROM collection_entries"
            ).fetchone()
        self.assertEqual(row, (alpha, "tmdb"))

    def test_collection_recommendation_uses_only_confirmed_members_and_existing_watched_filter(self):
        self.write_source([
            (1, "Alpha", 2000, "source_transcription_only_not_independently_verified", ""),
            (2, "Beta", 2001, "source_transcription_only_not_independently_verified", ""),
        ])
        self.importer().import_2013(self.source)
        self.canonical.save_watched([WatchedRecord("Alpha", 2000, "2020-01-01", "https://boxd.it/alpha")])
        with patch("moviekit.recommendation_service.has_prime", return_value=True), patch(
            "moviekit.recommendation_service.time.sleep"
        ):
            results = recommend_unwatched_movies(repository=self.canonical, api_key="test", verbose=False,
                                                  collection="1001-2013")
        self.assertEqual([result.movie.title for result in results], ["Beta"])

    def test_cli_import_list_show_and_invalid_recommendation_collection(self):
        def invoke(arguments):
            stdout, stderr = StringIO(), StringIO()
            with patch.object(sys, "argv", ["moviekit", *arguments]), patch(
                "moviekit.config.load_config", return_value=MovieKitConfig(database_path=str(self.path))
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main()
            return code, stdout.getvalue(), stderr.getvalue()

        code, output, error = invoke(["collections", "import", "--source", str(self.source)])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Editorial entries: 6", output)
        code, output, error = invoke(["collections", "list"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("1001-2013", output)
        self.assertIn("letterboxd-1001", output)
        self.assertIn("4 entries, 4 recommendable", output)
        code, output, error = invoke(["collections", "show", "1001-2013"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("recommendable: 1", output)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["recommend", "--collection", "bad"])

    def test_cli_import_requires_user_supplied_collection_source(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            cli.build_parser().parse_args(["collections", "import"])
        self.assertEqual(raised.exception.code, 2)

    def test_import_rejects_bad_schema_and_duplicate_entry_number_without_writes(self):
        invalid = self.root / "invalid.csv"
        invalid.write_text("title,year\nFilm,2000\n")
        with self.assertRaises(ValueError):
            self.importer().import_2013(invalid)
        self.write_source([
            (1, "Alpha", 2000, "source_transcription_only_not_independently_verified", ""),
            (1, "Beta", 2001, "source_transcription_only_not_independently_verified", ""),
        ])
        with self.assertRaises(ValueError):
            self.importer().import_2013(self.source)
        self.assertFalse(any(s.slug == "1001-2013" for s in self.collections.summaries()))
