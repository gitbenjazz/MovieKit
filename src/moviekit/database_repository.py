from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable, Union

from .database import DEFAULT_DATABASE_PATH, initialize_database
from .models import MovieRecord, WatchedRecord

DatabasePath = Union[str, Path]


@dataclass(frozen=True)
class MovieSummary:
    id: int
    title: str
    year: int | None
    letterboxd_url: str
    tmdb_id: int | None
    tmdb_title: str | None
    rating: float | None
    runtime: int | None


@dataclass(frozen=True)
class MovieCredit:
    person_id: int
    name: str
    role: str
    billing_order: int | None


@dataclass(frozen=True)
class MovieDetails:
    id: int
    title: str
    year: int | None
    letterboxd_url: str
    tmdb_id: int | None
    tmdb_title: str | None
    rating: float | None
    runtime: int | None
    genres: list[str]
    credits: list[MovieCredit]


class DatabaseRepository:
    def __init__(self, database_path: DatabasePath = DEFAULT_DATABASE_PATH):
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def save_movies(self, movies: Iterable[MovieRecord]) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")

            with connection:
                for movie in movies:
                    if movie.letterboxd_url is None:
                        continue

                    movie_id = self._upsert_movie(connection, movie)
                    self._replace_movie_genres(connection, movie_id, movie.genres)
                    self._replace_movie_directors(connection, movie_id, movie.director)

    def save_watched(self, watched: Iterable[WatchedRecord]) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")

            with connection:
                connection.execute("DELETE FROM watched")

                for item in watched:
                    if item.letterboxd_uri is None:
                        continue

                    movie_id = self._watched_movie_id(connection, item)
                    connection.execute(
                        """
                        INSERT INTO watched (
                            movie_id,
                            watched_date,
                            letterboxd_uri
                        )
                        VALUES (?, ?, ?)
                        """,
                        (movie_id, item.watched_date, item.letterboxd_uri),
                    )

                self._delete_duplicate_noncanonical_movies(connection)

    def get_movie_by_letterboxd_url(
        self,
        letterboxd_url: str,
    ) -> MovieSummary | None:
        with closing(self._read_connection()) as connection:
            row = connection.execute(
                f"""
                {self._movie_summary_select()}
                WHERE letterboxd_url = ?
                """,
                (letterboxd_url,),
            ).fetchone()

        return self._movie_summary_from_row(row) if row is not None else None

    def get_movie_by_tmdb_id(self, tmdb_id: int) -> MovieSummary | None:
        with closing(self._read_connection()) as connection:
            row = connection.execute(
                f"""
                {self._movie_summary_select()}
                WHERE tmdb_id = ?
                """,
                (tmdb_id,),
            ).fetchone()

        return self._movie_summary_from_row(row) if row is not None else None

    def search_movies(self, text: str) -> list[MovieSummary]:
        pattern = f"%{self._escape_like(text.strip().lower())}%"

        with closing(self._read_connection()) as connection:
            rows = connection.execute(
                f"""
                {self._movie_summary_select()}
                WHERE lower(title) LIKE ? ESCAPE '\\'
                    OR lower(coalesce(tmdb_title, '')) LIKE ? ESCAPE '\\'
                    OR coalesce(CAST(tmdb_id AS TEXT), '') LIKE ? ESCAPE '\\'
                    OR lower(letterboxd_url) LIKE ? ESCAPE '\\'
                ORDER BY title, year
                """,
                (pattern, pattern, pattern, pattern),
            ).fetchall()

        return [self._movie_summary_from_row(row) for row in rows]

    def get_unwatched_movies(self) -> list[MovieSummary]:
        with closing(self._read_connection()) as connection:
            rows = connection.execute(
                f"""
                {self._movie_summary_select()}
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM watched
                    WHERE watched.movie_id = movies.id
                )
                ORDER BY title, year
                """
            ).fetchall()

        return [self._movie_summary_from_row(row) for row in rows]

    def get_watched_movie_ids(self) -> set[int]:
        with closing(self._read_connection()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT movie_id
                FROM watched
                """
            ).fetchall()

        return {row["movie_id"] for row in rows}

    def get_movie_details(self, movie_id: int) -> MovieDetails | None:
        with closing(self._read_connection()) as connection:
            movie = connection.execute(
                f"""
                {self._movie_summary_select()}
                WHERE id = ?
                """,
                (movie_id,),
            ).fetchone()

            if movie is None:
                return None

            genres = [
                row["name"]
                for row in connection.execute(
                    """
                    SELECT genres.name
                    FROM movie_genres
                    JOIN genres
                        ON genres.id = movie_genres.genre_id
                    WHERE movie_genres.movie_id = ?
                    ORDER BY genres.name
                    """,
                    (movie_id,),
                ).fetchall()
            ]
            credits = [
                MovieCredit(
                    person_id=row["person_id"],
                    name=row["name"],
                    role=row["role"],
                    billing_order=row["billing_order"],
                )
                for row in connection.execute(
                    """
                    SELECT
                        people.id AS person_id,
                        people.name,
                        movie_credits.role,
                        movie_credits.billing_order
                    FROM movie_credits
                    JOIN people
                        ON people.id = movie_credits.person_id
                    WHERE movie_credits.movie_id = ?
                    ORDER BY
                        movie_credits.role,
                        movie_credits.billing_order,
                        people.name
                    """,
                    (movie_id,),
                ).fetchall()
            ]

        return MovieDetails(
            id=movie["id"],
            title=movie["title"],
            year=movie["year"],
            letterboxd_url=movie["letterboxd_url"],
            tmdb_id=movie["tmdb_id"],
            tmdb_title=movie["tmdb_title"],
            rating=movie["rating"],
            runtime=movie["runtime"],
            genres=genres,
            credits=credits,
        )

    @staticmethod
    def _watched_movie_id(
        connection: sqlite3.Connection,
        watched: WatchedRecord,
    ) -> int:
        row = connection.execute(
            """
            SELECT id
            FROM movies
            WHERE lower(title) = lower(?)
                AND (
                    year = ?
                    OR (year IS NULL AND ? IS NULL)
                )
            ORDER BY
                CASE
                    WHEN letterboxd_url LIKE 'https://letterboxd.com/film/%' THEN 0
                    ELSE 1
                END,
                id
            LIMIT 1
            """,
            (watched.title, watched.year, watched.year),
        ).fetchone()

        if row is not None:
            return int(row[0])

        return DatabaseRepository._upsert_movie(
            connection,
            MovieRecord(
                title=watched.title,
                year=watched.year,
                letterboxd_url=watched.letterboxd_uri,
            ),
        )

    @staticmethod
    def _delete_duplicate_noncanonical_movies(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM movies
            WHERE letterboxd_url NOT LIKE 'https://letterboxd.com/film/%'
                AND EXISTS (
                    SELECT 1
                    FROM movies AS canonical
                    WHERE canonical.id != movies.id
                        AND canonical.letterboxd_url
                            LIKE 'https://letterboxd.com/film/%'
                        AND lower(canonical.title) = lower(movies.title)
                        AND (
                            canonical.year = movies.year
                            OR (
                                canonical.year IS NULL
                                AND movies.year IS NULL
                            )
                        )
                )
            """
        )

    @staticmethod
    def _upsert_movie(connection: sqlite3.Connection, movie: MovieRecord) -> int:
        connection.execute(
            """
            INSERT INTO movies (
                title,
                year,
                letterboxd_url,
                tmdb_id,
                tmdb_title,
                rating,
                runtime
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(letterboxd_url) DO UPDATE SET
                title = excluded.title,
                year = coalesce(excluded.year, movies.year),
                tmdb_id = coalesce(excluded.tmdb_id, movies.tmdb_id),
                tmdb_title = coalesce(excluded.tmdb_title, movies.tmdb_title),
                rating = coalesce(excluded.rating, movies.rating),
                runtime = coalesce(excluded.runtime, movies.runtime),
                updated_at = datetime('now')
            """,
            DatabaseRepository._movie_row(movie),
        )
        row = connection.execute(
            "SELECT id FROM movies WHERE letterboxd_url = ?",
            (movie.letterboxd_url,),
        ).fetchone()

        if row is None:
            raise sqlite3.IntegrityError("Movie upsert did not produce a row")

        return int(row[0])

    @staticmethod
    def _replace_movie_genres(
        connection: sqlite3.Connection,
        movie_id: int,
        genres: str | None,
    ) -> None:
        connection.execute("DELETE FROM movie_genres WHERE movie_id = ?", (movie_id,))

        for genre in DatabaseRepository._split_names(genres):
            genre_id = DatabaseRepository._upsert_lookup(
                connection,
                table="genres",
                value=genre,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO movie_genres (
                    movie_id,
                    genre_id
                )
                VALUES (?, ?)
                """,
                (movie_id, genre_id),
            )

    @staticmethod
    def _replace_movie_directors(
        connection: sqlite3.Connection,
        movie_id: int,
        director: str | None,
    ) -> None:
        connection.execute(
            """
            DELETE FROM movie_credits
            WHERE movie_id = ?
                AND role = 'director'
            """,
            (movie_id,),
        )

        for billing_order, name in enumerate(
            DatabaseRepository._split_names(director),
            start=1,
        ):
            person_id = DatabaseRepository._upsert_lookup(
                connection,
                table="people",
                value=name,
            )
            connection.execute(
                """
                INSERT INTO movie_credits (
                    movie_id,
                    person_id,
                    role,
                    billing_order
                )
                VALUES (?, ?, 'director', ?)
                ON CONFLICT(movie_id, person_id, role) DO UPDATE SET
                    billing_order = excluded.billing_order
                """,
                (movie_id, person_id, billing_order),
        )

    def _read_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _movie_summary_select() -> str:
        return """
        SELECT
            id,
            title,
            year,
            letterboxd_url,
            tmdb_id,
            tmdb_title,
            rating,
            runtime
        FROM movies
        """

    @staticmethod
    def _movie_summary_from_row(row: sqlite3.Row) -> MovieSummary:
        return MovieSummary(
            id=row["id"],
            title=row["title"],
            year=row["year"],
            letterboxd_url=row["letterboxd_url"],
            tmdb_id=row["tmdb_id"],
            tmdb_title=row["tmdb_title"],
            rating=row["rating"],
            runtime=row["runtime"],
        )

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _upsert_lookup(
        connection: sqlite3.Connection,
        table: str,
        value: str,
    ) -> int:
        connection.execute(
            f"INSERT INTO {table} (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
            (value,),
        )
        row = connection.execute(
            f"SELECT id FROM {table} WHERE name = ?",
            (value,),
        ).fetchone()

        if row is None:
            raise sqlite3.IntegrityError(f"{table} upsert did not produce a row")

        return int(row[0])

    @staticmethod
    def _split_names(value: str | None) -> list[str]:
        if value is None:
            return []

        normalized = value.replace("|", ",").replace(";", ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]

    @staticmethod
    def _movie_row(
        movie: MovieRecord,
    ) -> tuple[
        str,
        int | None,
        str | None,
        int | None,
        str | None,
        float | None,
        int | None,
    ]:
        return (
            movie.title,
            movie.year,
            movie.letterboxd_url,
            movie.tmdb_id,
            movie.tmdb_title,
            movie.rating,
            movie.runtime,
        )
