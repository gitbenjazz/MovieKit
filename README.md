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

## Refresh Letterboxd history and recommend

MovieKit reads local exports; it does not connect to your Letterboxd account.
Export and unzip your latest Letterboxd data, then replace the project's
`watched.csv` and run `sync` **before** requesting recommendations. For the
export currently kept in Documents, the exact commands are:

```bash
cd /Users/hatimbenmeziane/letterboxd-1001
cp /Users/hatimbenmeziane/Documents/letterboxd-1001/watched.csv ./watched.csv
.venv/bin/moviekit sync
.venv/bin/moviekit recommend
```

For another export location, change the source path in `cp`. Use the full
`watched.csv` export, not a diary or an incremental list: `sync` replaces watched
history rather than appending to it. Re-importing the same export does not
accumulate watched entries. Separate viewing-history rows already present in
the source remain separate. Films outside `movies.csv` are skipped, never added
to the canonical collection by the watched import.

`sync` refreshes both SQLite (used by `search` and `tonight`) and
`unwatched1001.csv` (used by `recommend`). Merely replacing `watched.csv` is not
enough. No Sprint 6 personal-library synchronization is required.

Optional, inclusive release-year filters:

```bash
.venv/bin/moviekit recommend --from-year 1970
.venv/bin/moviekit recommend --to-year 1999
.venv/bin/moviekit recommend --from-year 1970 --to-year 1999
```

Filtering happens before TMDb lookups and selection of up to ten results.
An inverted range exits with status 2; omitting both options preserves the
existing behavior. Recommendations still use CSV order and Prime Video US
subscription availability reported by TMDb, not a personalized ranking.
They require network access and `TMDB_API_KEY`. CSV watched matching still
uses title and year, so differently named titles can require correction.

## Development checks

```bash
.venv/bin/python -m unittest discover
.venv/bin/python -m compileall -q src tests scripts
git diff --check
```

See [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for schema, repository, and testing notes.
