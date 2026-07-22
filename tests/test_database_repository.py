from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.database_repository import DatabaseRepository, MovieSummary
from moviekit.models import MovieRecord, WatchedRecord


class DatabaseRepositoryTests(unittest.TestCase):
    def test_get_random_unwatched_returns_movie_summary_objects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title="Movie A",
                        year=2001,
                        letterboxd_url="https://letterboxd.com/film/movie-a/",
                    ),
                    MovieRecord(
                        title="Movie B",
                        year=2002,
                        letterboxd_url="https://letterboxd.com/film/movie-b/",
                    ),
                ]
            )

            movies = repository.get_random_unwatched()

        self.assertEqual(len(movies), 1)
        self.assertIsInstance(movies[0], MovieSummary)
        self.assertIn(movies[0].title, {"Movie A", "Movie B"})

    def test_get_random_unwatched_excludes_watched_movies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title="Watched Movie",
                        year=2001,
                        letterboxd_url="https://letterboxd.com/film/watched-movie/",
                    ),
                    MovieRecord(
                        title="Unwatched Movie",
                        year=2002,
                        letterboxd_url="https://letterboxd.com/film/unwatched-movie/",
                    ),
                ]
            )
            repository.save_watched(
                [
                    WatchedRecord(
                        title="Watched Movie",
                        year=2001,
                        watched_date="2026-07-13",
                        letterboxd_uri="https://boxd.it/watched",
                    )
                ]
            )

            movies = repository.get_random_unwatched(limit=10)

        self.assertEqual([movie.title for movie in movies], ["Unwatched Movie"])

    def test_get_random_unwatched_honors_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title=f"Movie {index}",
                        year=2000 + index,
                        letterboxd_url=f"https://letterboxd.com/film/movie-{index}/",
                    )
                    for index in range(5)
                ]
            )

            movies = repository.get_random_unwatched(limit=3)

        self.assertEqual(len(movies), 3)
        self.assertTrue(all(isinstance(movie, MovieSummary) for movie in movies))

    def test_get_random_unwatched_returns_empty_for_non_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title="Movie A",
                        year=2001,
                        letterboxd_url="https://letterboxd.com/film/movie-a/",
                    )
                ]
            )

            self.assertEqual(repository.get_random_unwatched(limit=0), [])
            self.assertEqual(repository.get_random_unwatched(limit=-1), [])

    def test_save_watched_does_not_create_movie_for_unmatched_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            repository = DatabaseRepository(database_path)
            repository.save_movies(
                [
                    MovieRecord(
                        title="Existing Movie",
                        year=2001,
                        letterboxd_url="https://letterboxd.com/film/existing-movie/",
                    )
                ]
            )
            before_count = self._movie_count(database_path)

            summary = repository.save_watched(
                [
                    WatchedRecord(
                        title="Missing Movie",
                        year=2002,
                        watched_date="2026-07-21",
                        letterboxd_uri="https://boxd.it/missing",
                    )
                ]
            )
            after_count = self._movie_count(database_path)

        self.assertEqual(before_count, 1)
        self.assertEqual(after_count, before_count)
        self.assertEqual(summary.imported, 0)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.skipped_reasons, {"no matching movie": 1})

    def test_save_watched_skips_unmatched_watched_movies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            repository = DatabaseRepository(database_path)
            repository.save_movies(
                [
                    MovieRecord(
                        title="Existing Movie",
                        year=2001,
                        letterboxd_url="https://letterboxd.com/film/existing-movie/",
                    )
                ]
            )

            summary = repository.save_watched(
                [
                    WatchedRecord(
                        title="Missing Movie",
                        year=2002,
                        watched_date="2026-07-21",
                        letterboxd_uri="https://boxd.it/missing",
                    )
                ]
            )
            watched_count = self._watched_count(database_path)

        self.assertEqual(watched_count, 0)
        self.assertEqual(summary.imported, 0)
        self.assertEqual(summary.skipped, 1)

    def test_save_watched_imports_matched_watched_movies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            repository = DatabaseRepository(database_path)
            repository.save_movies(
                [
                    MovieRecord(
                        title="Existing Movie",
                        year=2001,
                        letterboxd_url="https://letterboxd.com/film/existing-movie/",
                    )
                ]
            )

            summary = repository.save_watched(
                [
                    WatchedRecord(
                        title="Existing Movie",
                        year=2001,
                        watched_date="2026-07-21",
                        letterboxd_uri="https://boxd.it/existing",
                    )
                ]
            )
            watched_count = self._watched_count(database_path)

        self.assertEqual(watched_count, 1)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(summary.skipped, 0)
        self.assertEqual(summary.skipped_reasons, {})

    def _movie_count(self, database_path: Path) -> int:
        with closing(sqlite3.connect(database_path)) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0])

    def _watched_count(self, database_path: Path) -> int:
        with closing(sqlite3.connect(database_path)) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM watched").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
