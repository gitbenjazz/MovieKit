from __future__ import annotations

from dataclasses import dataclass

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


class SyncService:
    def __init__(
        self,
        movie_repository: MovieRepository | None = None,
        database_repository: DatabaseRepository | None = None,
    ):
        self.movie_repository = movie_repository or MovieRepository()
        self.database_repository = database_repository or DatabaseRepository()

    def sync(self) -> SyncSummary:
        movies, seen, unseen = self.movie_repository.update_watched_1001_outputs()

        movie_records = self.movie_repository.movie_records()
        watched_records = self.movie_repository.watched_records()

        self.database_repository.save_movies(movie_records)
        self.database_repository.save_watched(watched_records)

        return SyncSummary(
            total_movies=len(movies),
            watched_movies=len(seen),
            remaining_movies=len(unseen),
            movies_synced=len(movie_records),
            watched_history_synced=len(watched_records),
        )