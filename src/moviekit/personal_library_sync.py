"""Additive Letterboxd import orchestration, isolated from Phase 1 watched state."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .canonical_linker import CanonicalMovieLinker, LinkState, normalized_title, normalized_uri
from .database_repository import DatabaseRepository
from .letterboxd_export_parser import LetterboxdExportParser
from .personal_library_models import (
    AccountRecord, ImportIssue, LikeRecord, MovieIdentity, PersonalMovieRecord,
    RatingRecord, ReviewRecord, WatchEventRecord,
)
from .personal_library_repository import PersonalLibraryRepository


@dataclass(frozen=True)
class PersonalSyncResult:
    account_id: int
    sync_run_id: int
    movies: int
    watch_events: int
    ratings: int
    reviews: int
    likes: int
    canonical_matches: int
    unmatched: int
    ambiguous: int
    inserted: int
    updated: int
    issues: tuple[ImportIssue, ...]


class PersonalLibrarySyncService:
    def __init__(self, repository=None, parser=None, canonical_repository=None):
        self.repository = repository or PersonalLibraryRepository()
        self.parser = parser or LetterboxdExportParser()
        self.canonical_repository = canonical_repository or DatabaseRepository(self.repository.database_path)

    def sync(self, source: str | Path, username: str) -> PersonalSyncResult:
        username = username.strip().lower()
        if not username or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in username):
            raise ValueError("A valid Letterboxd username is required")
        data = self.parser.parse(source)
        linker = CanonicalMovieLinker(self.canonical_repository.get_all_movies())
        old_account = self.repository.find_account("letterboxd", username)
        try:
            with self.repository.transaction():
                account = self.repository.upsert_account(AccountRecord(
                    "letterboxd", username, profile_url=f"https://letterboxd.com/{username}/"
                ))
                before = self.repository.get_personal_library(account.id)
                known_movies = {m.id: m for m in before.movies}
                imported_ids = set()
                aliases = {}

                def resolve(identity: MovieIdentity, activity=False):
                    key = identity.letterboxd_uri
                    if key in aliases:
                        return aliases[key]
                    existing = self.repository.find_personal_movie(
                        account.id, letterboxd_url=identity.letterboxd_url,
                        letterboxd_uri=identity.letterboxd_uri,
                    )
                    if existing is None:
                        # Reconcile short film URLs with long entry URLs only when unique.
                        candidates = [m for m in known_movies.values()
                            if identity.year is not None and m.year == identity.year
                            and normalized_title(m.title) == normalized_title(identity.title)
                            and (activity or bool(m.letterboxd_url) != bool(identity.letterboxd_url))
                            and not (m.letterboxd_url and identity.letterboxd_url
                                     and m.letterboxd_url != identity.letterboxd_url)]
                        if len(candidates) == 1:
                            existing = candidates[0]
                    effective_url = identity.letterboxd_url or (existing.letterboxd_url if existing else None)
                    link = linker.match(MovieIdentity(identity.title, identity.year,
                                                      identity.letterboxd_uri, effective_url))
                    result = self.repository.upsert_personal_movie(PersonalMovieRecord(
                        account.id, identity.title, identity.year,
                        identity.letterboxd_url or (existing.letterboxd_url if existing else None),
                        existing.letterboxd_uri if existing else identity.letterboxd_uri,
                        link.canonical_movie_id,
                    ))
                    known_movies[result.id] = result
                    aliases[key] = result
                    imported_ids.add(result.id)
                    return result

                # Establish film identities before resolving activity-specific URLs.
                for record in (*[w for w in data.watches if w.source == "letterboxd_watched"],
                               *data.ratings, *data.likes):
                    resolve(record.movie)

                occurrences = {}
                diary_sources = {}
                for watch in data.watches:
                    if watch.source != "letterboxd_diary":
                        continue
                    movie = resolve(watch.movie, activity=True)
                    uri = normalized_uri(watch.source_uri)
                    # A user-entry URL is stable across edits; a film URL is not an event ID.
                    is_entry = uri and "/film/" in uri and not uri.startswith("https://letterboxd.com/film/")
                    if is_entry:
                        event_uri = uri
                    else:
                        key = (movie.id, watch.watched_date)
                        occurrences[key] = occurrences.get(key, 0) + 1
                        event_uri = self._event_key("diary", movie.id, watch.watched_date, occurrences[key])
                    old_events = self.repository.get_watch_events(account.id, movie.id)
                    if not any(e.letterboxd_uri == event_uri for e in old_events):
                        review_events = [e for e in old_events if e.source == "letterboxd_review"
                                         and e.watched_date == watch.watched_date
                                         and (not is_entry or e.letterboxd_uri == event_uri)]
                        if len(review_events) == 1:
                            self.repository.rekey_watch_event(review_events[0].id, event_uri)
                    event = self.repository.save_watch_events([WatchEventRecord(
                        account.id, movie.id, watch.watched_date, event_uri,
                        "letterboxd_diary", watch.is_rewatch,
                    )])[0]
                    diary_sources[(watch.source_uri, watch.watched_date)] = event
                    self.repository.remove_watch_marker(account.id, movie.id)

                for review in data.reviews:
                    movie = resolve(review.movie, activity=True)
                    event = diary_sources.get((review.source_uri, review.watched_date))
                    if event is None and review.watched_date:
                        candidates = [e for e in self.repository.get_watch_events(account.id, movie.id)
                                      if e.watched_date == review.watched_date
                                      and (e.letterboxd_uri == review.source_uri
                                           or (e.letterboxd_uri or "").startswith("urn:moviekit:letterboxd:diary:"))]
                        if len(candidates) == 1:
                            event = candidates[0]
                        elif not candidates:
                            event = self.repository.save_watch_events([WatchEventRecord(
                                account.id, movie.id, review.watched_date, review.source_uri,
                                "letterboxd_review",
                            )])[0]
                        self.repository.remove_watch_marker(account.id, movie.id)
                    self.repository.save_reviews([ReviewRecord(
                        account.id, movie.id, event.id if event else None, review.source_uri,
                        review.text, review.rating, review.reviewed_at,
                    )])

                for watch in data.watches:
                    if watch.source != "letterboxd_watched":
                        continue
                    movie = resolve(watch.movie)
                    if not self.repository.get_watch_events(account.id, movie.id):
                        self.repository.save_watch_events([WatchEventRecord(
                            account.id, movie.id, letterboxd_uri=self._event_key("watched", movie.id),
                            source="letterboxd_watched",
                        )])
                for rating in data.ratings:
                    movie = resolve(rating.movie)
                    self.repository.save_ratings([RatingRecord(account.id, movie.id, rating.rating, rating.rated_at)])
                for like in data.likes:
                    movie = resolve(like.movie)
                    self.repository.save_likes([LikeRecord(account.id, movie.id, like.liked_at, like.movie.letterboxd_uri)])

                after = self.repository.get_personal_library(account.id)
                inserted, updated = self._changes(before, after)
                matches = unmatched = ambiguous = 0
                for movie in after.movies:
                    if movie.id not in imported_ids:
                        continue
                    link = linker.match(MovieIdentity(movie.title, movie.year,
                        movie.letterboxd_uri or movie.letterboxd_url, movie.letterboxd_url))
                    matches += link.state == LinkState.MATCHED
                    unmatched += link.state == LinkState.UNMATCHED
                    ambiguous += link.state == LinkState.AMBIGUOUS
                run_id = self.repository.record_sync_run(
                    account.id, status="completed_with_errors" if data.issues else "completed",
                    seen=data.rows_seen, inserted=inserted, updated=updated, skipped=len(data.issues),
                )
                return PersonalSyncResult(account.id, run_id, len(imported_ids),
                    len(after.watch_events), len(after.ratings), len(after.reviews), len(after.likes),
                    matches, unmatched, ambiguous, inserted, updated, data.issues)
        except Exception as exc:
            # Persist a useful failure marker after rolling back all imported data.
            self.repository.record_sync_run(
                old_account.id if old_account else None, status="failed", seen=data.rows_seen,
                error=type(exc).__name__,
            )
            raise

    @staticmethod
    def _event_key(kind, movie_id, watched_date=None, occurrence=1):
        value = f"{movie_id}|{watched_date}|{occurrence}"
        return f"urn:moviekit:letterboxd:{kind}:{hashlib.sha256(value.encode()).hexdigest()}"

    @staticmethod
    def _changes(before, after):
        inserted = updated = 0
        for name in ("movies", "watch_events", "ratings", "reviews", "likes"):
            key = lambda item: getattr(item, "id", item.personal_movie_id if hasattr(item, "personal_movie_id") else None)
            old = {key(item): item for item in getattr(before, name)}
            for item in getattr(after, name):
                if key(item) not in old:
                    inserted += 1
                elif old[key(item)] != item:
                    updated += 1
        return inserted, updated
