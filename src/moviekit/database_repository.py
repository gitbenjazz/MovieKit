from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Iterable, Union

from .database import DEFAULT_DATABASE_PATH, initialize_database
from .models import MovieRecord, WatchedRecord

DatabasePath = Union[str, Path]


class DatabaseRepository:
    def __init__(self, database_path: DatabasePath = DEFAULT_DATABASE_PATH):
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def save_movies(self, movies: Iterable[MovieRecord]) -> None:
        rows = [self._movie_row(movie) for movie in movies]

        with sqlite3.connect(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO movies (
                    title,
                    year,
                    letterboxd_url
                )
                VALUES (?, ?, ?)
                ON CONFLICT(letterboxd_url) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    updated_at = datetime('now')
                """,
                rows,
            )

    def save_watched(self, watched: Iterable[WatchedRecord]) -> None:
        rows = [self._watched_row(item) for item in watched]

        with sqlite3.connect(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO watched (
                    title,
                    year,
                    watched_date,
                    letterboxd_uri
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(letterboxd_uri) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    watched_date = excluded.watched_date
                """,
                rows,
            )

    @staticmethod
    def _movie_row(movie: MovieRecord) -> tuple[str, int | None, str | None]:
        return (
            movie.title,
            movie.year,
            movie.letterboxd_url,
        )

    @staticmethod
    def _watched_row(
        watched: WatchedRecord,
    ) -> tuple[str, int | None, str | None, str | None]:
        return (
            watched.title,
            watched.year,
            watched.watched_date,
            watched.letterboxd_uri,
        )