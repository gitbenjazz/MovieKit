"""Account-owned Personal Library records; no persistence dependencies."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountRecord:
    source: str
    username: str
    display_name: str | None = None
    profile_url: str | None = None


@dataclass(frozen=True)
class Account:
    id: int
    source: str
    username: str
    display_name: str | None
    profile_url: str | None


@dataclass(frozen=True)
class PersonalMovieRecord:
    account_id: int
    title: str
    year: int | None = None
    letterboxd_url: str | None = None
    letterboxd_uri: str | None = None
    canonical_movie_id: int | None = None


@dataclass(frozen=True)
class PersonalMovie:
    id: int
    account_id: int
    canonical_movie_id: int | None
    title: str
    year: int | None
    letterboxd_url: str | None
    letterboxd_uri: str | None


@dataclass(frozen=True)
class WatchEventRecord:
    account_id: int
    personal_movie_id: int
    watched_date: str | None = None
    letterboxd_uri: str | None = None
    source: str = "letterboxd"
    is_rewatch: bool = False


@dataclass(frozen=True)
class WatchEvent:
    id: int
    account_id: int
    personal_movie_id: int
    watched_date: str | None
    letterboxd_uri: str | None
    source: str
    is_rewatch: bool


@dataclass(frozen=True)
class RatingRecord:
    account_id: int
    personal_movie_id: int
    rating: float
    rated_at: str | None = None


@dataclass(frozen=True)
class Rating:
    account_id: int
    personal_movie_id: int
    rating: float
    rated_at: str | None


@dataclass(frozen=True)
class ReviewRecord:
    account_id: int
    personal_movie_id: int
    watch_event_id: int | None = None
    review_uri: str | None = None
    review_text: str | None = None
    rating: float | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True)
class Review:
    id: int
    account_id: int
    personal_movie_id: int
    watch_event_id: int | None
    review_uri: str | None
    review_text: str | None
    rating: float | None
    reviewed_at: str | None


@dataclass(frozen=True)
class LikeRecord:
    account_id: int
    personal_movie_id: int
    liked_at: str | None = None
    source_uri: str | None = None


@dataclass(frozen=True)
class Like:
    account_id: int
    personal_movie_id: int
    liked_at: str | None
    source_uri: str | None


@dataclass(frozen=True)
class PersonalLibraryData:
    account: Account
    movies: list[PersonalMovie]
    watch_events: list[WatchEvent]
    ratings: list[Rating]
    reviews: list[Review]
    likes: list[Like]


@dataclass(frozen=True)
class MovieIdentity:
    """External film identity, before account/database IDs have been assigned."""

    title: str
    year: int | None
    letterboxd_uri: str
    letterboxd_url: str | None = None


@dataclass(frozen=True)
class ImportedWatch:
    movie: MovieIdentity
    source_uri: str
    watched_date: str | None = None
    is_rewatch: bool = False
    source: str = "letterboxd_watched"


@dataclass(frozen=True)
class ImportedRating:
    movie: MovieIdentity
    rating: float
    rated_at: str | None = None


@dataclass(frozen=True)
class ImportedReview:
    movie: MovieIdentity
    source_uri: str
    text: str
    rating: float | None = None
    reviewed_at: str | None = None
    watched_date: str | None = None


@dataclass(frozen=True)
class ImportedLike:
    movie: MovieIdentity
    liked_at: str | None = None


@dataclass(frozen=True)
class ImportIssue:
    filename: str
    row: int
    message: str


@dataclass(frozen=True)
class LetterboxdImport:
    """Validated rows from a possibly partial export; absence is not deletion."""

    watches: tuple[ImportedWatch, ...] = ()
    ratings: tuple[ImportedRating, ...] = ()
    reviews: tuple[ImportedReview, ...] = ()
    likes: tuple[ImportedLike, ...] = ()
    issues: tuple[ImportIssue, ...] = ()
    files: tuple[str, ...] = ()
    rows_seen: int = 0
