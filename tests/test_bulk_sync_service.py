from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.bulk_sync_service import (
    BulkSyncResult,
    BulkSyncRunResult,
    BulkSyncService,
)
from moviekit.database_repository import DatabaseRepository, MovieSyncTarget
from moviekit.metadata_service import MetadataSyncResult
from moviekit.models import MovieRecord
from moviekit.sync_service import SyncResult


class BulkSyncServiceTests(unittest.TestCase):
    def test_sync_metadata_handles_empty_database(self) -> None:
        repository = FakeRepository([])
        metadata_service = FakeMetadataService({})
        service = BulkSyncService(
            repository=repository,
            metadata_service=metadata_service,
            availability_service=FakeAvailabilityService({}),
        )

        result = service.sync_metadata()

        self.assertEqual(result, BulkSyncResult(0, 0, 0, 0))
        self.assertEqual(metadata_service.synced_movies, [])

    def test_sync_metadata_aggregates_successful_skipped_and_failed_movies(self) -> None:
        movies = [
            self._movie(1, "Updated"),
            self._movie(2, "Skipped"),
            self._movie(3, "Failed Result"),
            self._movie(4, "Failed Exception"),
        ]
        metadata_service = FakeMetadataService(
            {
                1: MetadataSyncResult(
                    movie_title="Updated",
                    movie_id=1,
                    success=True,
                    updated=True,
                    tmdb_id=10,
                ),
                2: MetadataSyncResult(
                    movie_title="Skipped",
                    movie_id=2,
                    success=False,
                    updated=False,
                    error_message="No TMDb match found",
                ),
                3: MetadataSyncResult(
                    movie_title="Failed Result",
                    movie_id=3,
                    success=False,
                    updated=False,
                    error_message="TMDb request failed",
                ),
                4: RuntimeError("metadata backend down"),
            }
        )
        service = BulkSyncService(
            repository=FakeRepository(movies),
            metadata_service=metadata_service,
            availability_service=FakeAvailabilityService({}),
        )

        result = service.sync_metadata()

        self.assertEqual(result, BulkSyncResult(4, 1, 1, 2))
        self.assertEqual(metadata_service.synced_movies, movies)

    def test_sync_availability_aggregates_successful_skipped_and_failed_movies(
        self,
    ) -> None:
        movies = [
            self._movie(1, "Updated", tmdb_id=10),
            self._movie(2, "Empty", tmdb_id=20),
            self._movie(3, "Missing TMDb"),
            self._movie(4, "Failed", tmdb_id=40),
        ]
        availability_service = FakeAvailabilityService(
            {
                1: SyncResult(
                    movie_title="Updated",
                    movie_id=1,
                    providers_discovered=["Prime"],
                    providers_inserted=["Prime"],
                    availability_records_written=1,
                    success=True,
                ),
                2: SyncResult(
                    movie_title="Empty",
                    movie_id=2,
                    providers_discovered=[],
                    providers_inserted=[],
                    availability_records_written=0,
                    success=True,
                    error_message="No availability returned",
                ),
                3: SyncResult(
                    movie_title="Missing TMDb",
                    movie_id=3,
                    providers_discovered=[],
                    providers_inserted=[],
                    availability_records_written=0,
                    success=False,
                    error_message="Movie is missing a TMDb ID",
                ),
                4: RuntimeError("provider backend down"),
            }
        )
        service = BulkSyncService(
            repository=FakeRepository(movies),
            metadata_service=FakeMetadataService({}),
            availability_service=availability_service,
        )

        result = service.sync_availability()

        self.assertEqual(result, BulkSyncResult(4, 1, 2, 1))
        self.assertEqual(availability_service.synced_movies, movies)

    def test_sync_all_invokes_metadata_then_availability(self) -> None:
        calls = []

        class TrackingBulkSyncService(BulkSyncService):
            def sync_metadata(self) -> BulkSyncResult:
                calls.append("metadata")
                return BulkSyncResult(1, 1, 0, 0)

            def sync_availability(self) -> BulkSyncResult:
                calls.append("availability")
                return BulkSyncResult(1, 0, 1, 0)

        result = TrackingBulkSyncService(
            repository=FakeRepository([]),
            metadata_service=FakeMetadataService({}),
            availability_service=FakeAvailabilityService({}),
        ).sync_all()

        self.assertEqual(calls, ["metadata", "availability"])
        self.assertEqual(
            result,
            BulkSyncRunResult(
                metadata=BulkSyncResult(1, 1, 0, 0),
                availability=BulkSyncResult(1, 0, 1, 0),
            ),
        )

    def test_repository_get_all_movies_returns_lightweight_sync_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title="Alien",
                        year=1979,
                        letterboxd_url="https://letterboxd.com/film/alien/",
                        tmdb_id=348,
                        tmdb_title="Alien",
                        runtime=117,
                        director="Ridley Scott",
                        genres="Horror, Science Fiction",
                    )
                ]
            )

            movies = repository.get_all_movies()

        self.assertEqual(
            movies,
            [
                MovieSyncTarget(
                    id=1,
                    title="Alien",
                    year=1979,
                    letterboxd_url="https://letterboxd.com/film/alien/",
                    tmdb_id=348,
                )
            ],
        )

    def _movie(
        self,
        movie_id: int,
        title: str,
        tmdb_id: int | None = None,
    ) -> MovieSyncTarget:
        return MovieSyncTarget(
            id=movie_id,
            title=title,
            year=2000,
            letterboxd_url=f"https://letterboxd.com/film/{title.lower()}/",
            tmdb_id=tmdb_id,
        )


class FakeRepository:
    def __init__(self, movies: list[MovieSyncTarget]):
        self.movies = movies

    def get_all_movies(self) -> list[MovieSyncTarget]:
        return self.movies


@dataclass
class FakeMetadataService:
    results_by_movie_id: dict

    def __post_init__(self) -> None:
        self.synced_movies = []

    def sync_movie(self, movie):
        self.synced_movies.append(movie)
        result = self.results_by_movie_id.get(movie.id)
        if isinstance(result, Exception):
            raise result

        return result


@dataclass
class FakeAvailabilityService:
    results_by_movie_id: dict

    def __post_init__(self) -> None:
        self.synced_movies = []

    def sync_movie(self, movie):
        self.synced_movies.append(movie)
        result = self.results_by_movie_id.get(movie.id)
        if isinstance(result, Exception):
            raise result

        return result


if __name__ == "__main__":
    unittest.main()
