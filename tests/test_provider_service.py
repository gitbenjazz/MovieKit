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

from moviekit.database_repository import DatabaseRepository
from moviekit.models import MovieRecord
from moviekit.provider_service import ProviderAvailability, ProviderService


class ProviderServiceTests(unittest.TestCase):
    def test_normalize_provider_name_strips_whitespace_and_aliases_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = ProviderService(Path(directory) / "movies.db")

            self.assertEqual(service.normalize_provider_name("  Prime  "), "Prime")
            self.assertEqual(
                service.normalize_provider_name("Amazon   Prime Video"),
                "Prime",
            )
            self.assertEqual(service.normalize_provider_name("pluto   tv"), "Pluto TV")
            self.assertEqual(service.normalize_provider_name(" LaCinetek "), "LaCinetek")
            self.assertEqual(service.normalize_provider_name(""), "")
            self.assertEqual(service.normalize_provider_name(None), "")

    def test_save_availability_inserts_new_providers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            movie = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/heat-1995/",
            )
            service = ProviderService(repository)

            service.save_availability(movie.id, ["Prime", "Tubi"])

            availability = service.get_movie_availability(movie)
            self.assertEqual(
                [item.provider_name for item in availability],
                ["Prime", "Tubi"],
            )
            self.assertEqual(self._count(directory, "providers"), 2)
            self.assertEqual(self._count(directory, "availability"), 2)

    def test_save_availability_reuses_existing_providers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(
                directory,
                [
                    MovieRecord(
                        title="Heat",
                        year=1995,
                        letterboxd_url="https://letterboxd.com/film/heat-1995/",
                    ),
                    MovieRecord(
                        title="Thief",
                        year=1981,
                        letterboxd_url="https://letterboxd.com/film/thief/",
                    ),
                ],
            )
            heat = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/heat-1995/",
            )
            thief = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/thief/",
            )
            service = ProviderService(repository)

            service.save_availability(heat.id, ["Prime"])
            service.save_availability(thief.id, ["Prime"])

            self.assertEqual(self._count(directory, "providers"), 1)
            self.assertEqual(self._count(directory, "availability"), 2)

    def test_save_availability_replaces_existing_records_for_movie(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            movie = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/heat-1995/",
            )
            service = ProviderService(repository)

            service.save_availability(movie.id, ["Prime", "Tubi"])
            service.save_availability(
                movie.id,
                [
                    ProviderAvailability(
                        provider_name="YouTube",
                        country_code="ca",
                        access_type="rent",
                        fetched_at="2026-07-15T12:00:00",
                    )
                ],
            )

            availability = service.get_movie_availability(movie.id)
            self.assertEqual(len(availability), 1)
            self.assertEqual(availability[0].provider_name, "YouTube")
            self.assertEqual(availability[0].country_code, "CA")
            self.assertEqual(availability[0].access_type, "rent")
            self.assertEqual(availability[0].fetched_at, "2026-07-15T12:00:00")

    def test_save_availability_rolls_back_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            movie = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/heat-1995/",
            )
            service = ProviderService(repository)
            service.save_availability(movie.id, ["Prime"])

            with self.assertRaises(sqlite3.IntegrityError):
                service.save_availability(9999, ["Tubi"])

            self.assertEqual(service.get_movie_provider_names(movie.id), ["Prime"])
            self.assertEqual(self._provider_names(directory), ["Prime"])
            self.assertEqual(self._count(directory, "availability"), 1)

    def test_save_availability_accepts_empty_provider_lists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            movie = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/heat-1995/",
            )
            service = ProviderService(repository)

            service.save_availability(movie.id, ["Prime"])
            service.save_availability(movie.id, [])

            self.assertEqual(service.get_movie_availability(movie.id), [])
            self.assertEqual(self._count(directory, "availability"), 0)
            self.assertEqual(self._provider_names(directory), ["Prime"])

    def test_database_repository_get_movie_providers_uses_provider_service(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            movie = repository.get_movie_by_letterboxd_url(
                "https://letterboxd.com/film/heat-1995/",
            )
            ProviderService(repository).save_availability(movie.id, ["Prime"])

            self.assertEqual(repository.get_movie_providers(movie.id), ["Prime"])

    def _repository(
        self,
        directory: str,
        movies: list[MovieRecord] | None = None,
    ) -> DatabaseRepository:
        repository = DatabaseRepository(Path(directory) / "movies.db")
        repository.save_movies(
            movies
            or [
                MovieRecord(
                    title="Heat",
                    year=1995,
                    letterboxd_url="https://letterboxd.com/film/heat-1995/",
                )
            ]
        )
        return repository

    def _count(self, directory: str, table: str) -> int:
        with closing(sqlite3.connect(Path(directory) / "movies.db")) as connection:
            row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()

        return int(row[0])

    def _provider_names(self, directory: str) -> list[str]:
        with closing(sqlite3.connect(Path(directory) / "movies.db")) as connection:
            rows = connection.execute(
                "SELECT name FROM providers ORDER BY name",
            ).fetchall()

        return [row[0] for row in rows]


if __name__ == "__main__":
    unittest.main()
