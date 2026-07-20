from __future__ import annotations

import argparse
import re
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
    from .sync_service import SyncService

    summary = SyncService().sync()

    print("MovieKit Sync")
    print("-------------------")
    print(f"Watched 1001: {summary.watched_movies}")
    print(f"Remaining 1001: {summary.remaining_movies}")
    print(f"Progress: {summary.progress:.1%}")
    print(f"SQLite movies synced: {summary.movies_synced}")
    print(f"SQLite watched history synced: {summary.watched_history_synced}")

    return 0


def sync_metadata(_args: Optional[argparse.Namespace] = None) -> int:
    """Synchronize TMDb metadata for all local movies."""
    from .bulk_sync_service import BulkSyncService

    result = BulkSyncService().sync_metadata()

    _print_bulk_sync_summary("Metadata synchronization completed", result)

    return 0


def sync_availability(_args: Optional[argparse.Namespace] = None) -> int:
    """Synchronize streaming availability for all local movies."""
    from .bulk_sync_service import BulkSyncService

    result = BulkSyncService().sync_availability()

    _print_bulk_sync_summary("Availability synchronization completed", result)

    return 0


def sync_all(_args: Optional[argparse.Namespace] = None) -> int:
    """Synchronize all supported bulk data for local movies."""
    from .bulk_sync_service import BulkSyncService

    result = BulkSyncService().sync_all()

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
    from .recommendation_service import top_recommended_unwatched_movies

    prime_movies = top_recommended_unwatched_movies(
        limit=10,
        verbose=True,
    )

    print("\n========== TOP 10 ==========\n")

    for movie in prime_movies:
        print(movie)

    return 0


def search(args: argparse.Namespace) -> int:
    """Search movies in the local MovieKit database."""
    from .search_service import SearchService

    watched_filter = None
    if args.watched:
        watched_filter = True
    elif args.unwatched:
        watched_filter = False

    results = SearchService().search(
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
    from .database_repository import DatabaseRepository
    from .provider_service import ProviderService
    from .search_service import SearchService
    from .sync_service import SyncService
    from .tmdb_provider_backend import TMDbProviderBackend

    repository = DatabaseRepository()
    results = SearchService(repository).search(args.title, limit=1)
    if not results:
        print(f'No local movie found for "{args.title}".')
        return 0

    movie = results[0].movie
    provider_service = ProviderService(
        repository,
        backend=TMDbProviderBackend(),
    )
    result = SyncService(
        database_repository=repository,
        provider_service=provider_service,
    ).sync_movie(movie)

    if not result.success:
        print(f"Could not sync availability for {_format_movie_title(movie)}.")
        if result.error_message:
            print(result.error_message)
        return 0

    if result.availability_records_written == 0:
        print("No streaming availability found.")
        return 0

    availability = provider_service.get_movie_availability(movie.id)
    print("Synced:")
    print(_format_movie_title(movie))
    print()
    print("Providers:")
    for record in availability:
        print(f"✓ {record.provider_name} ({record.access_type})")

    return 0


def metadata_sync(args: argparse.Namespace) -> int:
    """Synchronize TMDb metadata for one local movie."""
    from .database_repository import DatabaseRepository
    from .metadata_service import MetadataSyncService
    from .search_service import SearchService
    from .tmdb_client import TMDbAPIError, TMDbAuthenticationError

    repository = DatabaseRepository()
    results = SearchService(repository).search(args.title, limit=1)
    if not results:
        print(f'No local movie found for "{args.title}".')
        return 0

    movie = results[0].movie
    try:
        result = MetadataSyncService(repository).sync_movie(movie)
    except TMDbAuthenticationError as exc:
        print(f"Could not sync metadata for {_format_movie_title(movie)}.")
        print(str(exc))
        return 0
    except TMDbAPIError as exc:
        print(f"Could not sync metadata for {_format_movie_title(movie)}.")
        print(str(exc))
        return 0

    if not result.success:
        print(f"Could not sync metadata for {_format_movie_title(movie)}.")
        if result.error_message:
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
    from .database_repository import DatabaseRepository
    from .recommendation_engine import RecommendationEngine

    repository = DatabaseRepository()
    recommendation = RecommendationEngine(repository).recommend_tonight()

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
    from .database import DEFAULT_DATABASE_PATH, initialize_database

    database_path = initialize_database(DEFAULT_DATABASE_PATH)
    print(f"MovieKit database initialized: {database_path}")

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
