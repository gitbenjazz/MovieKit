"""Read-only collection progress queries for account analytics."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from .personal_analytics_models import CollectionProgress


class CollectionAnalyticsRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def progress(self, watched_canonical_ids: set[int]) -> tuple[CollectionProgress, ...]:
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            canonical_total = connection.execute("SELECT count(*) FROM movies").fetchone()[0]
            collections = connection.execute(
                "SELECT id, slug, name FROM collections WHERE slug = '1001-2013'"
            ).fetchall()
            result = [self._canonical_progress(canonical_total, watched_canonical_ids)]
            for collection_id, slug, name in collections:
                rows = connection.execute(
                    """SELECT canonical_movie_id, match_state, editorial_group
                       FROM collection_entries WHERE collection_id = ?""",
                    (collection_id,),
                ).fetchall()
                result.append(self._edition_progress(slug, name, rows, watched_canonical_ids))
        return tuple(result)

    @staticmethod
    def _canonical_progress(total, watched):
        progress = len(watched) / total * 100 if total else None
        return CollectionProgress(
            "letterboxd-1001", "Letterboxd 1001 canonical collection", total, total,
            len(watched), total - len(watched), 0, 0, 0, 100.0 if total else None, progress,
        )

    @staticmethod
    def _edition_progress(slug, name, rows, watched):
        resolved = {row[0] for row in rows if row[0] is not None and row[1] == "matched"}
        unresolved = sum(row[1] in {"unmatched", "ambiguous", "grouped", "empty"} for row in rows)
        ambiguous = sum(row[1] == "ambiguous" for row in rows)
        grouped = sum(row[2] is not None for row in rows)
        coverage = len(resolved) / len(rows) * 100 if rows else None
        progress = len(resolved & watched) / len(resolved) * 100 if resolved else None
        watched_resolved = len(resolved & watched)
        return CollectionProgress(slug, name, len(rows), len(resolved), watched_resolved,
            len(resolved) - watched_resolved, unresolved, ambiguous, grouped, coverage, progress)
