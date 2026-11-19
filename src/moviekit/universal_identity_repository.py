"""Normalized, TMDb-verified identities shared without expanding ``movies``."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from .database import initialize_database


class UniversalIdentityRepository:
    def __init__(self, database_path=None):
        if database_path is None:
            from .config import load_config

            database_path = load_config().database_path
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def save(self, tmdb_id, title, original_title, release_year, genres, credits):
        """Upsert one verified TMDb identity and replace only its TMDb metadata."""
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """INSERT INTO film_identities
                   (tmdb_id, title, original_title, release_year, metadata_fetched_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(tmdb_id) DO UPDATE SET
                     title=excluded.title, original_title=excluded.original_title,
                     release_year=excluded.release_year, metadata_fetched_at=excluded.metadata_fetched_at,
                     updated_at=datetime('now')""",
                (tmdb_id, title, original_title, release_year),
            )
            identity_id = connection.execute(
                "SELECT id FROM film_identities WHERE tmdb_id = ?", (tmdb_id,)
            ).fetchone()[0]
            connection.execute("DELETE FROM identity_genres WHERE identity_id = ?", (identity_id,))
            for name in sorted({name.strip() for name in genres if isinstance(name, str) and name.strip()}):
                connection.execute("INSERT OR IGNORE INTO genres(name) VALUES (?)", (name,))
                genre_id = connection.execute("SELECT id FROM genres WHERE name = ?", (name,)).fetchone()[0]
                connection.execute(
                    "INSERT OR IGNORE INTO identity_genres(identity_id, genre_id) VALUES (?, ?)",
                    (identity_id, genre_id),
                )
            connection.execute("DELETE FROM identity_credits WHERE identity_id = ?", (identity_id,))
            for credit in credits:
                person_id = credit.get("id")
                name = credit.get("name")
                role = credit.get("role")
                if not isinstance(person_id, int) or not isinstance(name, str) or not name.strip():
                    continue
                if role not in {"director", "actor"}:
                    continue
                connection.execute(
                    """INSERT INTO identity_people(tmdb_person_id, name) VALUES (?, ?)
                       ON CONFLICT(tmdb_person_id) DO UPDATE SET name=excluded.name,
                       updated_at=datetime('now')""",
                    (person_id, name.strip()),
                )
                local_person_id = connection.execute(
                    "SELECT id FROM identity_people WHERE tmdb_person_id = ?", (person_id,)
                ).fetchone()[0]
                connection.execute(
                    """INSERT OR REPLACE INTO identity_credits(identity_id, person_id, role, billing_order)
                       VALUES (?, ?, ?, ?)""",
                    (identity_id, local_person_id, role, credit.get("billing_order")),
                )
            return identity_id

    def link_personal(self, personal_movie_id, identity_id):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "UPDATE personal_movie_metadata SET identity_id = ? WHERE personal_movie_id = ?",
                (identity_id, personal_movie_id),
            )

    def by_tmdb_id(self, tmdb_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT id FROM film_identities WHERE tmdb_id = ?", (tmdb_id,)
            ).fetchone()
        return row[0] if row else None

    @staticmethod
    def metadata_complete(cached):
        return bool(cached and cached.get("identity_id") is not None
                    and cached.get("metadata_status") == "complete"
                    and cached.get("identity_metadata_fetched_at"))

    def status(self, username):
        with closing(sqlite3.connect(self.database_path)) as connection:
            return connection.execute(
                """SELECT coalesce(m.status, 'unresolved'),
                          coalesce(m.metadata_status, 'unprocessed'), count(*) FROM personal_movies p
                   JOIN accounts a ON a.id = p.account_id
                   LEFT JOIN personal_movie_metadata m ON m.personal_movie_id = p.id
                   WHERE a.source = 'letterboxd' AND a.username = ?
                   GROUP BY m.status, m.metadata_status ORDER BY m.status, m.metadata_status""",
                (username,),
            ).fetchall()

    def unresolved(self, username):
        with closing(sqlite3.connect(self.database_path)) as connection:
            return connection.execute(
                """SELECT p.title, p.year, coalesce(m.status, 'unresolved'), m.tmdb_id,
                          m.metadata_status, m.failure_category, m.failure_message
                   FROM personal_movies p
                   JOIN accounts a ON a.id = p.account_id
                   LEFT JOIN personal_movie_metadata m ON m.personal_movie_id = p.id
                   WHERE a.source = 'letterboxd' AND a.username = ?
                     AND (m.status IS NULL OR m.status != 'complete'
                          OR m.metadata_status LIKE 'failed_%')
                   ORDER BY coalesce(m.status, 'unresolved'), m.metadata_status, p.title, p.year""",
                (username,),
            ).fetchall()
