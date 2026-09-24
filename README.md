# MovieKit

MovieKit is a local-first toolkit for tracking and exploring the 1001 movies list with CSV inputs, SQLite storage, and a small command-line interface.

## Current Scope

MovieKit Phase 1 manages the canonical Letterboxd 1001 movie library imported from `movies.csv`.

- The `movies` table contains only canonical movies from `movies.csv`.
- A clean rebuild is expected to contain exactly **1524 movies**.
- `moviekit sync` imports the canonical library and links watched history to those existing movies.
- Watched imports must never create additional movies.
- Metadata and availability synchronization enrich existing movies only.

Personal Library synchronization is available separately through `moviekit personal sync`.
It imports account-owned films and activity into Schema v3 personal tables, including
films outside the canonical list, without broadening `movies` or changing Phase 1
recommendations.

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

## Personal Library (Sprint 6)

Download and extract the official Letterboxd account export. Supply the directory
containing its CSV files and your Letterboxd username:

```bash
.venv/bin/moviekit personal sync --source "/path/to/extracted-letterboxd-export" --username themonkous
.venv/bin/moviekit personal status --username themonkous
```

If that export is in the existing Documents folder:

```bash
.venv/bin/moviekit personal sync --source "/Users/hatimbenmeziane/Documents/letterboxd-1001" --username themonkous
```

Supported files: `watched.csv`, `ratings.csv`, `diary.csv`, `reviews.csv`, and
`likes/films.csv`. Missing optional files are allowed. A folder containing only
`watched.csv` imports watched films but cannot provide missing reviews or ratings.
Use the extracted directory, not the ZIP archive. No scraping or TMDb calls occur.

The sync reports processed movies, canonical match states, inserted/changed records,
account activity totals, and skipped rows. Status shows local account totals and the
last synchronization result. Exit status is 0 for success, 1 for import failure or
partial success with skipped rows, and 2 for invalid command syntax. On partial
success, valid rows are committed and the errors identify the source file and row.

Re-imports are idempotent. Partial exports do not delete absent personal data.
Personal synchronization does **not** refresh the Phase 1 recommendation history;
continue using the `watched.csv` + `moviekit sync` workflow above for that.
See [Personal Library synchronization](docs/PERSONAL_LIBRARY_SYNC.md) for identity,
watch-event reconciliation, transaction guarantees, and current limitations.

## Personal Analytics (Sprint 7)

```bash
.venv/bin/moviekit personal stats --username themonkous
```

This command reads the local Personal Library without network calls or database
writes. It reports watched/rated/liked film totals, current rating distribution,
viewing activity by year, release decades, rewatches, genre/director preferences,
and canonical progress. Missing dates and metadata are shown explicitly.

- Watched totals count distinct personal films with a watch event; rated-only
  and liked-only films are not assumed watched.
- Activity uses actual `watched_date` values, not import dates. Undated watched
  markers and invalid dates appear in the unknown bucket.
- Decades cover all personal films, once each, including rated-only/liked-only films.
- Rewatches show explicit rewatch flags and, separately, films with multiple logged
  watches. Undated watched-state placeholders do not count as logged repeats.
- Highest-rated genres/directors use current **personal** ratings, with sample
  sizes shown. Favorites are ranked by film likes, not by public TMDb scores.
- Genre/director metadata currently comes only from linked canonical films. The
  command shows coverage; it does not fetch missing metadata or infer it from titles.
- Canonical progress counts distinct canonical IDs linked to this account's watched
  films, against the actual canonical collection size. It does not mix in Phase 1
  `watched` or another account's history.

Rankings show the top five. Mean-rating ties use rated-film count then name;
like-count ties use watched-film count then name. No minimum sample threshold is
imposed, so a one-film average is explicitly labeled as such. Multi-genre films
and co-directed films contribute once to each group, never once per watch event.

The figures describe the imported data, not live Letterboxd state. Missing
metadata, unresolved identities, and incomplete exports limit coverage. Personal
stats does not modify synchronization or recommendation behavior.

## Development checks

```bash
.venv/bin/python -m unittest discover
.venv/bin/python -m compileall -q src tests scripts
git diff --check
```

See [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for schema, repository, and testing notes.
