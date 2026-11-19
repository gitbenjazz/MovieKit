from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")

    return parsed


def _not_implemented(_args: argparse.Namespace) -> int:
    print("Not implemented")
    return 0


def sync(_args: Optional[argparse.Namespace] = None) -> int:
    """Refresh CSV outputs, populate SQLite, and print a summary."""
    from .application import SyncLibrary

    summary = SyncLibrary().execute()

    print("MovieKit Sync")
    print("-------------------")
    print(f"Watched 1001: {summary.watched_movies}")
    print(f"Remaining 1001: {summary.remaining_movies}")
    print(f"Progress: {summary.progress:.1%}")
    print(f"SQLite movies synced: {summary.movies_synced}")
    print(f"SQLite watched history imported: {summary.watched_history_imported}")
    print(f"SQLite watched history skipped: {summary.watched_history_skipped}")
    if summary.watched_history_skipped_reasons:
        print("SQLite watched skipped reasons:")
        for reason, count in summary.watched_history_skipped_reasons.items():
            print(f"  - {reason}: {count}")

    return 0


def sync_metadata(_args: Optional[argparse.Namespace] = None) -> int:
    """Synchronize TMDb metadata for all local movies."""
    from .application import SyncMetadata

    print("Canonical metadata synchronization started (saved films are skipped).", flush=True)

    def progress(movie, status, processed):
        print(f"[{processed}] {movie.title} ({movie.year}): {status}", flush=True)

    try:
        result = SyncMetadata().execute(limit=getattr(_args, "limit", None), progress=progress)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Metadata synchronization failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; completed films are saved. Rerun to resume.", flush=True)
        return 130

    _print_bulk_sync_summary("Metadata synchronization completed", result)

    return 1 if result.failed else 0


def sync_availability(_args: Optional[argparse.Namespace] = None) -> int:
    """Synchronize streaming availability for all local movies."""
    from .application import SyncAvailability

    result = SyncAvailability().execute()

    _print_bulk_sync_summary("Availability synchronization completed", result)

    return 0


def sync_all(_args: Optional[argparse.Namespace] = None) -> int:
    """Synchronize all supported bulk data for local movies."""
    from .application import SyncAll

    result = SyncAll().execute()

    print("Bulk synchronization completed")
    print()
    _print_bulk_sync_section("Metadata", result.metadata)
    print()
    _print_bulk_sync_section("Availability", result.availability)

    return 0


def _print_bulk_sync_summary(title: str, result) -> None:
    print(title)
    print()
    _print_bulk_sync_counts(result)


def _print_bulk_sync_section(title: str, result) -> None:
    print(title)
    print("-" * len(title))
    _print_bulk_sync_counts(result)


def _print_bulk_sync_counts(result) -> None:
    print(f"Processed: {result.processed}")
    print(f"Updated: {result.updated}")
    print(f"Skipped: {result.skipped}")
    print(f"Failed: {result.failed}")


def recommend(_args: Optional[argparse.Namespace] = None) -> int:
    """Print the top 10 recommended unwatched movies."""
    from .application import RecommendTopMovies
    from .collection_repository import CollectionNotFoundError
    from .recommendation_service import InvalidYearRange, RecommendationAccountError
    from .tmdb_client import TMDbAPIError

    try:
        prime_movies = RecommendTopMovies().execute(
            limit=10,
            verbose=True,
            from_year=getattr(_args, "from_year", None),
            to_year=getattr(_args, "to_year", None),
            username=getattr(_args, "username", None),
            collection=getattr(_args, "collection", None),
        )
    except (InvalidYearRange, RecommendationAccountError, CollectionNotFoundError, ValueError) as exc:
        print(f"moviekit recommend: error: {exc}", file=sys.stderr)
        return 2

    except (TMDbAPIError, sqlite3.Error, OSError) as exc:
        print(f"moviekit recommend: {exc}", file=sys.stderr)
        return 1

    print("\n========== TOP 10 ==========\n")

    if not prime_movies:
        print("No eligible Prime Video US recommendations found.")
    for recommendation in prime_movies:
        movie = recommendation.movie
        print(f"{movie.title} ({movie.year}) | Score: {recommendation.score:.2f}")
        print(f"  {recommendation.provider}")
        for reason in recommendation.reasons:
            print(f"  - {reason}")

    return 0


def collections_import(args: argparse.Namespace) -> int:
    from .application import Import2013Collection

    source = Path(args.source)
    try:
        result = Import2013Collection().execute(source)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Collection import failed: {exc}", file=sys.stderr)
        return 1
    print(f"Collection imported: {result.slug}")
    print(f"Editorial entries: {result.editorial_entries}")
    print(f"Inserted: {result.inserted}; updated: {result.updated}")
    print(f"Canonical links: {result.matched}; recommendable: {result.recommendable}")
    print(f"Unresolved: {result.unresolved}; ambiguous: {result.ambiguous}; "
          f"grouped: {result.grouped}; empty title: {result.empty_title}")
    return 0


def collections_list(_args: Optional[argparse.Namespace] = None) -> int:
    from .application import ListCollections

    for collection in ListCollections().execute():
        print(f"{collection.slug}: {collection.name} ({collection.editorial_entries} entries, "
              f"{collection.recommendable} recommendable)")
    return 0


def collections_show(args: argparse.Namespace) -> int:
    from .application import ShowCollection
    from .collection_repository import CollectionNotFoundError

    try:
        collection = ShowCollection().execute(args.slug)
    except CollectionNotFoundError as exc:
        print(f"moviekit collections: error: {exc}", file=sys.stderr)
        return 2
    print(f"{collection.slug}: {collection.name}")
    print(f"Editorial entries: {collection.editorial_entries}")
    print(f"Matched: {collection.matched}; recommendable: {collection.recommendable}")
    print(f"Unresolved: {collection.unresolved}; ambiguous: {collection.ambiguous}; "
          f"grouped: {collection.grouped}; empty title: {collection.empty_title}")
    return 0


def search(args: argparse.Namespace) -> int:
    """Search movies in the local MovieKit database."""
    from .application import SearchMovies

    watched_filter = None
    if args.watched:
        watched_filter = True
    elif args.unwatched:
        watched_filter = False

    results = SearchMovies().execute(
        args.text,
        limit=args.limit,
        watched=watched_filter,
    )

    if not results:
        print(f'No movies found for "{args.text}".')
        return 0

    for index, result in enumerate(results):
        if index:
            print()

        movie = result.movie
        print(_highlight_match(movie.title, args.text))
        print(f"Year: {movie.year if movie.year is not None else 'Unknown'}")
        print(f"Status: {'Watched' if result.watched else 'Unwatched'}")

        if movie.tmdb_id is not None:
            print(f"TMDB ID: {movie.tmdb_id}")

        print(f"Letterboxd URL: {movie.letterboxd_url}")

    return 0


def availability_sync(args: argparse.Namespace) -> int:
    """Synchronize streaming availability for one local movie."""
    from .application import SyncAvailability

    use_case_result = SyncAvailability().execute_movie(args.title)
    if use_case_result.movie is None:
        print(f'No local movie found for "{args.title}".')
        return 0

    movie = use_case_result.movie
    result = use_case_result.sync_result

    if result is None or not result.success:
        print(f"Could not sync availability for {_format_movie_title(movie)}.")
        if result is not None and result.error_message:
            print(result.error_message)
        return 0

    if result.availability_records_written == 0:
        print("No streaming availability found.")
        return 0

    print("Synced:")
    print(_format_movie_title(movie))
    print()
    print("Providers:")
    for record in use_case_result.availability:
        print(f"✓ {record.provider_name} ({record.access_type})")

    return 0


def metadata_sync(args: argparse.Namespace) -> int:
    """Synchronize TMDb metadata for one local movie."""
    from .application import SyncMetadata

    use_case_result = SyncMetadata().execute_movie(args.title)
    if use_case_result.movie is None:
        print(f'No local movie found for "{args.title}".')
        return 0

    movie = use_case_result.movie
    if use_case_result.error_message:
        print(f"Could not sync metadata for {_format_movie_title(movie)}.")
        print(use_case_result.error_message)
        return 0

    result = use_case_result.sync_result
    if result is None or not result.success:
        print(f"Could not sync metadata for {_format_movie_title(movie)}.")
        if result is not None and result.error_message:
            print(result.error_message)
        return 0

    print("Metadata synced:")
    print(_format_movie_title(movie))
    if result.tmdb_id is not None:
        print(f"TMDB ID: {result.tmdb_id}")
    if _has_value(result.tmdb_title):
        print(f"TMDb Title: {result.tmdb_title}")
    if result.runtime is not None:
        print(f"Runtime: {result.runtime} min")
    if _has_value(result.director):
        print(f"Director: {result.director}")
    if result.genres:
        print(f"Genres: {', '.join(result.genres)}")

    return 0


def tonight(_args: Optional[argparse.Namespace] = None) -> int:
    """Print one random unwatched movie recommendation."""
    from .application import RecommendTonight

    recommendation = RecommendTonight().execute()

    if recommendation is None:
        print("No unwatched movies found.")
        return 0

    print(_format_tonight_recommendation(recommendation.movie, recommendation.provider))
    return 0


def _format_movie_title(movie) -> str:
    title = _display_title(movie.title)
    if _has_value(movie.year):
        return f"{title} ({movie.year})"

    return title


def _format_tonight_recommendation(details, provider: str | None = None) -> str:
    title = _format_movie_title(details)

    metadata = []

    if _has_value(details.rating):
        metadata.append(f"⭐ TMDb Rating : {details.rating:.1f}")

    if _has_value(details.runtime):
        metadata.append(f"⏱ Runtime     : {details.runtime} min")

    directors = [
        credit.name
        for credit in details.credits
        if credit.role.lower() == "director" and _has_value(credit.name)
    ]
    if directors:
        metadata.append(f"🎬 Director    : {', '.join(directors)}")

    genres = [genre for genre in details.genres if _has_value(genre)]
    if genres:
        metadata.append(f"🎭 Genres      : {', '.join(genres)}")

    if _has_value(provider):
        metadata.append(f"📺 Provider    : {provider}")

    lines = [
        "🎬 Tonight's Movie",
        "────────────────────────────────",
        "",
        title,
        "",
    ]

    if metadata:
        lines.extend(metadata)
        lines.append("")

    lines.extend(
        [
            "🔗 Letterboxd",
            details.letterboxd_url,
        ]
    )

    return "\n".join(lines)


def _has_value(value) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() != "unknown"

    return True


def _display_title(title: str) -> str:
    acronyms = {
        "ii",
        "iii",
        "iv",
        "v",
        "vi",
        "vii",
        "viii",
        "ix",
        "x",
        "tmdb",
        "usa",
        "uk",
    }
    small_words = {
        "a",
        "an",
        "and",
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }

    def replace(match: re.Match) -> str:
        word = match.group(0)
        lowered = word.lower()

        if len(word) > 1 and word.isupper():
            return word
        if lowered in acronyms:
            return lowered.upper()
        if match.start() > 0 and lowered in small_words:
            return lowered

        return word[0].upper() + word[1:].lower()

    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", replace, title)


def _highlight_match(value: str, text: str) -> str:
    query = text.strip()
    if not query:
        return value

    return re.sub(
        re.escape(query),
        lambda match: f"[{match.group(0)}]",
        value,
        flags=re.IGNORECASE,
    )


def init_database(_args: Optional[argparse.Namespace] = None) -> int:
    """Create the MovieKit SQLite database."""
    from .application import InitializeDatabase

    database_path = InitializeDatabase().execute()
    print(f"MovieKit database initialized: {database_path}")

    return 0


def personal_enrich(args: argparse.Namespace) -> int:
    from .application import EnrichPersonalMetadata

    def progress(movie, status, result):
        print(f"[{result.processed}] {movie.title} ({movie.year}): {status}", flush=True)

    try:
        result = EnrichPersonalMetadata().execute(
            args.username, limit=args.limit, retry_unresolved=args.retry_unresolved,
            retry_failed=args.retry_failed, refresh=args.refresh, dry_run=args.dry_run, progress=progress,
        )
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Personal metadata enrichment failed: {exc}", file=sys.stderr)
        return 1
    mode = "Dry-run personal metadata" if args.dry_run else "Personal metadata"
    print(f"{mode}: total={result.total}, processed={result.processed}, "
          f"enriched={result.enriched}, cached={result.skipped}, "
          f"cached_resolved={result.cached_resolved}, cached_unresolved={result.cached_unresolved}, "
          f"cached_failed={result.cached_failed}, metadata_pending={result.metadata_pending}, unresolved={result.unresolved}, "
          f"failed={result.failed}, remaining={result.remaining}")
    return 1 if result.failed or result.unresolved else 0


def personal_sync(args: argparse.Namespace) -> int:
    from .application import SyncPersonalLibrary

    try:
        result = SyncPersonalLibrary().execute(args.source, args.username)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Personal sync failed: {exc}", file=sys.stderr)
        return 1
    print("Personal Library sync completed")
    print(f"Sync run: {result.sync_run_id}")
    print(f"Movies processed: {result.movies}")
    print(f"Canonical matches: {result.canonical_matches}")
    print(f"Unmatched movies: {result.unmatched}")
    print(f"Ambiguous matches: {result.ambiguous}")
    print(f"Records inserted: {result.inserted}")
    print(f"Records updated: {result.updated}")
    print(f"Watch events (account total): {result.watch_events}")
    print(f"Ratings (account total): {result.ratings}")
    print(f"Reviews (account total): {result.reviews}")
    print(f"Likes (account total): {result.likes}")
    print(f"Skipped rows: {len(result.issues)}")
    for issue in result.issues[:20]:
        print(f"  {issue.filename}:{issue.row}: {issue.message}", file=sys.stderr)
    if len(result.issues) > 20:
        print(f"  ... {len(result.issues) - 20} more skipped rows", file=sys.stderr)
    return 1 if result.issues else 0


def personal_status(args: argparse.Namespace) -> int:
    from .application import GetPersonalLibraryStatus

    try:
        status = GetPersonalLibraryStatus().execute(args.username)
    except (OSError, sqlite3.Error) as exc:
        print(f"Personal status failed: {exc}", file=sys.stderr)
        return 1
    if status is None:
        print(f"No personal library found for {args.username}.")
        return 0
    print(f"Personal Library: {status.username}")
    print(f"Movies: {status.movies}")
    print(f"Canonical matches: {status.canonical_matches}")
    print(f"Unlinked movies: {status.movies - status.canonical_matches}")
    print(f"Watch events: {status.watch_events}")
    print(f"Ratings: {status.ratings}")
    print(f"Reviews: {status.reviews}")
    print(f"Likes: {status.likes}")
    if status.last_sync:
        print(f"Last sync: {status.last_sync['status']} ({status.last_sync['finished_at']} UTC)")
    return 0


def personal_identity_status(args: argparse.Namespace) -> int:
    from .application import GetPersonalIdentityStatus

    try:
        rows = GetPersonalIdentityStatus().execute(args.username)
    except (OSError, sqlite3.Error) as exc:
        print(f"Personal identity status failed: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print(f"No personal library found for {args.username}.")
        return 0
    print(f"Personal identity status: {args.username}")
    for status, metadata_status, count in rows:
        print(f"{status}/{metadata_status}: {count}")
    return 0


def personal_unresolved(args: argparse.Namespace) -> int:
    from .application import ListUnresolvedPersonalIdentities

    try:
        rows = ListUnresolvedPersonalIdentities().execute(args.username)
    except (OSError, sqlite3.Error) as exc:
        print(f"Personal unresolved identities failed: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("No unresolved personal identities.")
        return 0
    for title, year, status, tmdb_id, metadata_status, category, message in rows:
        suffix = f"; TMDb {tmdb_id}" if tmdb_id is not None else ""
        failure = f"; {category}: {message}" if category else ""
        print(f"{title} ({year if year is not None else 'unknown'}): {status}/{metadata_status}{suffix}{failure}")
    return 0


def _analytics_report(username):
    from .application import GetAnalyticsReport

    try:
        return GetAnalyticsReport().execute(username), None
    except (OSError, sqlite3.Error) as exc:
        return None, f"Personal analytics unavailable: {exc}. Import a personal library first."


def analytics_summary(args: argparse.Namespace) -> int:
    report, error = _analytics_report(args.username)
    if error:
        print(error, file=sys.stderr)
        return 1
    if report is None:
        print(f"No personal library found for {args.username}.")
        return 0
    stats = report.stats
    print(f"Analytics summary: {report.username}")
    print(f"Unique watched films: {stats.watched}")
    print(f"Viewing events: {stats.watch_events}")
    print(f"Explicit rewatch events: {stats.rewatch_events} ({stats.rewatched_movies} films)")
    print(f"Personal films without canonical link: {report.unmatched_personal_movies}/{stats.movies}")
    print(f"Genre metadata coverage: {stats.genre_coverage}/{stats.movies}")
    print(f"Director metadata coverage: {stats.director_coverage}/{stats.movies}")
    print(f"Actor metadata coverage: {stats.actor_coverage}/{stats.movies}")
    _print_pairs("Watched films by release decade", report.watched_decades, suffix="s")
    _print_groups("Watched films by genre", stats.genres)
    _print_groups("Most frequently watched directors (top 10)", stats.directors, limit=10)
    _print_groups("Most frequently watched actors (top 10)", stats.actors, limit=10)
    _print_pairs("Viewing activity by calendar year", stats.activity_by_year)
    print(f"Undated or invalid viewing events: {stats.undated_events}")
    return 0


def analytics_taste(args: argparse.Namespace) -> int:
    report, error = _analytics_report(args.username)
    if error:
        print(error, file=sys.stderr)
        return 1
    if report is None:
        print(f"No personal library found for {args.username}.")
        return 0
    taste = report.taste
    print(f"Taste profile: {report.username}")
    if not taste.ratings_available:
        print("Explicit preference inference unavailable: no valid Letterboxd ratings.")
        print("Observed viewing behavior remains available through `moviekit analytics summary`.")
        return 0
    print(f"Rating scale: {taste.rating_scale}")
    print(f"Rated films: {taste.rated_movies}; average: {taste.average_rating:.2f}/5")
    print("Rating distribution:")
    for rating, count in taste.distribution:
        print(f"  {rating:.1f}: {count}")
    _print_taste_groups("Highest-rated genres", taste.genres, limit=10)
    _print_favorite_taste_groups("Favorite genres by likes", taste.genres)
    _print_taste_groups("Highest-rated directors", taste.directors, limit=10)
    _print_favorite_taste_groups("Favorite directors by likes", taste.directors)
    _print_taste_groups("Highest-rated actors", taste.actors, limit=10)
    _print_favorite_taste_groups("Favorite actors by likes", taste.actors)
    _print_taste_groups("Rated release decades", taste.decades)
    return 0


def analytics_collections(args: argparse.Namespace) -> int:
    report, error = _analytics_report(args.username)
    if error:
        print(error, file=sys.stderr)
        return 1
    if report is None:
        print(f"No personal library found for {args.username}.")
        return 0
    for progress in report.collections:
        coverage = _percent(progress.coverage_percent)
        completed = _percent(progress.progress_percent)
        print(f"{progress.slug}: {progress.name}")
        print(f"  Editorial entries: {progress.editorial_entries}")
        print(f"  Resolved film identities: {progress.resolved_films}/{progress.editorial_entries} ({coverage} coverage)")
        print(f"  Watched resolved films: {progress.watched_resolved_films}/{progress.resolved_films} ({completed} progress)")
        print(f"  Unwatched resolved films: {progress.unwatched_resolved_films}")
        print(f"  Unresolved entries: {progress.unresolved_entries}; ambiguous: {progress.ambiguous_entries}; "
              f"grouped: {progress.grouped_entries}")
        if progress.grouped_entries:
            print("  Grouped entries are not counted as complete from a single watched film.")
    return 0


def analytics_profile(args: argparse.Namespace) -> int:
    if args.format != "json":
        print("moviekit analytics profile: error: only --format json is supported", file=sys.stderr)
        return 2
    report, error = _analytics_report(args.username)
    if error:
        print(error, file=sys.stderr)
        return 1
    if report is None:
        print(f"No personal library found for {args.username}.", file=sys.stderr)
        return 2
    print(json.dumps(_profile_json(report), indent=2, sort_keys=True))
    return 0


def _print_pairs(title, pairs, suffix=""):
    print(f"{title}:")
    for name, count in pairs:
        print(f"  {name}{suffix}: {count}")
    if not pairs:
        print("  No data")


def _print_groups(title, groups, limit=None):
    print(f"{title}:")
    ranked = sorted(groups, key=lambda item: (-item.watched, item.name.casefold()))
    if limit is not None:
        ranked = ranked[:limit]
    for group in ranked:
        print(f"  {group.name}: {group.watched}")
    if not groups:
        print("  No metadata")


def _print_taste_groups(title, groups, limit=None):
    supported = [group for group in groups if group.rated >= 3]
    ranked = sorted(supported, key=lambda item: (-item.average_rating, -item.rated, item.name.casefold()))
    if limit is not None:
        ranked = ranked[:limit]
    print(f"{title} (minimum 3 rated films):")
    for group in ranked:
        print(f"  {group.name}: {group.average_rating:.2f}/5 ({group.rated} rated, {group.evidence} evidence)")
    if not supported:
        print("  Insufficient evidence")


def _print_favorite_taste_groups(title, groups, limit=10):
    ranked = sorted((group for group in groups if group.liked),
                    key=lambda item: (-item.liked, -item.rated, item.name.casefold()))[:limit]
    print(f"{title} (top {limit}):")
    for group in ranked:
        print(f"  {group.name}: {group.liked} liked films ({group.rated} rated, {group.evidence} evidence)")
    if not ranked:
        print("  No liked films with metadata")


def _percent(value):
    return "N/A" if value is None else f"{value:.1f}%"


def _profile_json(report):
    stats, taste = report.stats, report.taste
    def taste_groups(groups):
        return [{"name": group.name, "rated_films": group.rated, "liked_films": group.liked,
                 "average_rating": group.average_rating, "evidence": group.evidence}
                for group in groups]
    limitations = []
    if not taste.ratings_available:
        limitations.append("No valid personal ratings; explicit preference inference is unavailable.")
    if report.unmatched_personal_movies:
        limitations.append("Unmatched personal films are included in viewing totals but lack canonical metadata.")
    if any(progress.grouped_entries for progress in report.collections):
        limitations.append("Grouped editorial entries cannot be completed from one watched film.")
    return {
        "schema_version": "moviekit.personal-profile.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "username": report.username,
        "data_coverage": {
            "library_movies": stats.movies, "unique_watched_films": stats.watched,
            "rated_films": stats.rated, "liked_films": stats.liked,
            "linked_personal_movies": report.linked_personal_movies,
            "unmatched_personal_movies": report.unmatched_personal_movies,
            "genre_metadata_movies": stats.genre_coverage,
            "director_metadata_movies": stats.director_coverage,
            "actor_metadata_movies": stats.actor_coverage,
        },
        "viewing_behavior": {
            "viewing_events": stats.watch_events, "explicit_rewatch_events": stats.rewatch_events,
            "rewatched_films": stats.rewatched_movies, "activity_by_year": dict(stats.activity_by_year),
            "release_decades": {f"{decade}s": count for decade, count in report.watched_decades},
            "undated_or_invalid_events": stats.undated_events,
        },
        "explicit_preferences": {
            "available": taste.ratings_available, "rating_scale": taste.rating_scale,
            "average_rating": taste.average_rating, "rating_distribution": dict(taste.distribution),
            "genres": taste_groups(taste.genres), "directors": taste_groups(taste.directors),
            "actors": taste_groups(taste.actors),
            "release_decades": taste_groups(taste.decades),
        },
        "collection_progress": [
            {"slug": item.slug, "editorial_entries": item.editorial_entries,
             "resolved_films": item.resolved_films, "watched_resolved_films": item.watched_resolved_films,
             "unwatched_resolved_films": item.unwatched_resolved_films,
             "unresolved_entries": item.unresolved_entries, "ambiguous_entries": item.ambiguous_entries,
             "grouped_entries": item.grouped_entries, "coverage_percent": item.coverage_percent,
             "progress_percent_among_resolved": item.progress_percent}
            for item in report.collections
        ],
        "limitations": limitations,
    }


def personal_stats(args: argparse.Namespace) -> int:
    from .application import GetPersonalStats
    from .personal_analytics_service import PersonalAnalyticsService

    try:
        stats = GetPersonalStats().execute(args.username)
    except (OSError, sqlite3.Error) as exc:
        print(f"Personal stats unavailable: {exc}. Import a personal library first.", file=sys.stderr)
        return 1
    if stats is None:
        print(f"No personal library found for {args.username}.")
        return 0
    print(f"Personal analytics: {stats.username}")
    print(f"Library movies: {stats.movies}")
    print(f"Watched movies: {stats.watched}")
    print(f"Rated movies: {stats.rated}")
    print(f"Liked movies: {stats.liked}")
    average = f"{stats.average_rating:.2f}/5" if stats.average_rating is not None else "N/A"
    print(f"Average personal rating: {average}")
    print("Rating distribution (current personal ratings):")
    for rating, count in stats.rating_distribution:
        print(f"  {rating:.1f}: {count}")
    if stats.invalid_ratings:
        print(f"Invalid ratings excluded: {stats.invalid_ratings}")
    print(f"Watch events: {stats.watch_events}")
    print("Activity by viewing year (events):")
    for year, count in stats.activity_by_year:
        print(f"  {year}: {count}")
    if not stats.activity_by_year:
        print("  No dated viewing activity")
    print(f"  Unknown/invalid viewing date: {stats.undated_events}")
    print("Library movies by release decade:")
    for decade, count in stats.decades:
        print(f"  {decade}s: {count}")
    print(f"  Unknown release year: {stats.unknown_release_year}")
    print(f"Explicit rewatch events: {stats.rewatch_events} ({stats.rewatched_movies} movies)")
    print(f"Movies with multiple logged watches: {stats.multiple_logged_watches}")
    for label, groups, coverage in (
        ("genres", stats.genres, stats.genre_coverage),
        ("directors", stats.directors, stats.director_coverage),
        ("actors", stats.actors, stats.actor_coverage),
    ):
        print(f"{label.capitalize()} metadata coverage: {coverage}/{stats.movies} library movies")
        print(f"Highest-rated {label} (top 5):")
        highest = PersonalAnalyticsService.highest_rated(groups)
        for group in highest:
            print(f"  {group.name}: {group.average_rating:.2f}/5 ({group.rated} rated movies)")
        if not highest:
            print("  Insufficient metadata or personal ratings")
        print(f"Favorite {label} by film likes (top 5):")
        favorites = PersonalAnalyticsService.favorites(groups)
        for group in favorites:
            print(f"  {group.name}: {group.liked} liked movies ({group.watched} watched)")
        if not favorites:
            print("  Insufficient metadata or film likes")
    if stats.canonical_total:
        percentage = stats.canonical_watched / stats.canonical_total * 100
        print(f"Canonical 1001 progress (personal watches): {stats.canonical_watched}/{stats.canonical_total} ({percentage:.1f}%)")
        print(f"Canonical remaining: {stats.canonical_total - stats.canonical_watched}")
    else:
        print("Canonical 1001 progress: N/A (canonical collection not loaded)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    from .search_service import DEFAULT_SEARCH_LIMIT

    parser = argparse.ArgumentParser(prog="moviekit")
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("sync")
    sync_parser.set_defaults(func=sync)
    sync_subparsers = sync_parser.add_subparsers(dest="sync_command")

    sync_metadata_parser = sync_subparsers.add_parser("metadata")
    sync_metadata_parser.add_argument("--limit", type=int, help="Maximum pending films to attempt in this batch")
    sync_metadata_parser.set_defaults(func=sync_metadata)

    sync_availability_parser = sync_subparsers.add_parser("availability")
    sync_availability_parser.set_defaults(func=sync_availability)

    sync_all_parser = sync_subparsers.add_parser("all")
    sync_all_parser.set_defaults(func=sync_all)

    recommend_parser = subparsers.add_parser("recommend")
    recommend_parser.add_argument(
        "--from-year", type=int, help="Include movies released in this year or later"
    )
    recommend_parser.add_argument(
        "--to-year", type=int, help="Include movies released in this year or earlier"
    )
    recommend_parser.add_argument("--username", help="Personal account (automatic when only one exists)")
    recommend_parser.add_argument("--collection", choices=("letterboxd-1001", "1001-2013", "intersection", "all"),
                                  help="Curated collection selector")
    recommend_parser.set_defaults(func=recommend)

    collections_parser = subparsers.add_parser("collections", help="Import and inspect curated collections")
    collections_commands = collections_parser.add_subparsers(dest="collections_command", required=True)
    collections_list_parser = collections_commands.add_parser("list")
    collections_list_parser.set_defaults(func=collections_list)
    collections_show_parser = collections_commands.add_parser("show")
    collections_show_parser.add_argument("slug")
    collections_show_parser.set_defaults(func=collections_show)
    collections_import_parser = collections_commands.add_parser("import")
    collections_import_parser.add_argument("--source", required=True,
                                           help="Validated collection CSV obtained by the user")
    collections_import_parser.set_defaults(func=collections_import)

    tonight_parser = subparsers.add_parser("tonight")
    tonight_parser.set_defaults(func=tonight)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("text")
    search_parser.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_SEARCH_LIMIT,
    )
    search_filters = search_parser.add_mutually_exclusive_group()
    search_filters.add_argument("--watched", action="store_true")
    search_filters.add_argument("--unwatched", action="store_true")
    search_parser.set_defaults(func=search)

    db_parser = subparsers.add_parser("db")
    db_subparsers = db_parser.add_subparsers(dest="db_command")

    db_init_parser = db_subparsers.add_parser("init")
    db_init_parser.set_defaults(func=init_database)

    availability_parser = subparsers.add_parser("availability")
    availability_subparsers = availability_parser.add_subparsers(
        dest="availability_command"
    )

    availability_sync_parser = availability_subparsers.add_parser("sync")
    availability_sync_parser.add_argument("title")
    availability_sync_parser.set_defaults(func=availability_sync)

    metadata_parser = subparsers.add_parser("metadata")
    metadata_subparsers = metadata_parser.add_subparsers(dest="metadata_command")

    metadata_sync_parser = metadata_subparsers.add_parser("sync")
    metadata_sync_parser.add_argument("title")
    metadata_sync_parser.set_defaults(func=metadata_sync)

    personal_parser = subparsers.add_parser("personal", help="Import and inspect a personal Letterboxd library")
    personal_commands = personal_parser.add_subparsers(dest="personal_command", required=True)
    personal_sync_parser = personal_commands.add_parser("sync", help="Import an extracted Letterboxd export")
    personal_sync_parser.add_argument("--source", required=True, help="Directory containing exported CSV files")
    personal_sync_parser.add_argument("--username", required=True, help="Letterboxd account username")
    personal_sync_parser.set_defaults(func=personal_sync)

    enrich_parser = personal_commands.add_parser("enrich", help="Resume personal TMDb metadata enrichment")
    enrich_parser.add_argument("--username", required=True)
    enrich_parser.add_argument("--limit", type=int, help="Maximum films to process in this batch")
    enrich_parser.add_argument("--retry-unresolved", action="store_true", help="Retry cached unmatched/ambiguous films")
    enrich_parser.add_argument("--retry-failed", action="store_true", help="Retry cached TMDb or metadata failures")
    enrich_parser.add_argument("--refresh", action="store_true", help="Refetch completed metadata as well")
    enrich_parser.add_argument("--dry-run", action="store_true", help="Resolve/enrich without writing identity or metadata rows")
    enrich_parser.set_defaults(func=personal_enrich)
    identities_parser = personal_commands.add_parser("identities", help="Show cached personal identity states")
    identities_parser.add_argument("--username", required=True)
    identities_parser.set_defaults(func=personal_identity_status)
    unresolved_parser = personal_commands.add_parser("unresolved", help="List auditable unresolved personal identities")
    unresolved_parser.add_argument("--username", required=True)
    unresolved_parser.set_defaults(func=personal_unresolved)
    personal_status_parser = personal_commands.add_parser("status", help="Show local account totals")
    personal_status_parser.add_argument("--username", required=True)
    personal_status_parser.set_defaults(func=personal_status)
    personal_stats_parser = personal_commands.add_parser("stats", help="Show local personal analytics")
    personal_stats_parser.add_argument("--username", required=True)
    personal_stats_parser.set_defaults(func=personal_stats)

    analytics_parser = subparsers.add_parser("analytics", help="Read-only personal viewing analytics")
    analytics_commands = analytics_parser.add_subparsers(dest="analytics_command", required=True)
    for name, function, help_text in (
        ("summary", analytics_summary, "Show viewing behavior and metadata coverage"),
        ("taste", analytics_taste, "Show rating-backed personal taste evidence"),
        ("collections", analytics_collections, "Show progress for curated collections"),
    ):
        command = analytics_commands.add_parser(name, help=help_text)
        command.add_argument("--username", required=True)
        command.set_defaults(func=function)
    profile_parser = analytics_commands.add_parser("profile", help="Emit a versioned personal profile")
    profile_parser.add_argument("--username", required=True)
    profile_parser.add_argument("--format", required=True, choices=("json",))
    profile_parser.set_defaults(func=analytics_profile)

    for command in ("providers", "chat"):
        subparser = subparsers.add_parser(command)
        subparser.set_defaults(func=_not_implemented)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return args.func(args)
