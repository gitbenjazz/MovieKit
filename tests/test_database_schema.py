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

from moviekit.database import initialize_database


PERSONAL_TABLES = {
    "accounts",
    "personal_movies",
    "watch_events",
    "ratings",
    "reviews",
    "likes",
    "sync_runs",
}


class DatabaseSchemaTests(unittest.TestCase):
    def test_fresh_database_creates_schema_v3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"

            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                tables = self._tables(connection)
                user_version = self._user_version(connection)

        self.assertEqual(user_version, 3)
        self.assertTrue(PERSONAL_TABLES.issubset(tables))

    def test_schema_v3_personal_tables_have_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                self.assertEqual(
                    {
                        "id",
                        "source",
                        "username",
                        "display_name",
                        "profile_url",
                        "created_at",
                        "updated_at",
                    },
                    self._columns(connection, "accounts"),
                )
                personal_movie_columns = self._columns(connection, "personal_movies")
                self.assertTrue(
                    {
                        "id",
                        "account_id",
                        "canonical_movie_id",
                        "title",
                        "year",
                        "letterboxd_url",
                        "letterboxd_uri",
                        "created_at",
                        "updated_at",
                    }.issubset(personal_movie_columns)
                )
                self.assertNotIn("rating", personal_movie_columns)
                self.assertNotIn("liked", personal_movie_columns)
                self.assertTrue(
                    {
                        "id",
                        "account_id",
                        "personal_movie_id",
                        "watched_date",
                        "letterboxd_uri",
                        "source",
                        "is_rewatch",
                        "created_at",
                        "updated_at",
                    }.issubset(self._columns(connection, "watch_events"))
                )

    def test_schema_v3_required_indexes_exist(self) -> None:
        expected_indexes = {
            "idx_personal_movies_account_id",
            "idx_personal_movies_canonical_movie_id",
            "idx_personal_movies_title_year",
            "idx_watch_events_account_date",
            "idx_watch_events_personal_movie_id",
            "idx_ratings_account_rating",
            "idx_ratings_personal_movie_id",
            "idx_reviews_personal_movie_id",
            "idx_reviews_account_reviewed_at",
            "idx_likes_personal_movie_id",
            "idx_sync_runs_account_started",
            "idx_sync_runs_source_type",
        }

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                indexes = self._indexes(connection)

        self.assertTrue(expected_indexes.issubset(indexes))

    def test_migrates_schema_v2_database_to_schema_v3_without_changing_movies(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            self._create_schema_v2_database(database_path)

            before_movies = self._movie_rows(database_path)
            before_watched = self._watched_rows(database_path)
            initialize_database(database_path)
            after_movies = self._movie_rows(database_path)
            after_watched = self._watched_rows(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                user_version = self._user_version(connection)
                tables = self._tables(connection)

        self.assertEqual(user_version, 3)
        self.assertEqual(before_movies, after_movies)
        self.assertEqual(before_watched, after_watched)
        self.assertTrue(PERSONAL_TABLES.issubset(tables))

    def test_initialization_is_idempotent_for_schema_v3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)
            self._insert_personal_library_sample(database_path)

            before_counts = self._table_counts(database_path)
            initialize_database(database_path)
            after_counts = self._table_counts(database_path)

        self.assertEqual(before_counts, after_counts)

    def test_personal_library_foreign_keys_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        connection.execute(
                            """
                            INSERT INTO personal_movies (
                                account_id,
                                title
                            )
                            VALUES (?, ?)
                            """,
                            (999, "Heat"),
                        )

    def test_accounts_are_unique_by_source_and_username(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    self._insert_account(connection)

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        self._insert_account(connection)

                with connection:
                    connection.execute(
                        """
                        INSERT INTO accounts (
                            source,
                            username
                        )
                        VALUES (?, ?)
                        """,
                        ("imdb", "example"),
                    )

    def test_personal_movies_require_external_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    account_id = self._insert_account(connection)

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        connection.execute(
                            """
                            INSERT INTO personal_movies (
                                account_id,
                                title,
                                year
                            )
                            VALUES (?, ?, ?)
                            """,
                            (account_id, "Heat", 1995),
                        )

    def test_personal_movie_canonical_movie_foreign_key_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    account_id = self._insert_account(connection)

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        connection.execute(
                            """
                            INSERT INTO personal_movies (
                                account_id,
                                canonical_movie_id,
                                title,
                                year,
                                letterboxd_url
                            )
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                account_id,
                                999,
                                "Heat",
                                1995,
                                "https://letterboxd.com/film/heat-1995/",
                            ),
                        )

    def test_personal_library_account_ownership_foreign_keys_are_enforced(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    first_account_id = self._insert_account(connection)
                    second_account_id = self._insert_account(
                        connection,
                        username="other",
                    )
                    personal_movie_id = self._insert_personal_movie(
                        connection,
                        first_account_id,
                        "Heat",
                        "https://letterboxd.com/film/heat-1995/",
                    )

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        connection.execute(
                            """
                            INSERT INTO ratings (
                                account_id,
                                personal_movie_id,
                                rating
                            )
                            VALUES (?, ?, ?)
                            """,
                            (second_account_id, personal_movie_id, 4.0),
                        )

    def test_personal_library_unique_constraints_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    account_id = self._insert_account(connection)
                    self._insert_personal_movie(
                        connection,
                        account_id,
                        "Heat",
                        "https://letterboxd.com/film/heat-1995/",
                    )

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        self._insert_personal_movie(
                            connection,
                            account_id,
                            "Heat",
                            "https://letterboxd.com/film/heat-1995/",
                        )

    def test_watch_event_letterboxd_uri_is_unique_per_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    account_id = self._insert_account(connection)
                    personal_movie_id = self._insert_personal_movie(
                        connection,
                        account_id,
                        "Heat",
                        "https://letterboxd.com/film/heat-1995/",
                    )
                    self._insert_watch_event(
                        connection,
                        account_id,
                        personal_movie_id,
                        "https://boxd.it/29FA",
                    )

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        self._insert_watch_event(
                            connection,
                            account_id,
                            personal_movie_id,
                            "https://boxd.it/29FA",
                        )

    def test_reviews_are_unique_by_account_and_review_uri(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    account_id = self._insert_account(connection)
                    personal_movie_id = self._insert_personal_movie(
                        connection,
                        account_id,
                        "Heat",
                        "https://letterboxd.com/film/heat-1995/",
                    )
                    self._insert_review(
                        connection,
                        account_id,
                        personal_movie_id,
                        "https://letterboxd.com/example/film/heat/review/",
                    )

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        self._insert_review(
                            connection,
                            account_id,
                            personal_movie_id,
                            "https://letterboxd.com/example/film/heat/review/",
                        )

    def test_likes_are_unique_by_account_and_personal_movie(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    account_id = self._insert_account(connection)
                    personal_movie_id = self._insert_personal_movie(
                        connection,
                        account_id,
                        "Heat",
                        "https://letterboxd.com/film/heat-1995/",
                    )
                    self._insert_like(connection, account_id, personal_movie_id)

                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        self._insert_like(connection, account_id, personal_movie_id)

    def test_migration_does_not_add_canonical_movie_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            self._create_schema_v2_database(database_path)

            before_count = self._movie_count(database_path)
            initialize_database(database_path)
            after_count = self._movie_count(database_path)

        self.assertEqual(before_count, 2)
        self.assertEqual(after_count, before_count)

    def test_schema_v3_foreign_key_check_passes_after_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            self._create_schema_v2_database(database_path)

            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                foreign_key_errors = connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()

        self.assertEqual([], foreign_key_errors)

    def _create_schema_v2_database(self, database_path: Path) -> None:
        with closing(sqlite3.connect(database_path)) as connection:
            with connection:
                connection.executescript(
                    """
                    PRAGMA foreign_keys = ON;
                    PRAGMA user_version = 2;

                    CREATE TABLE movies (
                        id integer primary key,
                        title text not null,
                        year integer,
                        letterboxd_url text not null unique,
                        tmdb_id integer unique,
                        tmdb_title text,
                        rating real,
                        runtime integer,
                        created_at text not null default (datetime('now')),
                        updated_at text not null default (datetime('now'))
                    );

                    CREATE TABLE watched (
                        id integer primary key,
                        movie_id integer not null,
                        watched_date text,
                        letterboxd_uri text,
                        created_at text not null default (datetime('now')),
                        updated_at text not null default (datetime('now')),
                        foreign key (movie_id) references movies(id) on delete cascade
                    );

                    CREATE TABLE providers (
                        id integer primary key,
                        name text not null unique
                    );

                    CREATE TABLE countries (
                        code text primary key,
                        name text
                    );

                    CREATE TABLE availability (
                        id integer primary key,
                        movie_id integer not null,
                        provider_id integer not null,
                        country_code text not null,
                        access_type text not null,
                        fetched_at text not null,
                        unique (movie_id, provider_id, country_code, access_type),
                        foreign key (movie_id) references movies(id) on delete cascade,
                        foreign key (provider_id) references providers(id) on delete cascade,
                        foreign key (country_code) references countries(code)
                    );

                    CREATE TABLE source_lists (
                        id integer primary key,
                        name text not null unique
                    );

                    CREATE TABLE list_items (
                        id integer primary key,
                        movie_id integer not null,
                        source_list_id integer not null,
                        position integer not null,
                        created_at text not null default (datetime('now')),
                        unique (source_list_id, movie_id),
                        unique (source_list_id, position),
                        foreign key (movie_id) references movies(id) on delete cascade,
                        foreign key (source_list_id) references source_lists(id) on delete cascade
                    );
                    """
                )
                connection.execute(
                    """
                    INSERT INTO movies (
                        title,
                        year,
                        letterboxd_url,
                        tmdb_id,
                        tmdb_title,
                        runtime
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "alien",
                        1979,
                        "https://letterboxd.com/film/alien/",
                        348,
                        "Alien",
                        117,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO movies (
                        title,
                        year,
                        letterboxd_url
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        "heat",
                        1995,
                        "https://letterboxd.com/film/heat-1995/",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO watched (
                        movie_id,
                        watched_date,
                        letterboxd_uri
                    )
                    VALUES (?, ?, ?)
                    """,
                    (1, "2026-07-23", "https://boxd.it/2awY"),
                )

    def _insert_personal_library_sample(self, database_path: Path) -> None:
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                account_id = self._insert_account(connection)
                personal_movie_id = self._insert_personal_movie(
                    connection,
                    account_id,
                    "Heat",
                    "https://letterboxd.com/film/heat-1995/",
                )
                connection.execute(
                    """
                    INSERT INTO watch_events (
                        account_id,
                        personal_movie_id,
                        watched_date,
                        letterboxd_uri
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        personal_movie_id,
                        "2026-07-23",
                        "https://boxd.it/29FA",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO ratings (
                        account_id,
                        personal_movie_id,
                        rating
                    )
                    VALUES (?, ?, ?)
                    """,
                    (account_id, personal_movie_id, 4.5),
                )
                connection.execute(
                    """
                    INSERT INTO reviews (
                        account_id,
                        personal_movie_id,
                        review_uri,
                        review_text
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        personal_movie_id,
                        "https://letterboxd.com/example/film/heat/review/",
                        "Great.",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO likes (
                        account_id,
                        personal_movie_id
                    )
                    VALUES (?, ?)
                    """,
                    (account_id, personal_movie_id),
                )
                connection.execute(
                    """
                    INSERT INTO sync_runs (
                        account_id,
                        source,
                        sync_type,
                        status
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (account_id, "letterboxd", "personal_library", "success"),
                )

    def _insert_account(
        self,
        connection: sqlite3.Connection,
        username: str = "example",
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO accounts (
                source,
                username
            )
            VALUES (?, ?)
            """,
            ("letterboxd", username),
        )
        return int(cursor.lastrowid)

    def _insert_personal_movie(
        self,
        connection: sqlite3.Connection,
        account_id: int,
        title: str,
        letterboxd_url: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO personal_movies (
                account_id,
                title,
                year,
                letterboxd_url
            )
            VALUES (?, ?, ?, ?)
            """,
            (account_id, title, 1995, letterboxd_url),
        )
        return int(cursor.lastrowid)

    def _insert_watch_event(
        self,
        connection: sqlite3.Connection,
        account_id: int,
        personal_movie_id: int,
        letterboxd_uri: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO watch_events (
                account_id,
                personal_movie_id,
                watched_date,
                letterboxd_uri
            )
            VALUES (?, ?, ?, ?)
            """,
            (account_id, personal_movie_id, "2026-07-23", letterboxd_uri),
        )
        return int(cursor.lastrowid)

    def _insert_review(
        self,
        connection: sqlite3.Connection,
        account_id: int,
        personal_movie_id: int,
        review_uri: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO reviews (
                account_id,
                personal_movie_id,
                review_uri,
                review_text
            )
            VALUES (?, ?, ?, ?)
            """,
            (account_id, personal_movie_id, review_uri, "Great."),
        )
        return int(cursor.lastrowid)

    def _insert_like(
        self,
        connection: sqlite3.Connection,
        account_id: int,
        personal_movie_id: int,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO likes (
                account_id,
                personal_movie_id
            )
            VALUES (?, ?)
            """,
            (account_id, personal_movie_id),
        )
        return int(cursor.lastrowid)

    def _tables(self, connection: sqlite3.Connection) -> set[str]:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    def _columns(self, connection: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}

    def _indexes(self, connection: sqlite3.Connection) -> set[str]:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    def _user_version(self, connection: sqlite3.Connection) -> int:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def _movie_rows(self, database_path: Path) -> list[tuple]:
        with closing(sqlite3.connect(database_path)) as connection:
            return connection.execute(
                """
                SELECT
                    id,
                    title,
                    year,
                    letterboxd_url,
                    tmdb_id,
                    tmdb_title,
                    runtime
                FROM movies
                ORDER BY id
                """
            ).fetchall()

    def _watched_rows(self, database_path: Path) -> list[tuple]:
        with closing(sqlite3.connect(database_path)) as connection:
            return connection.execute(
                """
                SELECT
                    id,
                    movie_id,
                    watched_date,
                    letterboxd_uri
                FROM watched
                ORDER BY id
                """
            ).fetchall()

    def _movie_count(self, database_path: Path) -> int:
        with closing(sqlite3.connect(database_path)) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0])

    def _table_counts(self, database_path: Path) -> dict[str, int]:
        tables = [
            "movies",
            "watched",
            "accounts",
            "personal_movies",
            "watch_events",
            "ratings",
            "reviews",
            "likes",
            "sync_runs",
        ]

        with closing(sqlite3.connect(database_path)) as connection:
            return {
                table: int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in tables
            }


if __name__ == "__main__":
    unittest.main()
