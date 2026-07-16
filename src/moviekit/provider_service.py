from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Iterable, Union

from .database import DEFAULT_DATABASE_PATH, initialize_database
from .provider_backend import (
    NullProviderBackend,
    ProviderAvailability,
    ProviderBackend,
)

DatabasePath = Union[str, Path]


class ProviderService:
    _PROVIDER_ALIASES = {
        "amazon prime video": "Prime",
        "prime video": "Prime",
        "prime": "Prime",
        "youtube": "YouTube",
        "pluto tv": "Pluto TV",
        "tubi": "Tubi",
        "plex": "Plex",
        "lacinetek": "LaCinetek",
    }

    def __init__(
        self,
        database: object = DEFAULT_DATABASE_PATH,
        backend: ProviderBackend | None = None,
    ):
        database_path = getattr(database, "database_path", database)
        self.database_path = Path(database_path)
        self._backend = backend or NullProviderBackend()
        initialize_database(self.database_path)

    def search_movie_availability(self, movie) -> list[ProviderAvailability]:
        return list(
            self._availability_records(
                self._backend.search_movie_availability(movie),
            )
        )

    def backend_name(self) -> str:
        return self._backend.backend_name()

    def get_movie_availability(self, movie) -> list[ProviderAvailability]:
        movie_id = self._movie_id(movie)

        with closing(self._connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    providers.name AS provider_name,
                    availability.country_code,
                    availability.access_type,
                    availability.fetched_at
                FROM availability
                JOIN providers
                    ON providers.id = availability.provider_id
                WHERE availability.movie_id = ?
                ORDER BY
                    providers.name,
                    availability.country_code,
                    availability.access_type
                """,
                (movie_id,),
            ).fetchall()

        return [
            ProviderAvailability(
                provider_name=row["provider_name"],
                country_code=row["country_code"],
                access_type=row["access_type"],
                fetched_at=row["fetched_at"],
            )
            for row in rows
        ]

    def get_movie_provider_names(self, movie) -> list[str]:
        return [
            availability.provider_name
            for availability in self.get_movie_availability(movie)
        ]

    def normalize_provider_name(self, name: str | None) -> str:
        if name is None:
            return ""

        normalized = " ".join(name.strip().split())
        return self._PROVIDER_ALIASES.get(normalized.casefold(), normalized)

    def save_availability(
        self,
        movie_id: int,
        providers: Iterable[str | ProviderAvailability],
    ) -> None:
        availability_records = list(self._availability_records(providers))

        with closing(self._connection()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM availability WHERE movie_id = ?",
                    (movie_id,),
                )

                for availability in availability_records:
                    provider_id = self._upsert_provider(
                        connection,
                        availability.provider_name,
                    )
                    self._upsert_country(connection, availability.country_code)
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO availability (
                            movie_id,
                            provider_id,
                            country_code,
                            access_type,
                            fetched_at
                        )
                        VALUES (?, ?, ?, ?, coalesce(?, datetime('now')))
                        """,
                        (
                            movie_id,
                            provider_id,
                            availability.country_code,
                            availability.access_type,
                            availability.fetched_at,
                        ),
                    )

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _availability_records(
        self,
        providers: Iterable[str | ProviderAvailability],
    ) -> Iterable[ProviderAvailability]:
        for provider in providers:
            if isinstance(provider, ProviderAvailability):
                provider_name = self.normalize_provider_name(provider.provider_name)
                country_code = provider.country_code.strip().upper()
                access_type = provider.access_type.strip().lower()
                fetched_at = provider.fetched_at
            else:
                provider_name = self.normalize_provider_name(provider)
                country_code = "US"
                access_type = "flatrate"
                fetched_at = None

            if provider_name and country_code and access_type:
                yield ProviderAvailability(
                    provider_name=provider_name,
                    country_code=country_code,
                    access_type=access_type,
                    fetched_at=fetched_at,
                )

    @staticmethod
    def _movie_id(movie) -> int:
        return int(getattr(movie, "id", movie))

    @staticmethod
    def _upsert_provider(connection: sqlite3.Connection, name: str) -> int:
        connection.execute(
            """
            INSERT INTO providers (name)
            VALUES (?)
            ON CONFLICT(name) DO NOTHING
            """,
            (name,),
        )
        row = connection.execute(
            "SELECT id FROM providers WHERE name = ?",
            (name,),
        ).fetchone()

        if row is None:
            raise sqlite3.IntegrityError("Provider upsert did not produce a row")

        return int(row["id"])

    @staticmethod
    def _upsert_country(connection: sqlite3.Connection, country_code: str) -> None:
        connection.execute(
            """
            INSERT INTO countries (code)
            VALUES (?)
            ON CONFLICT(code) DO NOTHING
            """,
            (country_code,),
        )
