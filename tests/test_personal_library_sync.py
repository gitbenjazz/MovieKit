from contextlib import closing
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from moviekit.database_repository import DatabaseRepository
from moviekit.models import MovieRecord
from moviekit.personal_library_repository import PersonalLibraryRepository
from moviekit.personal_library_sync import PersonalLibrarySyncService


class PersonalSyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.export = self.root / "export"
        self.export.mkdir()
        self.repository = PersonalLibraryRepository(self.root / "movies.db")
        self.canonical = DatabaseRepository(self.repository.database_path)
        self.canonical.save_movies([MovieRecord(
            "Canonical", 2000, "https://letterboxd.com/film/canonical/"
        )])
        self.service = PersonalLibrarySyncService(self.repository)

    def write(self, file, extra, rows):
        path = self.export / file
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Date", "Name", "Year", "Letterboxd URI", *extra])
            writer.writerows(rows)

    def seed(self):
        canonical = ["2026-09-01", "Canonical", 2000, "https://boxd.it/canon"]
        outside = ["2026-09-01", "Outside", 2020, "https://boxd.it/outside"]
        self.write("watched.csv", [], [canonical, outside])
        self.write("ratings.csv", ["Rating"], [outside + [4]])
        self.write("likes/films.csv", [], [outside])
        entry = ["2026-09-02", "Canonical", 2000, "https://letterboxd.com/user/film/canonical/"]
        self.write("diary.csv", ["Watched Date", "Rewatch"], [entry + ["2026-08-31", "No"]])
        self.write("reviews.csv", ["Watched Date", "Review", "Rating"],
                   [entry + ["2026-08-31", "First review", 3.5]])

    def snapshot(self, table):
        with closing(sqlite3.connect(self.repository.database_path)) as connection:
            return connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()

    def test_full_import_idempotency_updates_and_canonical_isolation(self):
        self.seed()
        canonical_before = self.snapshot("movies")
        first = self.service.sync(self.export, "User")
        self.assertEqual((first.movies, first.watch_events, first.ratings, first.reviews, first.likes),
                         (2, 2, 1, 1, 1))
        self.assertEqual((first.canonical_matches, first.unmatched, first.ambiguous), (1, 1, 0))
        self.assertEqual(first.inserted, 7)
        second = self.service.sync(self.export, "user")
        self.assertEqual((second.inserted, second.updated), (0, 0))
        library = self.repository.get_personal_library(first.account_id)
        self.assertEqual(len(library.movies), 2)
        self.assertEqual(len(library.watch_events), 2)
        self.assertEqual(library.reviews[0].watch_event_id,
                         next(e.id for e in library.watch_events if e.source == "letterboxd_diary"))
        outside = ["2026-09-03", "Outside", 2020, "https://boxd.it/outside"]
        self.write("ratings.csv", ["Rating"], [outside + [2]])
        entry = ["2026-09-03", "Canonical", 2000, "https://letterboxd.com/user/film/canonical/"]
        self.write("reviews.csv", ["Watched Date", "Review", "Rating"],
                   [entry + ["2026-08-31", "Edited review", 4]])
        changed = self.service.sync(self.export, "user")
        self.assertGreaterEqual(changed.updated, 2)
        library = self.repository.get_personal_library(first.account_id)
        self.assertEqual(library.ratings[0].rating, 2)
        self.assertEqual(library.reviews[0].review_text, "Edited review")
        self.assertEqual(self.snapshot("movies"), canonical_before)
        self.assertEqual(self.snapshot("watched"), [])
        self.assertEqual(len(self.snapshot("sync_runs")), 3)

    def test_watch_marker_promoted_to_diary_and_rewatches_preserved(self):
        self.write("watched.csv", [], [["2026-09-01", "Outside", 2020, "https://boxd.it/outside"]])
        self.service.sync(self.export, "user")
        base = ["2026-09-03", "Outside", 2020, "https://boxd.it/outside"]
        self.write("diary.csv", ["Watched Date", "Rewatch"], [
            base + ["2026-08-01", "No"], base + ["2026-08-02", "Yes"],
            base + ["2026-08-02", "Yes"],
        ])
        for _ in range(2):
            result = self.service.sync(self.export, "user")
            self.assertEqual(result.watch_events, 3)
        events = self.repository.get_watch_events(result.account_id)
        self.assertTrue(all(e.source == "letterboxd_diary" for e in events))
        self.assertEqual(sum(e.is_rewatch for e in events), 2)

    def test_partial_export_does_not_delete_and_accounts_are_isolated(self):
        self.seed()
        first = self.service.sync(self.export, "one")
        other = self.service.sync(self.export, "two")
        self.assertNotEqual(first.account_id, other.account_id)
        for path in self.export.glob("*.csv"):
            if path.name != "ratings.csv":
                path.unlink()
        (self.export / "likes/films.csv").unlink()
        again = self.service.sync(self.export, "one")
        self.assertEqual((again.watch_events, again.reviews, again.likes), (2, 1, 1))
        self.assertEqual(len(self.repository.get_personal_movies(other.account_id)), 2)

    def test_failure_rolls_back_entire_import_and_records_failure(self):
        self.seed()
        with patch.object(self.repository, "save_reviews", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.service.sync(self.export, "user")
        for table in ("accounts", "personal_movies", "watch_events", "ratings", "reviews", "likes"):
            self.assertEqual(self.snapshot(table), [])
        with closing(sqlite3.connect(self.repository.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM sync_runs").fetchone()[0], "failed")
        self.assertEqual(len(self.snapshot("movies")), 1)

    def test_malformed_rows_are_reported_and_ambiguity_is_unlinked(self):
        self.canonical.save_movies([MovieRecord(
            "Canonical", 2000, "https://letterboxd.com/film/duplicate/"
        )])
        self.write("watched.csv", [], [
            ["2026-09-01", "Canonical", 2000, "https://boxd.it/canon"],
            ["2026-09-01", "", 2000, "https://boxd.it/bad"],
        ])
        result = self.service.sync(self.export, "user")
        self.assertEqual(result.ambiguous, 1)
        self.assertEqual(len(result.issues), 1)
        movie = self.repository.get_personal_movies(result.account_id)[0]
        self.assertIsNone(movie.canonical_movie_id)
        self.assertEqual(self.repository.latest_sync_run(result.account_id)["records_skipped"], 1)

    def test_reviews_then_diary_do_not_duplicate_same_watch(self):
        base = ["2026-09-01", "Outside", 2020, "https://boxd.it/outside"]
        self.write("reviews.csv", ["Watched Date", "Review"],
                   [base + ["2026-08-01", "Review"]])
        first = self.service.sync(self.export, "user")
        self.assertEqual(first.watch_events, 1)
        self.write("diary.csv", ["Watched Date"], [base + ["2026-08-01"]])
        for _ in range(2):
            result = self.service.sync(self.export, "user")
            self.assertEqual(result.watch_events, 1)
            library = self.repository.get_personal_library(result.account_id)
            self.assertEqual(library.reviews[0].watch_event_id, library.watch_events[0].id)
