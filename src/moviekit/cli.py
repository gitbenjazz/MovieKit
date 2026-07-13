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

    recommend_parser = subparsers.add_parser("recommend")
    recommend_parser.set_defaults(func=recommend)

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
