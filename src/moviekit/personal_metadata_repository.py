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
                "SELECT * FROM personal_movie_metadata WHERE personal_movie_id = ? "
                "AND source_title = ? AND source_year IS ?",
                (movie.id, movie.title, movie.year),
            ).fetchone()
        return dict(row) if row else None

    def save(self, movie, status, tmdb_id=None, genres=(), directors=()):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """INSERT INTO personal_movie_metadata
                   (personal_movie_id, source_title, source_year, status, tmdb_id,
                    genres_json, directors_json) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(personal_movie_id) DO UPDATE SET
                    source_title=excluded.source_title, source_year=excluded.source_year,
                    status=excluded.status, tmdb_id=excluded.tmdb_id,
                    genres_json=excluded.genres_json, directors_json=excluded.directors_json,
                    fetched_at=datetime('now')""",
                (movie.id, movie.title, movie.year, status, tmdb_id,
                 json.dumps(sorted(set(genres))), json.dumps(sorted(set(directors)))),
            )
