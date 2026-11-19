"""Read models for local, account-scoped Personal Library analytics."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyticsMovie:
    id: int
    year: int | None
    canonical_id: int | None
    rating: float | None
    liked: bool


@dataclass(frozen=True)
class AnalyticsWatch:
    movie_id: int
    watched_date: str | None
    is_rewatch: bool
    source: str


@dataclass(frozen=True)
class AnalyticsSnapshot:
    username: str
    movies: tuple[AnalyticsMovie, ...]
    watches: tuple[AnalyticsWatch, ...]
    genres: tuple[tuple[int, str], ...]
    directors: tuple[tuple[int, str], ...]
    canonical_total: int
    actors: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class PreferenceStats:
    name: str
    movies: int
    watched: int
    rated: int
    liked: int
    average_rating: float | None


@dataclass(frozen=True)
class PersonalStats:
    username: str
    movies: int
    watched: int
    rated: int
    liked: int
    average_rating: float | None
    rating_distribution: tuple[tuple[float, int], ...]
    invalid_ratings: int
    watch_events: int
    activity_by_year: tuple[tuple[int, int], ...]
    undated_events: int
    decades: tuple[tuple[int, int], ...]
    unknown_release_year: int
    rewatch_events: int
    rewatched_movies: int
    multiple_logged_watches: int
    genres: tuple[PreferenceStats, ...]
    directors: tuple[PreferenceStats, ...]
    genre_coverage: int
    director_coverage: int
    canonical_watched: int
    canonical_total: int
    actors: tuple[PreferenceStats, ...] = ()
    actor_coverage: int = 0


@dataclass(frozen=True)
class TasteGroup:
    name: str
    rated: int
    liked: int
    average_rating: float | None
    evidence: str


@dataclass(frozen=True)
class TasteProfile:
    ratings_available: bool
    rating_scale: str
    rated_movies: int
    average_rating: float | None
    distribution: tuple[tuple[float, int], ...]
    genres: tuple[TasteGroup, ...]
    directors: tuple[TasteGroup, ...]
    decades: tuple[TasteGroup, ...]
    actors: tuple[TasteGroup, ...] = ()


@dataclass(frozen=True)
class CollectionProgress:
    slug: str
    name: str
    editorial_entries: int
    resolved_films: int
    watched_resolved_films: int
    unwatched_resolved_films: int
    unresolved_entries: int
    ambiguous_entries: int
    grouped_entries: int
    coverage_percent: float | None
    progress_percent: float | None


@dataclass(frozen=True)
class PersonalAnalyticsReport:
    username: str
    stats: PersonalStats
    taste: TasteProfile
    collections: tuple[CollectionProgress, ...]
    watched_decades: tuple[tuple[int, int], ...]
    linked_personal_movies: int
    unmatched_personal_movies: int
