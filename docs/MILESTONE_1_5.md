# Milestone 1.5

Milestone 1.5 turns MovieKit from CSV-first scripts plus a bootstrap database into a normalized local movie database with a user-facing search command.

## Goals

- Normalize the SQLite schema while keeping `movies` central.
- Preserve `letterboxd_url` as the movie business key.
- Keep CLI and sync APIs stable while moving persistence behind repository methods.
- Add a practical `moviekit search` command backed by the repository layer.
- Make watched detection reliable through canonical movie relationships.

## Delivered

- Schema v2 with foreign keys for watch history, genres, credits, lists, providers, countries, and availability.
- `initialize_database()` still exposes the same public API and enables `PRAGMA foreign_keys = ON`.
- Repository writes now upsert movies and related normalized records inside single transactions.
- Repository reads now return `MovieSummary`, `MovieDetails`, and related Python objects.
- `moviekit search "<text>"` supports partial case-insensitive search, highlighted matches, `--limit`, `--watched`, and `--unwatched`.
- Watch history from `watched.csv` resolves to canonical movie rows by title/year when possible.
- Duplicate watch-history entries remain representable in SQLite.
- Regression coverage for search ranking, filters, output formatting, and The Godfather Part II watched-state bug.

## Verification

Run:

```bash
moviekit db init
moviekit sync
moviekit search "godfather"
python3 -m unittest discover
```

When the console script is not on `PATH`, use:

```bash
.venv/bin/moviekit sync
```

## Known Follow-Ups

- Add explicit migrations instead of compatibility guards inside initialization.
- Add richer search ranking or SQLite FTS.
- Expand CLI coverage for details, lists, availability, and provider-backed recommendations.
- Decide whether generated SQLite databases and egg-info metadata should remain tracked.

