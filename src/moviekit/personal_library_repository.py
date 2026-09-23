from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable, Union

from .database import initialize_database

DatabasePath = Union[str, Path]


@dataclass(frozen=True)
class AccountRecord:
    source: str
    username: str
    display_name: str | None = None
    profile_url: str | None = None


@dataclass(frozen=True)
class Account:
    id: int
    source: str
    username: str
    display_name: str | None
    profile_url: str | None


@dataclass(frozen=True)
class PersonalMovieRecord:
    account_id: int
    title: str
    year: int | None = None
    letterboxd_url: str | None = None
    letterboxd_uri: str | None = None
    canonical_movie_id: int | None = None


@dataclass(frozen=True)
class PersonalMovie:
    id: int
    account_id: int
    canonical_movie_id: int | None
    title: str
    year: int | None
    letterboxd_url: str | None
    letterboxd_uri: str | None


@dataclass(frozen=True)
class WatchEventRecord:
    account_id: int
    personal_movie_id: int
    watched_date: str | None = None
    letterboxd_uri: str | None = None
    source: str = "letterboxd"
    is_rewatch: bool = False


@dataclass(frozen=True)
class WatchEvent:
    id: int
    account_id: int
    personal_movie_id: int
    watched_date: str | None
    letterboxd_uri: str | None
    source: str
    is_rewatch: bool


@dataclass(frozen=True)
class RatingRecord:
    account_id: int
    personal_movie_id: int
    rating: float
    rated_at: str | None = None


@dataclass(frozen=True)
class Rating:
    account_id: int
    personal_movie_id: int
    rating: float
    rated_at: str | None


@dataclass(frozen=True)
class ReviewRecord:
    account_id: int
    personal_movie_id: int
    watch_event_id: int | None = None
    review_uri: str | None = None
    review_text: str | None = None
    rating: float | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True)
class Review:
    id: int
    account_id: int
    personal_movie_id: int
    watch_event_id: int | None
    review_uri: str | None
    review_text: str | None
    rating: float | None
    reviewed_at: str | None


@dataclass(frozen=True)
class LikeRecord:
    account_id: int
    personal_movie_id: int
    liked_at: str | None = None
    source_uri: str | None = None


@dataclass(frozen=True)
class Like:
    account_id: int
    personal_movie_id: int
    liked_at: str | None
    source_uri: str | None


@dataclass(frozen=True)
class PersonalLibraryData:
    account: Account
    movies: list[PersonalMovie]
    watch_events: list[WatchEvent]
    ratings: list[Rating]
    reviews: list[Review]
    likes: list[Like]


class PersonalLibraryRepository:
    def __init__(self, database_path: DatabasePath | None = None):
        if database_path is None:
            from .config import load_config

            database_path = load_config().database_path
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def upsert_account(self, account: AccountRecord) -> Account:
        with closing(self._connection()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO accounts (
                        source,
                        username,
                        display_name,
                        profile_url
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(source, username) DO UPDATE SET
                        display_name = excluded.display_name,
                        profile_url = excluded.profile_url,
                        updated_at = datetime('now')
                    """,
                    (
                        account.source,
                        account.username,
                        account.display_name,
                        account.profile_url,
                    ),
                )
                row = self._account_row(
                    connection,
                    source=account.source,
                    username=account.username,
                )

        if row is None:
            raise sqlite3.IntegrityError("Account upsert did not produce a row")

        return self._account_from_row(row)

    def find_account(self, source: str, username: str) -> Account | None:
        with closing(self._connection()) as connection:
            row = self._account_row(connection, source=source, username=username)

        return self._account_from_row(row) if row is not None else None

    def get_account(self, account_id: int) -> Account | None:
        with closing(self._connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    source,
                    username,
                    display_name,
                    profile_url
                FROM accounts
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()

        return self._account_from_row(row) if row is not None else None

    def upsert_personal_movie(self, movie: PersonalMovieRecord) -> PersonalMovie:
        with closing(self._connection()) as connection:
            with connection:
                existing = self._find_personal_movie_row(
                    connection,
                    account_id=movie.account_id,
                    letterboxd_url=movie.letterboxd_url,
                    letterboxd_uri=movie.letterboxd_uri,
                )

                if existing is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO personal_movies (
                            account_id,
                            canonical_movie_id,
                            title,
                            year,
                            letterboxd_url,
                            letterboxd_uri
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        self._personal_movie_values(movie),
                    )
                    personal_movie_id = int(cursor.lastrowid)
                else:
                    personal_movie_id = int(existing["id"])
                    connection.execute(
                        """
                        UPDATE personal_movies
                        SET
                            canonical_movie_id = ?,
                            title = ?,
                            year = ?,
                            letterboxd_url = coalesce(?, letterboxd_url),
                            letterboxd_uri = coalesce(?, letterboxd_uri),
                            updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (
                            movie.canonical_movie_id,
                            movie.title,
                            movie.year,
                            movie.letterboxd_url,
                            movie.letterboxd_uri,
                            personal_movie_id,
                        ),
                    )

                row = self._personal_movie_row(connection, personal_movie_id)

        if row is None:
            raise sqlite3.IntegrityError("Personal movie upsert did not produce a row")

        return self._personal_movie_from_row(row)

    def find_personal_movie(
        self,
        account_id: int,
        *,
        letterboxd_url: str | None = None,
        letterboxd_uri: str | None = None,
    ) -> PersonalMovie | None:
        with closing(self._connection()) as connection:
            row = self._find_personal_movie_row(
                connection,
                account_id=account_id,
                letterboxd_url=letterboxd_url,
                letterboxd_uri=letterboxd_uri,
            )

        return self._personal_movie_from_row(row) if row is not None else None

    def get_personal_movie(self, personal_movie_id: int) -> PersonalMovie | None:
        with closing(self._connection()) as connection:
            row = self._personal_movie_row(connection, personal_movie_id)

        return self._personal_movie_from_row(row) if row is not None else None

    def link_personal_movie_to_canonical(
        self,
        personal_movie_id: int,
        canonical_movie_id: int,
    ) -> PersonalMovie:
        with closing(self._connection()) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE personal_movies
                    SET
                        canonical_movie_id = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (canonical_movie_id, personal_movie_id),
                )
                row = self._personal_movie_row(connection, personal_movie_id)

        if row is None:
            raise sqlite3.IntegrityError("Personal movie does not exist")

        return self._personal_movie_from_row(row)

    def save_watch_events(
        self,
        events: Iterable[WatchEventRecord],
    ) -> list[WatchEvent]:
        event_list = list(events)

        with closing(self._connection()) as connection:
            with connection:
                event_ids = [
                    self._save_watch_event(connection, event) for event in event_list
                ]
                rows = [
                    self._watch_event_row(connection, event_id)
                    for event_id in event_ids
                ]

        return [self._watch_event_from_row(row) for row in rows if row is not None]

    def save_ratings(self, ratings: Iterable[RatingRecord]) -> list[Rating]:
        rating_list = list(ratings)

        with closing(self._connection()) as connection:
            with connection:
                for rating in rating_list:
                    connection.execute(
                        """
                        INSERT INTO ratings (
                            account_id,
                            personal_movie_id,
                            rating,
                            rated_at
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(account_id, personal_movie_id) DO UPDATE SET
                            rating = excluded.rating,
                            rated_at = excluded.rated_at,
                            updated_at = datetime('now')
                        """,
                        (
                            rating.account_id,
                            rating.personal_movie_id,
                            rating.rating,
                            rating.rated_at,
                        ),
                    )
                rows = [
                    self._rating_row(
                        connection,
                        rating.account_id,
                        rating.personal_movie_id,
                    )
                    for rating in rating_list
                ]

        return [self._rating_from_row(row) for row in rows if row is not None]

    def save_reviews(self, reviews: Iterable[ReviewRecord]) -> list[Review]:
        review_list = list(reviews)

        with closing(self._connection()) as connection:
            with connection:
                review_ids = [
                    self._save_review(connection, review) for review in review_list
                ]
                rows = [
                    self._review_row(connection, review_id)
                    for review_id in review_ids
                ]

        return [self._review_from_row(row) for row in rows if row is not None]

    def save_likes(self, likes: Iterable[LikeRecord]) -> list[Like]:
        like_list = list(likes)

        with closing(self._connection()) as connection:
            with connection:
                for like in like_list:
                    connection.execute(
                        """
                        INSERT INTO likes (
                            account_id,
                            personal_movie_id,
                            liked_at,
                            source_uri
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(account_id, personal_movie_id) DO UPDATE SET
                            liked_at = excluded.liked_at,
                            source_uri = excluded.source_uri,
                            updated_at = datetime('now')
                        """,
                        (
                            like.account_id,
                            like.personal_movie_id,
                            like.liked_at,
                            like.source_uri,
                        ),
                    )
                rows = [
                    self._like_row(connection, like.account_id, like.personal_movie_id)
                    for like in like_list
                ]

        return [self._like_from_row(row) for row in rows if row is not None]

    def get_watch_events(
        self,
        account_id: int,
        personal_movie_id: int | None = None,
    ) -> list[WatchEvent]:
        query = """
            SELECT
                id,
                account_id,
                personal_movie_id,
                watched_date,
                letterboxd_uri,
                source,
                is_rewatch
            FROM watch_events
            WHERE account_id = ?
        """
        parameters: list[object] = [account_id]

        if personal_movie_id is not None:
            query += " AND personal_movie_id = ?"
            parameters.append(personal_movie_id)

        query += " ORDER BY watched_date, id"

        with closing(self._connection()) as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [self._watch_event_from_row(row) for row in rows]

    def get_rating(
        self,
        account_id: int,
        personal_movie_id: int,
    ) -> Rating | None:
        with closing(self._connection()) as connection:
            row = self._rating_row(connection, account_id, personal_movie_id)

        return self._rating_from_row(row) if row is not None else None

    def get_reviews(
        self,
        account_id: int,
        personal_movie_id: int | None = None,
    ) -> list[Review]:
        query = """
            SELECT
                id,
                account_id,
                personal_movie_id,
                watch_event_id,
                review_uri,
                review_text,
                rating,
                reviewed_at
            FROM reviews
            WHERE account_id = ?
        """
        parameters: list[object] = [account_id]

        if personal_movie_id is not None:
            query += " AND personal_movie_id = ?"
            parameters.append(personal_movie_id)

        query += " ORDER BY reviewed_at, id"

        with closing(self._connection()) as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [self._review_from_row(row) for row in rows]

    def get_like(
        self,
        account_id: int,
        personal_movie_id: int,
    ) -> Like | None:
        with closing(self._connection()) as connection:
            row = self._like_row(connection, account_id, personal_movie_id)

        return self._like_from_row(row) if row is not None else None

    def get_personal_movies(self, account_id: int) -> list[PersonalMovie]:
        with closing(self._connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    account_id,
                    canonical_movie_id,
                    title,
                    year,
                    letterboxd_url,
                    letterboxd_uri
                FROM personal_movies
                WHERE account_id = ?
                ORDER BY title, year, id
                """,
                (account_id,),
            ).fetchall()

        return [self._personal_movie_from_row(row) for row in rows]

    def get_personal_library(self, account_id: int) -> PersonalLibraryData | None:
        account = self.get_account(account_id)
        if account is None:
            return None

        return PersonalLibraryData(
            account=account,
            movies=self.get_personal_movies(account_id),
            watch_events=self.get_watch_events(account_id),
            ratings=self._get_ratings(account_id),
            reviews=self.get_reviews(account_id),
            likes=self._get_likes(account_id),
        )

    def _save_watch_event(
        self,
        connection: sqlite3.Connection,
        event: WatchEventRecord,
    ) -> int:
        if event.letterboxd_uri is None:
            cursor = connection.execute(
                """
                INSERT INTO watch_events (
                    account_id,
                    personal_movie_id,
                    watched_date,
                    letterboxd_uri,
                    source,
                    is_rewatch
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                self._watch_event_values(event),
            )
            return int(cursor.lastrowid)

        connection.execute(
            """
            INSERT INTO watch_events (
                account_id,
                personal_movie_id,
                watched_date,
                letterboxd_uri,
                source,
                is_rewatch
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, letterboxd_uri) DO UPDATE SET
                personal_movie_id = excluded.personal_movie_id,
                watched_date = excluded.watched_date,
                source = excluded.source,
                is_rewatch = excluded.is_rewatch,
                updated_at = datetime('now')
            """,
            self._watch_event_values(event),
        )
        row = connection.execute(
            """
            SELECT id
            FROM watch_events
            WHERE account_id = ?
                AND letterboxd_uri = ?
            """,
            (event.account_id, event.letterboxd_uri),
        ).fetchone()

        if row is None:
            raise sqlite3.IntegrityError("Watch event upsert did not produce a row")

        return int(row["id"])

    def _save_review(
        self,
        connection: sqlite3.Connection,
        review: ReviewRecord,
    ) -> int:
        if review.watch_event_id is not None:
            event = self._watch_event_row(connection, review.watch_event_id)
            if event is None or (event["account_id"], event["personal_movie_id"]) != (
                review.account_id, review.personal_movie_id
            ):
                raise sqlite3.IntegrityError("Review watch event must belong to the same account and movie")
        if review.review_uri is None:
            cursor = connection.execute(
                """
                INSERT INTO reviews (
                    account_id,
                    personal_movie_id,
                    watch_event_id,
                    review_uri,
                    review_text,
                    rating,
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                self._review_values(review),
            )
            return int(cursor.lastrowid)

        connection.execute(
            """
            INSERT INTO reviews (
                account_id,
                personal_movie_id,
                watch_event_id,
                review_uri,
                review_text,
                rating,
                reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, review_uri) DO UPDATE SET
                personal_movie_id = excluded.personal_movie_id,
                watch_event_id = excluded.watch_event_id,
                review_text = excluded.review_text,
                rating = excluded.rating,
                reviewed_at = excluded.reviewed_at,
                updated_at = datetime('now')
            """,
            self._review_values(review),
        )
        row = connection.execute(
            """
            SELECT id
            FROM reviews
            WHERE account_id = ?
                AND review_uri = ?
            """,
            (review.account_id, review.review_uri),
        ).fetchone()

        if row is None:
            raise sqlite3.IntegrityError("Review upsert did not produce a row")

        return int(row["id"])

    def _get_ratings(self, account_id: int) -> list[Rating]:
        with closing(self._connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    account_id,
                    personal_movie_id,
                    rating,
                    rated_at
                FROM ratings
                WHERE account_id = ?
                ORDER BY personal_movie_id
                """,
                (account_id,),
            ).fetchall()

        return [self._rating_from_row(row) for row in rows]

    def _get_likes(self, account_id: int) -> list[Like]:
        with closing(self._connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    account_id,
                    personal_movie_id,
                    liked_at,
                    source_uri
                FROM likes
                WHERE account_id = ?
                ORDER BY personal_movie_id
                """,
                (account_id,),
            ).fetchall()

        return [self._like_from_row(row) for row in rows]

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _account_row(
        connection: sqlite3.Connection,
        *,
        source: str,
        username: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                source,
                username,
                display_name,
                profile_url
            FROM accounts
            WHERE source = ?
                AND username = ?
            """,
            (source, username),
        ).fetchone()

    @staticmethod
    def _personal_movie_row(
        connection: sqlite3.Connection,
        personal_movie_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                account_id,
                canonical_movie_id,
                title,
                year,
                letterboxd_url,
                letterboxd_uri
            FROM personal_movies
            WHERE id = ?
            """,
            (personal_movie_id,),
        ).fetchone()

    @staticmethod
    def _find_personal_movie_row(
        connection: sqlite3.Connection,
        *,
        account_id: int,
        letterboxd_url: str | None,
        letterboxd_uri: str | None,
    ) -> sqlite3.Row | None:
        if letterboxd_url is None and letterboxd_uri is None:
            return None

        rows = connection.execute(
            """
            SELECT
                id,
                account_id,
                canonical_movie_id,
                title,
                year,
                letterboxd_url,
                letterboxd_uri
            FROM personal_movies
            WHERE account_id = ?
                AND (
                    (? IS NOT NULL AND letterboxd_url = ?)
                    OR (? IS NOT NULL AND letterboxd_uri = ?)
                )
            ORDER BY id
            LIMIT 2
            """,
            (
                account_id,
                letterboxd_url,
                letterboxd_url,
                letterboxd_uri,
                letterboxd_uri,
            ),
        ).fetchall()
        if len(rows) > 1:
            raise sqlite3.IntegrityError("Conflicting personal movie identities")
        return rows[0] if rows else None

    @staticmethod
    def _watch_event_row(
        connection: sqlite3.Connection,
        watch_event_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                account_id,
                personal_movie_id,
                watched_date,
                letterboxd_uri,
                source,
                is_rewatch
            FROM watch_events
            WHERE id = ?
            """,
            (watch_event_id,),
        ).fetchone()

    @staticmethod
    def _rating_row(
        connection: sqlite3.Connection,
        account_id: int,
        personal_movie_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                account_id,
                personal_movie_id,
                rating,
                rated_at
            FROM ratings
            WHERE account_id = ?
                AND personal_movie_id = ?
            """,
            (account_id, personal_movie_id),
        ).fetchone()

    @staticmethod
    def _review_row(
        connection: sqlite3.Connection,
        review_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                account_id,
                personal_movie_id,
                watch_event_id,
                review_uri,
                review_text,
                rating,
                reviewed_at
            FROM reviews
            WHERE id = ?
            """,
            (review_id,),
        ).fetchone()

    @staticmethod
    def _like_row(
        connection: sqlite3.Connection,
        account_id: int,
        personal_movie_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                account_id,
                personal_movie_id,
                liked_at,
                source_uri
            FROM likes
            WHERE account_id = ?
                AND personal_movie_id = ?
            """,
            (account_id, personal_movie_id),
        ).fetchone()

    @staticmethod
    def _personal_movie_values(
        movie: PersonalMovieRecord,
    ) -> tuple[int, int | None, str, int | None, str | None, str | None]:
        return (
            movie.account_id,
            movie.canonical_movie_id,
            movie.title,
            movie.year,
            movie.letterboxd_url,
            movie.letterboxd_uri,
        )

    @staticmethod
    def _watch_event_values(
        event: WatchEventRecord,
    ) -> tuple[int, int, str | None, str | None, str, int]:
        return (
            event.account_id,
            event.personal_movie_id,
            event.watched_date,
            event.letterboxd_uri,
            event.source,
            int(event.is_rewatch),
        )

    @staticmethod
    def _review_values(
        review: ReviewRecord,
    ) -> tuple[int, int, int | None, str | None, str | None, float | None, str | None]:
        return (
            review.account_id,
            review.personal_movie_id,
            review.watch_event_id,
            review.review_uri,
            review.review_text,
            review.rating,
            review.reviewed_at,
        )

    @staticmethod
    def _account_from_row(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            source=row["source"],
            username=row["username"],
            display_name=row["display_name"],
            profile_url=row["profile_url"],
        )

    @staticmethod
    def _personal_movie_from_row(row: sqlite3.Row) -> PersonalMovie:
        return PersonalMovie(
            id=row["id"],
            account_id=row["account_id"],
            canonical_movie_id=row["canonical_movie_id"],
            title=row["title"],
            year=row["year"],
            letterboxd_url=row["letterboxd_url"],
            letterboxd_uri=row["letterboxd_uri"],
        )

    @staticmethod
    def _watch_event_from_row(row: sqlite3.Row) -> WatchEvent:
        return WatchEvent(
            id=row["id"],
            account_id=row["account_id"],
            personal_movie_id=row["personal_movie_id"],
            watched_date=row["watched_date"],
            letterboxd_uri=row["letterboxd_uri"],
            source=row["source"],
            is_rewatch=bool(row["is_rewatch"]),
        )

    @staticmethod
    def _rating_from_row(row: sqlite3.Row) -> Rating:
        return Rating(
            account_id=row["account_id"],
            personal_movie_id=row["personal_movie_id"],
            rating=row["rating"],
            rated_at=row["rated_at"],
        )

    @staticmethod
    def _review_from_row(row: sqlite3.Row) -> Review:
        return Review(
            id=row["id"],
            account_id=row["account_id"],
            personal_movie_id=row["personal_movie_id"],
            watch_event_id=row["watch_event_id"],
            review_uri=row["review_uri"],
            review_text=row["review_text"],
            rating=row["rating"],
            reviewed_at=row["reviewed_at"],
        )

    @staticmethod
    def _like_from_row(row: sqlite3.Row) -> Like:
        return Like(
            account_id=row["account_id"],
            personal_movie_id=row["personal_movie_id"],
            liked_at=row["liked_at"],
            source_uri=row["source_uri"],
        )
