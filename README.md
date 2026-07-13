# MovieKit

MovieKit is a local-first toolkit for tracking and exploring the 1001 movies list with CSV inputs, SQLite storage, and a small command-line interface.

## What's New in v0.2

- Normalized SQLite Schema v2 with movies as the central table.
- `moviekit sync` now populates normalized movie and watched-history tables.
- `moviekit search "<text>"` searches the local database with watched/unwatched status.
- Search supports partial, case-insensitive matching, result limits, and watched filters.
- Watch history now resolves to canonical movie rows while preserving duplicate history entries.

## Common Commands

```bash
moviekit db init
moviekit sync
moviekit search "godfather"
moviekit search "godfather" --watched --limit 5
```

If the console script is not installed on your shell path, use the repository virtual environment:

```bash
.venv/bin/moviekit sync
```

## Development

See [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for schema, repository, and testing notes.

