# Developer Guide

This guide captures the conventions used by the MovieKit codebase.

## Project Layout

- `src/moviekit/cli.py`: command-line entry point.
- `src/moviekit/bulk_sync_service.py`: library-wide synchronization orchestration.
- `src/moviekit/config.py`: user configuration loading and persistence.
- `src/moviekit/database.py`: SQLite schema and database initialization.
- `src/moviekit/database_repository.py`: canonical SQLite reads and writes.
- `src/moviekit/personal_analytics_repository.py`: read-only, account-scoped analytics snapshots.
- `src/moviekit/personal_analytics_service.py`: analytics calculations and preference ordering.
- `src/moviekit/personal_analytics_models.py`: typed analytics input/output records.
- `src/moviekit/collection_analytics_repository.py`: read-only collection-progress queries.
- `src/moviekit/universal_identity_repository.py`: verified TMDb identities and normalized noncanonical credits.
- `src/moviekit/metadata_service.py`: single-movie TMDb metadata synchronization.
- `src/moviekit/movie_repository.py`: CSV loading and CSV-derived record creation.
- `src/moviekit/provider_backend.py`: provider availability backend interface.
- `src/moviekit/provider_service.py`: provider normalization and availability persistence.
- `src/moviekit/recommendation_engine.py`: recommendation selection and scoring.
- `src/moviekit/search_service.py`: search orchestration and result ranking.
- `src/moviekit/sync_service.py`: sync workflow coordinating CSV and database repositories.
- `src/moviekit/tmdb_client.py`: reusable TMDb HTTP client helpers.
- `src/moviekit/tmdb_provider_backend.py`: TMDb watch-provider backend.
- `tests/`: unittest-based regression coverage.

## Layering Rules

- Keep SQL inside repository modules unless the schema itself is being edited.
- The Personal Library analytics snapshot uses a read-only SQLite connection and one read transaction; collection progress is a separate read-only query.
- The analytics report service builds presentation-neutral typed results; CLI commands only format them.
- Analytics must not infer personal ratings from public metadata or modify Personal Library/canonical rows.
- Keep CLI functions thin: parse arguments, call services, print results.
- Put workflow logic in service classes.
- Keep public CLI and service behavior stable unless a feature explicitly requires a change.

## SQLite Schema

Schema v9 keeps `movies` as the canonical collection and adds an optional
identity layer for personal and editorial films.

- `movies.letterboxd_url` is the movie business key.
- In Phase 1, `movies` contains only the canonical library imported from `movies.csv`; a clean rebuild should contain exactly 1524 movies.
- `watched.movie_id` points to `movies.id`.
- Genres, credits, source lists, providers, countries, and availability are normalized into their own tables.
- `film_identities` is keyed by verified TMDb ID; `identity_people` and
  `identity_credits` keep TMDb-person-backed director/actor credits separate
  from legacy canonical name credits.
- `personal_movie_metadata.identity_id`, `movies.identity_id`, and
  `collection_entries.identity_id` are optional, additive links.  They never
  cause a personal-only row to be inserted into `movies`.
- `personal_movie_metadata.status` records resolution state; its
  `metadata_status` independently records whether a universal TMDb detail
  response has been fetched. `refresh_order` makes bounded refresh batches
  progress without repeating the same first page.
- Failed metadata fetches retain a category, diagnostic, timestamp, and count;
  normal batches skip them and explicit retry is required.
- `initialize_database()` enables `PRAGMA foreign_keys = ON`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the Phase 1 database scope and the future personal-library boundary.

Compatibility guards currently drop incompatible legacy v1 tables before applying Schema v2. A future migration system should replace those guards.

## Sync Flow

`moviekit sync` follows this path:

1. `MovieRepository` reads `movies.csv` and `watched.csv`.
2. `SyncService` asks the CSV repository for movie and watched records.
3. `DatabaseRepository.save_movies()` upserts canonical movie records.
4. `DatabaseRepository.save_watched()` rebuilds watched history and links rows to existing canonical movies where possible.
5. The CLI prints the sync summary.

Watched import must not create rows in `movies`. Unmatched watched entries are skipped and reported.

## Search Flow

`moviekit search "<text>"` follows this path:

1. CLI parses text, limit, and watched filters.
2. `SearchService.search()` calls repository query methods.
3. `DatabaseRepository.search_movies()` performs case-insensitive partial matching.
4. `DatabaseRepository.get_watched_movie_ids()` returns canonical watched movie IDs.
5. `SearchService` ranks, filters, and limits results.
6. CLI prints title, year, watched state, optional TMDB ID, and Letterboxd URL.

## Bulk Sync Flow

`moviekit sync metadata`, `moviekit sync availability`, and `moviekit sync all` keep orchestration in `BulkSyncService`.

1. CLI commands construct `BulkSyncService`.
2. `BulkSyncService` iterates over `DatabaseRepository.get_all_movies()`.
3. Metadata sync delegates each movie to `MetadataSyncService.sync_movie()`.
4. Availability sync delegates each movie to `SyncService.sync_movie()`.
5. `moviekit sync all` runs metadata synchronization first, then availability synchronization.
6. CLI commands print only the returned processed, updated, skipped, and failed counts.

The bulk layer must not know about Typer/argparse, print output, instantiate provider backends, or perform raw SQLite operations.

## Testing

Use:

```bash
python3 -m unittest discover
```

The tests use temporary SQLite databases and should not depend on the workspace `movies.db`.

Add regression tests for bugs that involve CSV-to-database relationships, especially when short `boxd.it` watched URLs need to resolve to canonical `letterboxd.com/film/...` movie rows.
