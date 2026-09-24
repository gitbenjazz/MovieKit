from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from moviekit import cli
from moviekit.config import MovieKitConfig
from moviekit.database_repository import DatabaseRepository
from moviekit.models import MovieRecord, WatchedRecord
from moviekit.personal_analytics_models import AnalyticsMovie, AnalyticsSnapshot, AnalyticsWatch, PreferenceStats
from moviekit.personal_analytics_repository import PersonalAnalyticsRepository
from moviekit.personal_analytics_service import PersonalAnalyticsService
from moviekit.personal_library_models import AccountRecord, LikeRecord, PersonalMovieRecord, RatingRecord, WatchEventRecord
from moviekit.personal_library_repository import PersonalLibraryRepository


class AnalyticsServiceTests(unittest.TestCase):
    def snapshot(self):
        return AnalyticsSnapshot("user", (
            AnalyticsMovie(1, 1999, 10, 4.5, True),
            AnalyticsMovie(2, 2000, None, 2.5, False),
            AnalyticsMovie(3, None, 20, None, True),
            AnalyticsMovie(4, 2010, 30, 5.0, False),  # rated-only; not watched
        ), (
            AnalyticsWatch(1, "2020-12-31", False, "letterboxd_diary"),
            AnalyticsWatch(1, "2021-01-01", True, "letterboxd_diary"),
            AnalyticsWatch(2, None, False, "letterboxd_watched"),
            AnalyticsWatch(3, "invalid", False, "letterboxd_diary"),
        ), ((1, "Drama"), (1, "Drama"), (3, "Drama"), (4, "Comedy")),
           ((1, "Director A"), (4, "Director B")), 100)

    def service(self, snapshot):
        repo = Mock()
        repo.snapshot.return_value = snapshot
        return PersonalAnalyticsService(repo)

    def test_totals_dates_decades_and_rewatches(self):
        stats = self.service(self.snapshot()).stats(" USER ")
        self.assertEqual((stats.movies, stats.watched, stats.rated, stats.liked), (4, 3, 3, 2))
        self.assertEqual(stats.average_rating, 4)
        self.assertEqual(sum(dict(stats.rating_distribution).values()), 3)
        self.assertEqual(dict(stats.rating_distribution)[4.5], 1)
        self.assertEqual(len(stats.rating_distribution), 10)
        self.assertEqual(stats.activity_by_year, ((2020, 1), (2021, 1)))
        self.assertEqual(stats.undated_events, 2)
        self.assertEqual(stats.decades, ((1990, 1), (2000, 1), (2010, 1)))
        self.assertEqual(stats.unknown_release_year, 1)
        self.assertEqual((stats.rewatch_events, stats.rewatched_movies, stats.multiple_logged_watches), (1, 1, 1))
        self.assertEqual((stats.canonical_watched, stats.canonical_total), (2, 100))

    def test_preferences_use_current_ratings_and_likes_not_watch_frequency(self):
        service = self.service(self.snapshot())
        stats = service.stats("user")
        drama = next(g for g in stats.genres if g.name == "Drama")
        self.assertEqual((drama.movies, drama.rated, drama.liked, drama.average_rating), (2, 1, 2, 4.5))
        self.assertEqual(service.highest_rated(stats.genres)[0].name, "Comedy")
        self.assertEqual(service.favorites(stats.genres)[0].name, "Drama")
        self.assertEqual((stats.genre_coverage, stats.director_coverage), (3, 2))

    def test_empty_account_and_missing_metadata(self):
        stats = self.service(AnalyticsSnapshot("empty", (), (), (), (), 0)).stats("empty")
        self.assertEqual(stats.movies, 0)
        self.assertIsNone(stats.average_rating)
        self.assertEqual(stats.genres, ())
        self.assertEqual(stats.canonical_total, 0)
        self.assertIsNone(self.service(None).stats("unknown"))

    def test_invalid_ratings_excluded_and_canonical_ids_deduplicated(self):
        snapshot = self.snapshot()
        snapshot = replace(snapshot, movies=snapshot.movies + (AnalyticsMovie(5, 0, 10, float("inf"), False),),
                           watches=snapshot.watches + (AnalyticsWatch(5, None, False, "letterboxd_watched"),))
        stats = self.service(snapshot).stats("user")
        self.assertEqual(stats.invalid_ratings, 1)
        self.assertEqual(stats.canonical_watched, 2)
        self.assertEqual(stats.unknown_release_year, 2)

    def test_rankings_have_deterministic_ties_and_limit(self):
        groups = [PreferenceStats(n, 1, 1, 1, 1, 4) for n in ("Z", "A", "B")]
        self.assertEqual([g.name for g in PersonalAnalyticsService.highest_rated(groups, 2)], ["A", "B"])
        self.assertEqual([g.name for g in PersonalAnalyticsService.favorites(groups, 2)], ["A", "B"])


class AnalyticsRepositoryAndCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "library.db"
        self.repo = PersonalLibraryRepository(self.path)
        canonical = DatabaseRepository(self.path)
        canonical.save_movies([
            MovieRecord("Film", 1999, "https://letterboxd.com/film/film/", rating=9.9,
                        director="A, B", genres="Drama, Adventure"),
            MovieRecord("Unseen", 2000, "https://letterboxd.com/film/unseen/"),
        ])
        film = canonical.get_movie_by_letterboxd_url("https://letterboxd.com/film/film/")
        unseen = canonical.get_movie_by_letterboxd_url("https://letterboxd.com/film/unseen/")
        account = self.repo.upsert_account(AccountRecord("letterboxd", "user"))
        self.account = account
        movie = self.repo.upsert_personal_movie(PersonalMovieRecord(
            account.id, "Film", 1999, "https://letterboxd.com/film/film/", canonical_movie_id=film.id))
        self.repo.save_watch_events([
            WatchEventRecord(account.id, movie.id, "2020-01-01", "entry1", "letterboxd_diary"),
            WatchEventRecord(account.id, movie.id, "2021-01-01", "entry2", "letterboxd_diary", True),
        ])
        self.repo.save_ratings([RatingRecord(account.id, movie.id, 4)])
        self.repo.save_likes([LikeRecord(account.id, movie.id)])
        # Other accounts and Phase 1 history must not leak into this account's stats.
        other = self.repo.upsert_account(AccountRecord("letterboxd", "other"))
        other_movie = self.repo.upsert_personal_movie(PersonalMovieRecord(
            other.id, "Unseen", 2000, "https://letterboxd.com/film/unseen/", canonical_movie_id=unseen.id))
        self.repo.save_watch_events([WatchEventRecord(other.id, other_movie.id, "1990-01-01", "other")])
        canonical.save_watched([WatchedRecord("Unseen", 2000, "2000-01-01", "https://letterboxd.com/film/unseen/")])

    def run_cli(self, username):
        stdout, stderr = StringIO(), StringIO()
        with patch("sys.argv", ["moviekit", "personal", "stats", "--username", username]), patch(
            "moviekit.config.load_config", return_value=MovieKitConfig(database_path=str(self.path))
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_repository_avoids_join_multiplication_and_is_read_only(self):
        before = self.path.read_bytes()
        snapshot = PersonalAnalyticsRepository(self.path).snapshot("user")
        self.assertEqual(len(snapshot.movies), 1)
        self.assertEqual(len(snapshot.watches), 2)
        self.assertEqual(len(snapshot.genres), 2)
        self.assertEqual(len(snapshot.directors), 2)
        self.assertEqual(snapshot.movies[0].rating, 4)  # not public TMDb score
        self.assertEqual(snapshot.canonical_total, 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_actor_credits_and_other_sources_are_excluded(self):
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute("INSERT INTO people(name) VALUES ('Actor only')")
                connection.execute(
                    "INSERT INTO movie_credits(movie_id, person_id, role) "
                    "SELECT movies.id, people.id, 'actor' FROM movies, people "
                    "WHERE movies.title = 'Film' AND people.name = 'Actor only'"
                )
        self.repo.upsert_account(AccountRecord("imdb", "user"))
        snapshot = PersonalAnalyticsRepository(self.path).snapshot("user")
        self.assertEqual({name for _, name in snapshot.directors}, {"A", "B"})
        self.assertEqual(len(snapshot.movies), 1)

    def test_cli_output_and_canonical_progress(self):
        code, output, error = self.run_cli(" USER ")
        self.assertEqual((code, error), (0, ""))
        for expected in ["Watched movies: 1", "Rated movies: 1", "4.0: 1", "2020: 1", "2021: 1",
                         "1990s: 1", "Explicit rewatch events: 1", "Drama: 4.00/5 (1 rated movies)",
                         "A: 1 liked movies", "Canonical 1001 progress (personal watches): 1/2 (50.0%)"]:
            self.assertIn(expected, output)
        self.assertNotIn("1990: 1", output)

    def test_cli_missing_account_and_empty_account(self):
        code, output, _ = self.run_cli("missing")
        self.assertEqual(code, 0)
        self.assertIn("No personal library found", output)
        self.repo.upsert_account(AccountRecord("letterboxd", "empty"))
        code, output, _ = self.run_cli("empty")
        self.assertEqual(code, 0)
        self.assertIn("Average personal rating: N/A", output)
        self.assertIn("Insufficient metadata", output)
        self.assertIn("No dated viewing activity", output)

    def test_missing_database_not_created(self):
        self.path = self.path.parent / "missing.db"
        code, _, error = self.run_cli("user")
        self.assertEqual(code, 1)
        self.assertIn("Import a personal library first", error)
        self.assertFalse(self.path.exists())

    def test_username_required(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            cli.build_parser().parse_args(["personal", "stats"])
        self.assertEqual(raised.exception.code, 2)
