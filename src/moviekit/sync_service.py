from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .provider_service import ProviderService

if TYPE_CHECKING:
    from .database_repository import DatabaseRepository
    from .movie_repository import MovieRepository


@dataclass(frozen=True)
class SyncSummary:
    total_movies: int
    watched_movies: int
    remaining_movies: int
    movies_synced: int
    watched_history_synced: int

    @property
    def progress(self) -> float:
        if self.total_movies == 0:
            return 0.0

        return self.watched_movies / self.total_movies


@dataclass(frozen=True)
class SyncResult:
    movie_title: str
    movie_id: int | None
    providers_discovered: list[str]
    providers_inserted: list[str]
    availability_records_written: int
    success: bool
    error_message: str | None = None


class SyncService:
    def __init__(
        self,
        movie_repository: MovieRepository | None = None,
        database_repository: DatabaseRepository | None = None,
        provider_service: ProviderService | None = None,
    ):
        if database_repository is None:
            from .database_repository import DatabaseRepository

            database_repository = DatabaseRepository()

        self.movie_repository = movie_repository
        self.database_repository = database_repository
        self.provider_service = provider_service or ProviderService(
            self.database_repository
        )

    def sync(self) -> SyncSummary:
        movie_repository = self.movie_repository
        if movie_repository is None:
            from .movie_repository import MovieRepository

            movie_repository = MovieRepository()

        movies, seen, unseen = movie_repository.update_watched_1001_outputs()

        movie_records = movie_repository.movie_records()
        watched_records = movie_repository.watched_records()

        self.database_repository.save_movies(movie_records)
        self.database_repository.save_watched(watched_records)

        return SyncSummary(
            total_movies=len(movies),
            watched_movies=len(seen),
            remaining_movies=len(unseen),
            movies_synced=len(movie_records),
            watched_history_synced=len(watched_records),
        )

    def sync_movie(self, movie) -> SyncResult:
        movie_title = getattr(movie, "title", "Unknown")
        movie_id = getattr(movie, "id", None)
        tmdb_id = getattr(movie, "tmdb_id", None)

        if tmdb_id is None:
            return SyncResult(
                movie_title=movie_title,
                movie_id=movie_id,
                providers_discovered=[],
                providers_inserted=[],
                availability_records_written=0,
                success=False,
                error_message="Movie is missing a TMDb ID",
            )

        try:
            availability = self.provider_service.search_movie_availability(movie)
        except Exception as exc:
            return SyncResult(
                movie_title=movie_title,
                movie_id=movie_id,
                providers_discovered=[],
                providers_inserted=[],
                availability_records_written=0,
                success=False,
                error_message=str(exc),
            )

        providers = self._provider_names(availability)

        try:
            self.provider_service.save_availability(movie_id, availability)
        except Exception as exc:
            return SyncResult(
                movie_title=movie_title,
                movie_id=movie_id,
                providers_discovered=providers,
                providers_inserted=[],
                availability_records_written=0,
                success=False,
                error_message=str(exc),
            )

        return SyncResult(
            movie_title=movie_title,
            movie_id=movie_id,
            providers_discovered=providers,
            providers_inserted=providers,
            availability_records_written=len(availability),
            success=True,
            error_message=None if availability else "No availability returned",
        )

    @staticmethod
    def _provider_names(availability) -> list[str]:
        names = []
        for record in availability:
            provider_name = getattr(record, "provider_name", None)
            if provider_name is not None and provider_name not in names:
                names.append(provider_name)

        return names
