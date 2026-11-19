from __future__ import annotations

import csv
import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from moviekit import cli
from moviekit.collection_import_service import CollectionImportService
from moviekit.collection_repository import CollectionRepository
from moviekit.config import MovieKitConfig
from moviekit.database_repository import DatabaseRepository
from moviekit.models import MovieRecord
from moviekit.personal_analytics_repository import PersonalAnalyticsRepository
from moviekit.personal_analytics_service import PersonalAnalyticsService
from moviekit.personal_library_models import AccountRecord, LikeRecord, PersonalMovieRecord, RatingRecord, WatchEventRecord
from moviekit.personal_library_repository import PersonalLibraryRepository


class AnalyticsCommandTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "movies.db"
        self.personal = PersonalLibraryRepository(self.path)
        self.canonical = DatabaseRepository(self.path)
        self.canonical.save_movies([
            MovieRecord("Film A", 1999, "https://letterboxd.com/film/a/", tmdb_id=1,
                        genres="Drama, Mystery", director="Director A"),
            MovieRecord("Film B", 2001, "https://letterboxd.com/film/b/", tmdb_id=2,
                        genres="Drama", director="Director B"),
        ])
        self.account = self.personal.upsert_account(AccountRecord("letterboxd", "user"))
        first = self.canonical.get_movie_by_tmdb_id(1)
        second = self.canonical.get_movie_by_tmdb_id(2)
        self.first = self.personal.upsert_personal_movie(PersonalMovieRecord(
            self.account.id, "Film A", 1999, first.letterboxd_url, canonical_movie_id=first.id))
        self.second = self.personal.upsert_personal_movie(PersonalMovieRecord(
            self.account.id, "Film B", 2001, second.letterboxd_url, canonical_movie_id=second.id))
        self.unmatched = self.personal.upsert_personal_movie(PersonalMovieRecord(
            self.account.id, "Unlinked", 2002, "https://letterboxd.com/film/unlinked/"))
        self.personal.save_watch_events([
            WatchEventRecord(self.account.id, self.first.id, "2020-01-01", "a1", "letterboxd_diary"),
            WatchEventRecord(self.account.id, self.first.id, "2021-01-01", "a2", "letterboxd_diary", True),
            WatchEventRecord(self.account.id, self.second.id, None, "b1", "letterboxd_watched"),
            WatchEventRecord(self.account.id, self.unmatched.id, "bad-date", "u1", "letterboxd_diary"),
        ])
        self.personal.save_ratings([
            RatingRecord(self.account.id, self.first.id, 4.5),
            RatingRecord(self.account.id, self.second.id, 2.5),
        ])
        self.personal.save_likes([LikeRecord(self.account.id, self.first.id)])
        self.import_collection()

    def import_collection(self):
        source = self.root / "collection.csv"
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["edition_entry_number", "title", "year", "source_url", "verification_status", "review_reason"])
            writer.writerows([
                (1, "Film A", 1999, "https://example.test", "source_transcription_only_not_independently_verified", ""),
                (2, "Film B", 2001, "https://example.test", "source_transcription_only_not_independently_verified", ""),
                (3, "Toy Story Trilogy", 1995, "https://example.test", "needs_review", "Grouped trilogy"),
                (4, "", 1963, "https://example.test", "needs_review", "Missing title"),
            ])
        CollectionImportService(CollectionRepository(self.path), self.canonical).import_2013(source)

    def report(self):
        return PersonalAnalyticsService(PersonalAnalyticsRepository(self.path)).report("user")

    def run_cli(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with patch.object(sys, "argv", ["moviekit", "analytics", *args]), patch(
            "moviekit.config.load_config", return_value=MovieKitConfig(database_path=str(self.path))
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_report_distinguishes_events_ratings_metadata_and_unmatched_movies_read_only(self):
        before = self.path.read_bytes()
        report = self.report()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual((report.stats.watched, report.stats.watch_events), (3, 4))
        self.assertEqual((report.linked_personal_movies, report.unmatched_personal_movies), (2, 1))
        self.assertEqual((report.stats.undated_events, report.stats.rewatch_events), (2, 1))
        self.assertEqual(report.watched_decades, ((1990, 1), (2000, 2)))
        self.assertEqual((report.stats.genre_coverage, report.stats.director_coverage), (2, 2))
        drama = next(group for group in report.taste.genres if group.name == "Drama")
        self.assertEqual((drama.rated, drama.liked, drama.average_rating, drama.evidence),
                         (2, 1, 3.5, "insufficient"))

    def test_collection_progress_uses_resolved_denominator_and_preserves_groups(self):
        progress = {item.slug: item for item in self.report().collections}
        canonical = progress["letterboxd-1001"]
        edition = progress["1001-2013"]
        self.assertEqual((canonical.resolved_films, canonical.watched_resolved_films), (2, 2))
        self.assertEqual(canonical.unwatched_resolved_films, 0)
        self.assertEqual((edition.editorial_entries, edition.resolved_films, edition.watched_resolved_films), (4, 2, 2))
        self.assertEqual(edition.unwatched_resolved_films, 0)
        self.assertEqual((edition.unresolved_entries, edition.grouped_entries), (2, 1))
        self.assertEqual((edition.coverage_percent, edition.progress_percent), (50.0, 100.0))

    def test_summary_taste_collections_and_json_profile_cli(self):
        code, output, error = self.run_cli("summary", "--username", "user")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Unique watched films: 3", output)
        self.assertIn("Viewing events: 4", output)
        self.assertIn("Personal films without canonical link: 1/3", output)
        code, output, error = self.run_cli("taste", "--username", "user")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Rated films: 2", output)
        self.assertIn("Insufficient evidence", output)
        self.assertIn("Favorite genres by likes", output)
        code, output, error = self.run_cli("collections", "--username", "user")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Resolved film identities: 2/4 (50.0% coverage)", output)
        self.assertIn("Unwatched resolved films: 0", output)
        self.assertIn("Grouped entries are not counted", output)
        code, output, error = self.run_cli("profile", "--username", "user", "--format", "json")
        self.assertEqual((code, error), (0, ""))
        profile = json.loads(output)
        self.assertEqual(profile["schema_version"], "moviekit.personal-profile.v1")
        self.assertEqual(profile["username"], "user")
        self.assertEqual(profile["data_coverage"]["unmatched_personal_movies"], 1)
        self.assertEqual(profile["collection_progress"][1]["resolved_films"], 2)
        self.assertEqual(profile["collection_progress"][1]["unwatched_resolved_films"], 0)
        self.assertNotIn(str(self.root), output)

    def test_no_ratings_empty_library_and_invalid_username_are_explicit(self):
        empty = self.personal.upsert_account(AccountRecord("letterboxd", "empty"))
        self.assertFalse(PersonalAnalyticsService(PersonalAnalyticsRepository(self.path)).report(empty.username).taste.ratings_available)
        code, output, error = self.run_cli("taste", "--username", "empty")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("preference inference unavailable", output)
        code, output, error = self.run_cli("profile", "--username", "missing", "--format", "json")
        self.assertEqual(code, 2)
        self.assertIn("No personal library found", error)
