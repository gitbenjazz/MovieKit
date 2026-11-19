"""Persistence for transitional, personal-film TMDb metadata (never canonical writes)."""
from __future__ import annotations

from contextlib import closing
import json
import sqlite3

from .personal_library_repository import PersonalLibraryRepository


class PersonalMetadataRepository:
    def __init__(self, database_path=None):
        self.library = PersonalLibraryRepository(database_path)
        self.database_path = self.library.database_path

    def cached(self, movie):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT m.*, i.metadata_fetched_at AS identity_metadata_fetched_at
                   FROM personal_movie_metadata m LEFT JOIN film_identities i ON i.id = m.identity_id
                   WHERE m.personal_movie_id = ? """
                "AND source_title = ? AND source_year IS ?",
                (movie.id, movie.title, movie.year),
            ).fetchone()
        return dict(row) if row else None

    def save(self, movie, status, tmdb_id=None, genres=(), directors=(), identity_id=None,
             metadata_status=None, refresh_order=None):
        if metadata_status is None:
            metadata_status = 'complete' if status == 'complete' and identity_id is not None else (
                'pending' if status == 'pending' else 'unavailable'
            )
        if refresh_order is None:
            refresh_order = 0
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """INSERT INTO personal_movie_metadata
                   (personal_movie_id, source_title, source_year, status, tmdb_id,
                    genres_json, directors_json, identity_id, metadata_status, refresh_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(personal_movie_id) DO UPDATE SET
                    source_title=excluded.source_title, source_year=excluded.source_year,
                    status=excluded.status, tmdb_id=excluded.tmdb_id,
                    genres_json=excluded.genres_json, directors_json=excluded.directors_json,
                    identity_id=coalesce(excluded.identity_id, personal_movie_metadata.identity_id),
                    metadata_status=excluded.metadata_status,
                    refresh_order=CASE WHEN excluded.refresh_order > 0 THEN excluded.refresh_order
                                       ELSE personal_movie_metadata.refresh_order END,
                    failure_category=NULL, failure_message=NULL, failure_count=0, last_failed_at=NULL,
                    fetched_at=datetime('now')""",
                (movie.id, movie.title, movie.year, status, tmdb_id,
                 json.dumps(sorted(set(genres))), json.dumps(sorted(set(directors))), identity_id,
                 metadata_status, refresh_order),
            )

    def next_refresh_order(self):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            return connection.execute(
                "SELECT coalesce(max(refresh_order), 0) + 1 FROM personal_movie_metadata"
            ).fetchone()[0]

    def record_failure(self, movie, category, message):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                """UPDATE personal_movie_metadata
                   SET metadata_status=?, failure_category=?, failure_message=?,
                       failure_count=failure_count + 1, last_failed_at=datetime('now')
                   WHERE personal_movie_id=? AND source_title=? AND source_year IS ?""",
                ("failed_permanent" if category == "metadata" else "failed_retryable",
                 category, message[:500], movie.id, movie.title, movie.year),
            )
