import argparse
from typing import Optional

from .movie_repository import MovieRepository


def _not_implemented(_args: argparse.Namespace) -> int:
    print("Not implemented")
    return 0


def sync(_args: Optional[argparse.Namespace] = None) -> int:
    """Refresh watched/unwatched 1001 CSV outputs and print a summary."""
    repository = MovieRepository()
    movies, seen, unseen = repository.update_watched_1001_outputs()

    print("MovieKit Sync")
    print("-------------------")
    print(f"Watched: {len(seen)}")
    print(f"Remaining: {len(unseen)}")
    print(f"Progress: {len(seen)/len(movies):.1%}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moviekit")
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("sync")
    sync_parser.set_defaults(func=sync)

    for command in ("recommend", "providers", "chat"):
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
