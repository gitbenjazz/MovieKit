# Developer Guide

This guide captures the conventions used by the v0.2 MovieKit codebase.

## Project Layout

- `src/moviekit/cli.py`: command-line entry point.
- `src/moviekit/database.py`: SQLite schema and database initialization.
- `src/moviekit/database_repository.py`: all SQLite reads and writes.
- `src/moviekit/movie_repository.py`: CSV loading and CSV-derived record creation.
- `src/moviekit/search_service.py`: search orchestration and result ranking.
- `src/moviekit/sync_service.py`: sync workflow coordinating CSV and database repositories.
- `tests/`: unittest-based regression coverage.

## Layering Rules

- Keep SQL inside `database_repository.py` unless the schema itself is being edited.
- Keep CLI functions thin: parse arguments, call services, print results.
- Put workflow logic in service classes.
- Keep public CLI and service behavior stable unless a feature explicitly requires a change.

## SQLite Schema

Schema v2 keeps `movies` as the central table.

- `movies.letterboxd_url` is the movie business key.
- `watched.movie_id` points to `movies.id`.
- Genres, credits, source lists, providers, countries, and availability are normalized into their own tables.
- `initialize_database()` enables `PRAGMA foreign_keys = ON`.

Compatibility guards currently drop incompatible legacy v1 tables before applying Schema v2. A future migration system should replace those guards.

## Sync Flow

`moviekit sync` follows this path:

1. `MovieRepository` reads `movies.csv` and `watched.csv`.
2. `SyncService` asks the CSV repository for movie and watched records.
3. `DatabaseRepository.save_movies()` upserts canonical movie records.
4. `DatabaseRepository.save_watched()` rebuilds watched history and resolves rows to canonical movies by title/year where possible.
5. The CLI prints the sync summary.

## Search Flow

`moviekit search "<text>"` follows this path:

1. CLI parses text, limit, and watched filters.
2. `SearchService.search()` calls repository query methods.
3. `DatabaseRepository.search_movies()` performs case-insensitive partial matching.
4. `DatabaseRepository.get_watched_movie_ids()` returns canonical watched movie IDs.
5. `SearchService` ranks, filters, and limits results.
6. CLI prints title, year, watched state, optional TMDB ID, and Letterboxd URL.

## Testing

Use:

```bash
python3 -m unittest discover
```

The tests use temporary SQLite databases and should not depend on the workspace `movies.db`.

Add regression tests for bugs that involve CSV-to-database relationships, especially when short `boxd.it` watched URLs need to resolve to canonical `letterboxd.com/film/...` movie rows.

