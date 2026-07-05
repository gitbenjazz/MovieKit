from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MovieRecord:
    title: str
    year: int | None
    letterboxd_url: str | None
    tmdb_id: int | None = None
    tmdb_title: str | None = None
    rating: float | None = None
    runtime: int | None = None
    director: str | None = None
    genres: str | None = None


@dataclass(frozen=True)
class WatchedRecord:
    title: str
    year: int | None
    watched_date: str | None
    letterboxd_uri: str | None