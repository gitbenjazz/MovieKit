"""SQLite persistence for curated collection entries; canonical rows are read-only."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .collection_models import CollectionRecord, CollectionSummary
from .database import initialize_database


class CollectionNotFoundError(ValueError):
    pass


class CollectionRepository:
    CANONICAL_SLUG = "letterboxd-1001"
    EDITION_2013_SLUG = "1001-2013"

    def __init__(self, database_path=None):
        if database_path is None:
            from .config import load_config

            database_path = load_config().database_path
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def ensure_canonical_collection(self):
        return self.upsert_collection(CollectionRecord(
            self.CANONICAL_SLUG, "Letterboxd 1001 canonical collection", None,
            description="Existing canonical collection represented by movies; membership is not copied.",
        ))

    def upsert_collection(self, collection: CollectionRecord) -> int:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                """INSERT INTO collections (slug, name, edition_year, source_url, description)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(slug) DO UPDATE SET name=excluded.name,
                    edition_year=excluded.edition_year, source_url=excluded.source_url,
                    description=excluded.description, updated_at=datetime('now')""",
                (collection.slug, collection.name, collection.edition_year,
                 collection.source_url, collection.description),
            )
            return connection.execute("SELECT id FROM collections WHERE slug = ?", (collection.slug,)).fetchone()[0]

    def replace_entries(self, slug: str, entries) -> tuple[int, int]:
        """Upsert one complete editorial source atomically; preserve no stale rows."""
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            collection = connection.execute("SELECT id FROM collections WHERE slug = ?", (slug,)).fetchone()
            if collection is None:
                raise CollectionNotFoundError(f"Collection not found: {slug}")
            collection_id = collection[0]
            existing = {r[0] for r in connection.execute(
                "SELECT editorial_entry_number FROM collection_entries WHERE collection_id = ?", (collection_id,)
            )}
            numbers = {entry.editorial_entry_number for entry in entries}
            if len(numbers) != len(entries):
                raise ValueError("Collection source has duplicate editorial entry numbers")
            inserted = sum(n not in existing for n in numbers)
            for entry in entries:
                connection.execute(
                    """INSERT INTO collection_entries (
                       collection_id, editorial_entry_number, source_title, source_year, source_url,
                       verification_status, review_reason, editorial_group, tmdb_id, canonical_movie_id,
                       match_state, match_method, candidate_ids_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(collection_id, editorial_entry_number) DO UPDATE SET
                        source_title=excluded.source_title, source_year=excluded.source_year,
                        source_url=excluded.source_url, verification_status=excluded.verification_status,
                        review_reason=excluded.review_reason, editorial_group=excluded.editorial_group,
                        tmdb_id=excluded.tmdb_id, canonical_movie_id=excluded.canonical_movie_id,
                        match_state=excluded.match_state, match_method=excluded.match_method,
                        candidate_ids_json=excluded.candidate_ids_json, updated_at=datetime('now')""",
                    (collection_id, entry.editorial_entry_number, entry.source_title, entry.source_year,
                     entry.source_url, entry.verification_status, entry.review_reason,
                     entry.editorial_group, entry.tmdb_id, entry.canonical_movie_id,
                     entry.match_state, entry.match_method, json.dumps(entry.candidate_ids)),
                )
            stale = existing - numbers
            if stale:
                connection.executemany(
                    "DELETE FROM collection_entries WHERE collection_id = ? AND editorial_entry_number = ?",
                    [(collection_id, number) for number in stale],
                )
            connection.execute(
                """INSERT OR IGNORE INTO film_identities (tmdb_id, title, release_year)
                   SELECT tmdb_id, source_title, source_year FROM collection_entries
                   WHERE collection_id = ? AND tmdb_id IS NOT NULL""",
                (collection_id,),
            )
            connection.execute(
                """UPDATE collection_entries SET identity_id = (
                       SELECT id FROM film_identities WHERE tmdb_id = collection_entries.tmdb_id)
                   WHERE collection_id = ? AND tmdb_id IS NOT NULL""",
                (collection_id,),
            )
            connection.execute(
                """UPDATE collection_entries SET identity_id = (
                       SELECT identity_id FROM movies WHERE movies.id = collection_entries.canonical_movie_id)
                   WHERE collection_id = ? AND identity_id IS NULL
                     AND canonical_movie_id IS NOT NULL""",
                (collection_id,),
            )
        return inserted, len(entries) - inserted

    def summaries(self) -> list[CollectionSummary]:
        self.ensure_canonical_collection()
        with closing(sqlite3.connect(self.database_path)) as connection:
            rows = connection.execute(
                """SELECT c.slug, c.name, c.edition_year, count(e.id),
                   sum(e.match_state = 'matched'),
                   sum(e.match_state = 'matched' AND e.verification_status != 'needs_review'
                       AND e.editorial_group IS NULL),
                   sum(e.match_state = 'unmatched'), sum(e.match_state = 'ambiguous'),
                   sum(e.match_state = 'grouped'), sum(e.match_state = 'empty')
                   FROM collections c LEFT JOIN collection_entries e ON e.collection_id = c.id
                   GROUP BY c.id ORDER BY c.slug"""
            ).fetchall()
            canonical_count = connection.execute("SELECT count(*) FROM movies").fetchone()[0]
        summaries = []
        for row in rows:
            if row[0] == self.CANONICAL_SLUG:
                summaries.append(CollectionSummary(row[0], row[1], row[2], canonical_count,
                    canonical_count, canonical_count, 0, 0, 0, 0))
            else:
                summaries.append(CollectionSummary(row[0], row[1], row[2], row[3],
                    *(int(value or 0) for value in row[4:])))
        return summaries

    def summary(self, slug: str) -> CollectionSummary:
        matches = [item for item in self.summaries() if item.slug == slug]
        if not matches:
            raise CollectionNotFoundError(f"Collection not found: {slug}")
        return matches[0]

    def canonical_ids(self, selector: str) -> set[int]:
        self.ensure_canonical_collection()
        if selector not in {self.CANONICAL_SLUG, self.EDITION_2013_SLUG, "intersection", "all"}:
            raise ValueError("Unknown collection: " + selector)
        with closing(sqlite3.connect(self.database_path)) as connection:
            canonical = {row[0] for row in connection.execute("SELECT id FROM movies")}
            if selector == self.CANONICAL_SLUG:
                return canonical
            row = connection.execute("SELECT id FROM collections WHERE slug = ?", (self.EDITION_2013_SLUG,)).fetchone()
            if row is None:
                raise CollectionNotFoundError("2013 collection is not imported; run moviekit collections import")
            edition = {r[0] for r in connection.execute(
                """SELECT DISTINCT canonical_movie_id FROM collection_entries
                   WHERE collection_id = ? AND canonical_movie_id IS NOT NULL
                     AND match_state = 'matched' AND verification_status != 'needs_review'
                     AND editorial_group IS NULL""", (row[0],)
            )}
        if selector == self.EDITION_2013_SLUG:
            return edition
        if selector == "intersection":
            return canonical & edition
        return canonical | edition
