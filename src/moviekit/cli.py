import argparse
from typing import Optional


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


def init_database(_args: Optional[argparse.Namespace] = None) -> int:
    """Create the MovieKit SQLite database."""
    from .database import DEFAULT_DATABASE_PATH, initialize_database

    database_path = initialize_database(DEFAULT_DATABASE_PATH)
    print(f"MovieKit database initialized: {database_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moviekit")
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("sync")
    sync_parser.set_defaults(func=sync)

    recommend_parser = subparsers.add_parser("recommend")
    recommend_parser.set_defaults(func=recommend)

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