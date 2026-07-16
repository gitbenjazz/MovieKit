from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.database_repository import DatabaseRepository, MovieSummary
from moviekit.metadata_service import MetadataSyncService
from moviekit.models import MovieRecord
from moviekit.tmdb_client import TMDbAPIError, TMDbAuthenticationError


class FakeTMDbClient:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    def get_json(self, path: str, params=None) -> dict:
        self.calls.append((path, params))
        if self.error is not None:
            raise self.error

        return self.responses.get(path, {})


class MetadataSyncServiceTests(unittest.TestCase):
    def test_sync_movie_updates_existing_row_with_tmdb_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title="alien",
                        year=1979,
                        letterboxd_url="https://letterboxd.com/film/alien/",
                    )
                ]
            )
            movie = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/alien/"
            )
            client = FakeTMDbClient(
                {
                    "search/movie": {
                        "results": [
                            {
                                "id": 348,
                                "title": "Alien",
                                "release_date": "1979-05-25",
                            }
                        ]
                    },
                    "movie/348": {
                        "title": "Alien",
                        "runtime": 117,
                        "genres": [
                            {"name": "Horror"},
                            {"name": "Science Fiction"},
                        ],
                        "credits": {
                            "crew": [
                                {"job": "Director", "name": "Ridley Scott"},
                                {"job": "Producer", "name": "Gordon Carroll"},
                            ]
                        },
                    },
                }
            )

            result = MetadataSyncService(repository, client=client).sync_movie(movie)
            updated = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/alien/"
            )
            details = repository.get_movie_details(movie.id)
            all_movies = repository.search_movies("alien")

        self.assertTrue(result.success)
        self.assertTrue(result.updated)
        self.assertEqual(result.tmdb_id, 348)
        self.assertEqual(result.tmdb_title, "Alien")
        self.assertEqual(result.runtime, 117)
        self.assertEqual(result.director, "Ridley Scott")
        self.assertEqual(result.genres, ["Horror", "Science Fiction"])
        self.assertEqual(updated.id, movie.id)
        self.assertEqual(updated.tmdb_id, 348)
        self.assertEqual(updated.tmdb_title, "Alien")
        self.assertEqual(updated.runtime, 117)
        self.assertEqual(details.genres, ["Horror", "Science Fiction"])
        self.assertEqual(
            [credit.name for credit in details.credits if credit.role == "director"],
            ["Ridley Scott"],
        )
        self.assertEqual(len(all_movies), 1)
        self.assertEqual(
            client.calls,
            [
                (
                    "search/movie",
                    {
                        "query": "alien",
                        "year": 1979,
                    },
                ),
                (
                    "movie/348",
                    {"append_to_response": "credits"},
                ),
            ],
        )

    def test_sync_movie_reports_no_tmdb_match(self) -> None:
        movie = self._movie()
        client = FakeTMDbClient({"search/movie": {"results": []}})

        result = MetadataSyncService(
            database_repository=FakeRepository(),
            client=client,
        ).sync_movie(movie)

        self.assertFalse(result.success)
        self.assertFalse(result.updated)
        self.assertEqual(result.error_message, "No TMDb match found")

    def test_sync_movie_reports_missing_year(self) -> None:
        movie = self._movie(year=None)
        repository = FakeRepository()

        result = MetadataSyncService(repository, client=FakeTMDbClient()).sync_movie(
            movie
        )

        self.assertFalse(result.success)
        self.assertFalse(result.updated)
        self.assertEqual(
            result.error_message,
            "Movie year is required to resolve TMDb metadata",
        )
        self.assertEqual(repository.saved_movies, [])

    def test_sync_movie_reports_duplicate_candidates(self) -> None:
        movie = self._movie()
        client = FakeTMDbClient(
            {
                "search/movie": {
                    "results": [
                        {
                            "id": 1,
                            "title": "Alien",
                            "release_date": "1979-05-25",
                        },
                        {
                            "id": 2,
                            "title": "Alien",
                            "release_date": "1979-06-01",
                        },
                    ]
                }
            }
        )

        result = MetadataSyncService(FakeRepository(), client=client).sync_movie(movie)

        self.assertFalse(result.success)
        self.assertFalse(result.updated)
        self.assertEqual(result.error_message, "Multiple TMDb matches found")

    def test_sync_movie_propagates_api_failure(self) -> None:
        service = MetadataSyncService(
            FakeRepository(),
            client=FakeTMDbClient(error=TMDbAPIError("TMDb request failed")),
        )

        with self.assertRaises(TMDbAPIError):
            service.sync_movie(self._movie())

    def test_sync_movie_propagates_authentication_failure(self) -> None:
        service = MetadataSyncService(
            FakeRepository(),
            client=FakeTMDbClient(
                error=TMDbAuthenticationError("TMDb authentication failed")
            ),
        )

        with self.assertRaises(TMDbAuthenticationError):
            service.sync_movie(self._movie())

    def _movie(self, year: int | None = 1979) -> MovieSummary:
        return MovieSummary(
            id=1,
            title="alien",
            year=year,
            letterboxd_url="https://letterboxd.com/film/alien/",
            tmdb_id=None,
            tmdb_title=None,
            rating=None,
            runtime=None,
        )


class FakeRepository:
    def __init__(self):
        self.saved_movies = []

    def save_movies(self, movies):
        self.saved_movies.extend(movies)


if __name__ == "__main__":
    unittest.main()
