"""Collection records separate editorial membership from canonical movies."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionRecord:
    slug: str
    name: str
    edition_year: int | None = None
    source_url: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class CollectionEntryRecord:
    editorial_entry_number: int
    source_title: str
    source_year: int | None
    source_url: str
    verification_status: str
    review_reason: str | None
    editorial_group: str | None
    tmdb_id: int | None
    canonical_movie_id: int | None
    match_state: str
    match_method: str | None
    candidate_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class CollectionImportResult:
    slug: str
    editorial_entries: int
    inserted: int
    updated: int
    matched: int
    recommendable: int
    unresolved: int
    ambiguous: int
    grouped: int
    empty_title: int


@dataclass(frozen=True)
class CollectionSummary:
    slug: str
    name: str
    edition_year: int | None
    editorial_entries: int
    matched: int
    recommendable: int
    unresolved: int
    ambiguous: int
    grouped: int
    empty_title: int
