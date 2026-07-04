import argparse


def _not_implemented(_args: argparse.Namespace) -> int:
    print("Not implemented")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moviekit")
    subparsers = parser.add_subparsers(dest="command")

    for command in ("sync", "recommend", "providers", "chat"):
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
