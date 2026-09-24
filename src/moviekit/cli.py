from __future__ import annotations

import argparse
import re
import sqlite3
import sys
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

    result = SyncMetadata().execute()

    _print_bulk_sync_summary("Metadata synchronization completed", result)

    return 0


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
    from .recommendation_service import InvalidYearRange

    try:
        prime_movies = RecommendTopMovies().execute(
            limit=10,
            verbose=True,
            from_year=getattr(_args, "from_year", None),
            to_year=getattr(_args, "to_year", None),
        )
    except InvalidYearRange as exc:
        print(f"moviekit recommend: error: {exc}", file=sys.stderr)
        return 2

    print("\n========== TOP 10 ==========\n")

    for movie in prime_movies:
        print(movie)

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
    recommend_parser.set_defaults(func=recommend)

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
    personal_status_parser = personal_commands.add_parser("status", help="Show local account totals")
    personal_status_parser.add_argument("--username", required=True)
    personal_status_parser.set_defaults(func=personal_status)
    personal_stats_parser = personal_commands.add_parser("stats", help="Show local personal analytics")
    personal_stats_parser.add_argument("--username", required=True)
    personal_stats_parser.set_defaults(func=personal_stats)

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
