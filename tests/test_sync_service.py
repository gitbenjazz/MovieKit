from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.provider_backend import ProviderAvailability
from moviekit.sync_service import SyncResult, SyncService


@dataclass(frozen=True)
class FakeMovie:
    id: int | None = 42
    title: str = "Heat"
    tmdb_id: int | None = 949


class FakeProviderService:
    def __init__(
        self,
        availability: list[ProviderAvailability] | None = None,
        search_error: Exception | None = None,
        save_error: Exception | None = None,
    ):
        self.availability = availability or []
        self.search_error = search_error
        self.save_error = save_error
        self.searched_movies = []
        self.saved_availability = []

    def search_movie_availability(self, movie):
        self.searched_movies.append(movie)
        if self.search_error is not None:
            raise self.search_error

        return self.availability

    def save_availability(self, movie_id, availability):
        self.saved_availability.append((movie_id, availability))
        if self.save_error is not None:
            raise self.save_error


class SyncServiceProviderTests(unittest.TestCase):
    def test_sync_movie_successfully_persists_availability(self) -> None:
        movie = FakeMovie()
        availability = [
            ProviderAvailability(
                provider_name="Prime Video",
                country_code="US",
                access_type="subscription",
            ),
            ProviderAvailability(
                provider_name="Prime Video",
                country_code="US",
                access_type="rent",
            ),
            ProviderAvailability(
                provider_name="Tubi",
                country_code="US",
                access_type="free",
            ),
        ]
        provider_service = FakeProviderService(availability)
        service = self._service(provider_service)

        result = service.sync_movie(movie)

        self.assertEqual(provider_service.searched_movies, [movie])
        self.assertEqual(provider_service.saved_availability, [(42, availability)])
        self.assertEqual(
            result,
            SyncResult(
                movie_title="Heat",
                movie_id=42,
                providers_discovered=["Prime Video", "Tubi"],
                providers_inserted=["Prime Video", "Tubi"],
                availability_records_written=3,
                success=True,
                error_message=None,
            ),
        )

    def test_sync_movie_reports_empty_availability(self) -> None:
        movie = FakeMovie()
        provider_service = FakeProviderService([])
        service = self._service(provider_service)

        result = service.sync_movie(movie)

        self.assertEqual(provider_service.searched_movies, [movie])
        self.assertEqual(provider_service.saved_availability, [(42, [])])
        self.assertTrue(result.success)
        self.assertEqual(result.providers_discovered, [])
        self.assertEqual(result.providers_inserted, [])
        self.assertEqual(result.availability_records_written, 0)
        self.assertEqual(result.error_message, "No availability returned")

    def test_sync_movie_reports_missing_tmdb_id(self) -> None:
        movie = FakeMovie(tmdb_id=None)
        provider_service = FakeProviderService(
            [ProviderAvailability(provider_name="Prime")]
        )
        service = self._service(provider_service)

        result = service.sync_movie(movie)

        self.assertFalse(result.success)
        self.assertEqual(result.movie_title, "Heat")
        self.assertEqual(result.movie_id, 42)
        self.assertEqual(result.error_message, "Movie is missing a TMDb ID")
        self.assertEqual(provider_service.searched_movies, [])
        self.assertEqual(provider_service.saved_availability, [])

    def test_sync_movie_reports_backend_exception(self) -> None:
        movie = FakeMovie()
        provider_service = FakeProviderService(search_error=RuntimeError("backend down"))
        service = self._service(provider_service)

        result = service.sync_movie(movie)

        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "backend down")
        self.assertEqual(result.providers_discovered, [])
        self.assertEqual(result.providers_inserted, [])
        self.assertEqual(result.availability_records_written, 0)
        self.assertEqual(provider_service.searched_movies, [movie])
        self.assertEqual(provider_service.saved_availability, [])

    def test_sync_movie_reports_persistence_exception(self) -> None:
        movie = FakeMovie()
        availability = [ProviderAvailability(provider_name="Prime")]
        provider_service = FakeProviderService(
            availability=availability,
            save_error=RuntimeError("database locked"),
        )
        service = self._service(provider_service)

        result = service.sync_movie(movie)

        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "database locked")
        self.assertEqual(result.providers_discovered, ["Prime"])
        self.assertEqual(result.providers_inserted, [])
        self.assertEqual(result.availability_records_written, 0)
        self.assertEqual(provider_service.saved_availability, [(42, availability)])

    def test_sync_movie_returns_structured_result_without_printing(self) -> None:
        movie = FakeMovie(id=7, title="Moonlight", tmdb_id=376867)
        provider_service = FakeProviderService(
            [ProviderAvailability(provider_name="Kanopy")]
        )
        service = self._service(provider_service)
        output = StringIO()

        with redirect_stdout(output):
            result = service.sync_movie(movie)

        self.assertIsInstance(result, SyncResult)
        self.assertEqual(result.movie_title, "Moonlight")
        self.assertEqual(result.movie_id, 7)
        self.assertEqual(result.providers_discovered, ["Kanopy"])
        self.assertEqual(result.providers_inserted, ["Kanopy"])
        self.assertEqual(result.availability_records_written, 1)
        self.assertTrue(result.success)
        self.assertEqual(output.getvalue(), "")

    def _service(self, provider_service: FakeProviderService) -> SyncService:
        return SyncService(
            movie_repository=object(),
            database_repository=object(),
            provider_service=provider_service,
        )


if __name__ == "__main__":
    unittest.main()
