"""Strict CSV import for edition-specific editorial collections."""
from __future__ import annotations

import csv
from pathlib import Path

from .canonical_linker import CanonicalMovieLinker, LinkState
from .collection_models import CollectionEntryRecord, CollectionImportResult, CollectionRecord
from .collection_repository import CollectionRepository
from .database_repository import DatabaseRepository
from .personal_library_models import MovieIdentity


class CollectionImportService:
    REQUIRED_COLUMNS = {"edition_entry_number", "title", "year", "source_url", "verification_status"}

    def __init__(self, repository=None, canonical_repository=None):
        self.repository = repository or CollectionRepository()
        self.canonical_repository = canonical_repository or DatabaseRepository(self.repository.database_path)

    def import_2013(self, source):
        source = Path(source)
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not self.REQUIRED_COLUMNS.issubset(reader.fieldnames):
                raise ValueError("Collection CSV is missing required columns")
            rows = list(reader)
        linker = CanonicalMovieLinker(self.canonical_repository.get_all_movies())
        entries = [self._entry(row, linker) for row in rows]
        if len({entry.editorial_entry_number for entry in entries}) != len(entries):
            raise ValueError("Collection source has duplicate editorial entry numbers")
        self.repository.upsert_collection(CollectionRecord(
            "1001-2013", "1001 Movies You Must See Before You Die — international 10th edition",
            2013, "https://1001movies.fandom.com/wiki/10th_Edition",
            "Approximation of the 2013 international selection; source transcription is retained verbatim.",
        ))
        inserted, updated = self.repository.replace_entries("1001-2013", entries)
        states = {state: sum(entry.match_state == state for entry in entries)
                  for state in {entry.match_state for entry in entries}}
        recommendable = sum(entry.match_state == "matched" and entry.verification_status != "needs_review"
                            and entry.editorial_group is None for entry in entries)
        return CollectionImportResult("1001-2013", len(entries), inserted, updated,
            states.get("matched", 0), recommendable, states.get("unmatched", 0),
            states.get("ambiguous", 0), states.get("grouped", 0), states.get("empty", 0))

    @staticmethod
    def _entry(row, linker):
        try:
            number = int(row["edition_entry_number"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Collection CSV has an invalid editorial entry number") from exc
        title = (row.get("title") or "").strip()
        try:
            year = int(row["year"]) if (row.get("year") or "").strip() else None
        except ValueError as exc:
            raise ValueError(f"Collection entry {number} has an invalid year") from exc
        status = (row.get("verification_status") or "").strip()
        source_url = (row.get("source_url") or "").strip()
        if not status or not source_url:
            raise ValueError(f"Collection entry {number} is missing provenance or verification status")
        review = (row.get("review_reason") or "").strip() or None
        group = CollectionImportService._group(title, review)
        tmdb_id = CollectionImportService._tmdb_id(row.get("tmdb_id"), number)
        if not title:
            state, link = "empty", None
        elif group:
            state, link = "grouped", None
        else:
            link = linker.match(MovieIdentity(title, year, f"collection:{number}"), tmdb_id)
            state = link.state.value
        return CollectionEntryRecord(number, title, year, source_url, status, review, group, tmdb_id,
            link.canonical_movie_id if link and link.state == LinkState.MATCHED else None,
            state, link.method if link else None, link.candidates if link else ())

    @staticmethod
    def _group(title, review_reason):
        marker = f"{title} {review_reason or ''}".casefold()
        if "trilogy" in marker or "grouped" in marker or "multi-part" in marker:
            return title or review_reason
        return None

    @staticmethod
    def _tmdb_id(value, number):
        if not (value or "").strip():
            return None
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"Collection entry {number} has an invalid TMDb ID") from exc
        if parsed < 1:
            raise ValueError(f"Collection entry {number} has an invalid TMDb ID")
        return parsed
