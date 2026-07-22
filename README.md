# MovieKit

MovieKit is a local-first toolkit for tracking and exploring the 1001 movies list with CSV inputs, SQLite storage, and a small command-line interface.

## Current Scope

MovieKit Phase 1 manages the canonical Letterboxd 1001 movie library imported from `movies.csv`.

- The `movies` table contains only canonical movies from `movies.csv`.
- A clean rebuild is expected to contain exactly **1524 movies**.
- `moviekit sync` imports the canonical library and links watched history to those existing movies.
- Watched imports must never create additional movies.
- Metadata and availability synchronization enrich existing movies only.

Personal Letterboxd library synchronization is a future milestone. That future phase may intentionally import watched movies outside the 1001 list, ratings, reviews, diary entries, favorites/likes, and additional metadata. It is not part of Phase 1.

## What's New in v0.2

- Normalized SQLite Schema v2 with movies as the central table.
- `moviekit sync` now populates normalized movie and watched-history tables.
- `moviekit search "<text>"` searches the local database with watched/unwatched status.
- Search supports partial, case-insensitive matching, result limits, and watched filters.
- Watch history now resolves to canonical movie rows while preserving duplicate history entries.

## What's New in v0.3.9

- `moviekit tonight` recommends one unwatched movie from the local library.
- `moviekit availability sync "<movie title>"` syncs streaming providers for one movie.
- `moviekit metadata sync "<movie title>"` enriches one local movie with TMDb metadata.
- `moviekit sync metadata` runs TMDb metadata synchronization across the local library.
- `moviekit sync availability` runs streaming availability synchronization across the local library.
- `moviekit sync all` runs bulk metadata synchronization followed by bulk availability synchronization.

## Common Commands

```bash
moviekit db init
moviekit sync
moviekit search "godfather"
moviekit search "godfather" --watched --limit 5
moviekit tonight
moviekit metadata sync "Alien"
moviekit availability sync "Alien"
moviekit sync metadata
moviekit sync availability
moviekit sync all
```

Bulk synchronization commands print concise summaries:

```bash
moviekit sync metadata
moviekit sync availability
moviekit sync all
```

If the console script is not installed on your shell path, use the repository virtual environment:

```bash
.venv/bin/moviekit sync
```

## Development

See [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for schema, repository, and testing notes.
