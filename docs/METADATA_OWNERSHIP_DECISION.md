# Metadata Ownership Decision

This document decides how MovieKit should own movie identity and metadata as it moves from the Phase 1 canonical 1001 database toward a personal Letterboxd library.

No implementation is started by this document.

## Decision Summary

MovieKit should use a phased approach.

Sprint 6 should **not** immediately migrate every workflow to a new shared `catalog_movies` identity. Instead, Sprint 6 should introduce the smallest personal-library model that preserves Phase 1, while explicitly designing it so a shared catalog can become authoritative later.

The long-term authoritative identity for a real-world movie should be `catalog_movies`, but MovieKit should not force that migration in the first Personal Library sprint.

Decision:

```text
Use a phased approach where Sprint 6 starts with the simpler design and migrates to a catalog later.
```

## 1. Movie Identity

MovieKit currently has one movie identity:

```text
movies.id
```

In Phase 1, this means:

```text
one canonical 1001 movie imported from movies.csv
```

The possible future identities are:

- `movies`
- `personal_movies`
- `catalog_movies`

### `movies`

`movies` should continue to exist.

Why:

- Existing CLI commands depend on it.
- Existing repository methods depend on it.
- Existing tests enforce the Phase 1 invariant.
- Documentation now explicitly states that `movies` is canonical-only.
- A clean rebuild must keep exactly 1524 rows in `movies`.

`movies` should not become the general movie catalog during Sprint 6.

If `movies` were broadened to include every personal movie, it would violate the most important Phase 1 invariant and force every existing query to learn how to filter canonical rows.

### `personal_movies`

`personal_movies` may exist in Sprint 6 as an incremental staging and account-owned identity table, but it should not become the long-term authoritative identity for a real-world movie.

Why it may exist:

- It is the least disruptive way to import non-1001 Letterboxd watches.
- It keeps Phase 1 commands isolated from personal-library growth.
- It allows personal-library sync to be implemented without rewriting metadata, availability, search, and recommendation workflows all at once.

Why it should not be permanent authority:

- It duplicates public movie identity fields.
- It creates one row per account/movie relationship unless carefully split.
- It makes cross-account deduplication harder.
- It creates ambiguity with `movies` when a movie is both canonical and personal.

If introduced, `personal_movies` should be treated as transitional and account-scoped, not as "the movie table."

### `catalog_movies`

`catalog_movies` should become the long-term authoritative identity for a real-world movie.

Why:

- A real-world movie should have one public identity inside MovieKit.
- Canonical membership, personal membership, ratings, reviews, diary entries, availability, and metadata can all point to that identity.
- Future AI and MCP integrations need stable, non-ambiguous movie IDs.
- Multiple accounts should not duplicate public movie metadata.

Why not adopt it fully immediately:

- Current code assumes `movies` is central.
- Metadata sync, availability sync, search, tonight, watched status, and details all read from `movies`.
- Moving all of those in Sprint 6 would be high migration risk.
- The immediate business goal is personal import, not a full identity migration.

### Justified Coexistence

Multiple IDs are justified only as a transition:

| Identity | Meaning | Lifetime |
| -------- | ------- | -------- |
| `movies.id` | Canonical 1001 movie identity | Permanent for Phase 1 compatibility |
| `personal_movies.id` | Imported personal-library row or transitional personal identity | Short to medium term |
| `catalog_movies.id` | Long-term real-world movie identity | Long term |

The complexity is justified only if every ID has a clear boundary:

- `movies.id` answers: "Which canonical 1001 movie is this?"
- `personal_movies.id` answers: "Which imported personal-library row is this?"
- `catalog_movies.id` answers: "Which real-world movie is this?"

If Sprint 6 cannot maintain those boundaries, then `catalog_movies` should wait.

## 2. Metadata Ownership

Long-term metadata ownership should be unambiguous.

The table below describes the target ownership model once `catalog_movies` exists.

| Field | Owner Table | Duplicate Allowed | Why |
| ----- | ----------- | ----------------- | --- |
| title | `catalog_movies` | Transitional only in `movies` | Public movie title belongs to the real-world movie identity. `movies.title` remains for Phase 1 compatibility until canonical reads migrate. |
| year | `catalog_movies` | Transitional only in `movies` | Release year is public movie metadata. Canonical `movies.year` remains as imported list data during transition. |
| Letterboxd URL | `catalog_movies` | Transitional only in `movies` | It is the strongest public business key for a movie. Long term, only the catalog should own it. |
| Letterboxd slug | `catalog_movies` | No | The slug is derived from Letterboxd identity and should not be repeated across account tables. |
| TMDb ID | `catalog_movies` | Transitional only in `movies` | TMDb ID is global movie identity metadata. Duplicate ownership would cause enrichment conflicts. |
| TMDb title | `catalog_movies` | Transitional only in `movies` | TMDb title belongs with TMDb metadata for the movie identity. |
| runtime | `catalog_movies` | Transitional only in `movies` | Runtime is public metadata used by both canonical and personal workflows. |
| genres | `catalog_movie_genres` | Transitional duplication allowed in `movie_genres` | Genres are public movie metadata. Existing `movie_genres` remains until canonical workflows migrate. |
| directors | `catalog_movie_credits` | Transitional duplication allowed in `movie_credits` | Directors are public credits. Existing canonical credits remain during transition. |
| cast | `catalog_movie_credits` | No | Cast should be introduced only in the catalog credit model, not the legacy canonical credit model. |
| providers | `catalog_availability` or future generalized `availability` keyed to `catalog_movie_id` | Transitional duplication allowed in current `availability` | Provider availability is about a real-world movie, not an account. Current `availability.movie_id` remains canonical-only during transition. |
| poster path | `catalog_movies` or `catalog_movie_images` | No | Poster paths are public metadata. If multiple image sources are needed, use a separate image table. |
| synopsis | `catalog_movies` or `catalog_movie_descriptions` | No | Synopsis is public metadata. A separate descriptions table is better if multiple sources/languages are needed. |
| release date | `catalog_movies` | No | Release date is public metadata and should be owned by the catalog. |

Important rule:

```text
Account-specific data must never own public movie metadata.
```

Account tables own:

- rating
- review text
- diary date
- watched date
- likes/favorites
- account-specific tags
- import source URIs

Catalog tables own:

- public identity
- public metadata
- public credits
- public genres
- public availability

Canonical tables own:

- membership in the 1001 list
- list position/source
- Phase 1 compatibility fields until migration

## 3. Canonical Movies with `catalog_movies`

If `catalog_movies` is introduced, `movies` should not disappear.

### Data Remaining in `movies`

During transition, `movies` keeps:

- `id`
- `title`
- `year`
- `letterboxd_url`
- `tmdb_id`
- `tmdb_title`
- `rating`
- `runtime`
- timestamps

This is not ideal normalization, but it preserves compatibility.

Long term, `movies` should either become:

1. A compatibility table maintained from catalog data, or
2. A canonical membership table with only canonical-specific fields.

The second option is cleaner, but it is a larger migration.

### Data Moving to `catalog_movies`

Long term, these fields move to `catalog_movies`:

- title
- year
- Letterboxd URL
- Letterboxd slug
- TMDb ID
- TMDb title
- runtime
- poster path
- synopsis
- release date

Genres and credits move to catalog-owned join tables:

- `catalog_movie_genres`
- `catalog_movie_credits`

Availability moves to a catalog-owned availability table:

- `catalog_availability`

### Data That Should Never Be Duplicated Long Term

These should have one long-term owner:

- TMDb ID
- Letterboxd URL
- runtime
- poster path
- synopsis
- release date
- provider availability
- cast
- director credits
- genre membership

During migration, duplication may exist only for compatibility and should be treated as derived or temporary.

### Synchronization

Canonical sync should keep its current behavior in Sprint 6:

```text
movies.csv -> movies
```

If `catalog_movies` exists, canonical sync can additionally upsert catalog rows and bridge rows:

```text
movies.csv -> movies
movies -> catalog_movies
movies.id -> canonical_movie_links.catalog_movie_id
```

But canonical sync must still verify:

```sql
SELECT COUNT(*) FROM movies;
-- 1524
```

## 4. Non-Canonical Movie Lifecycle: Heat (1995)

Example:

```text
Heat (1995)
```

Assume it is not part of the canonical 1001 list for this example.

### First Import

In the phased Sprint 6 design:

1. Letterboxd personal sync reads Heat from the account export.
2. It creates or updates a personal-library record.
3. It does **not** create a row in `movies`.
4. If `catalog_movies` is not yet implemented, it creates `personal_movies`.
5. If `catalog_movies` is implemented, it creates or links `catalog_movies`.

Preferred eventual path:

```text
catalog_movies
    Heat public identity

account_movies
    account membership for Heat
```

### TMDb Metadata

If using the simple Sprint 6 model:

- TMDb metadata for Heat would be stored in `personal_movies`.
- This is acceptable only as a short-lived transitional compromise.

If using the catalog model:

- TMDb metadata is stored in `catalog_movies`.
- Genres/directors/cast are stored in catalog join tables.

Target owner:

```text
catalog_movies + catalog metadata tables
```

### Streaming Availability

If using the simple Sprint 6 model:

- Availability for Heat needs a personal-library availability table or a generalized availability table.
- It should not go into current `availability`, because current `availability.movie_id` references canonical `movies`.

If using the catalog model:

- Availability is stored against `catalog_movie_id`.

Target owner:

```text
catalog_availability
```

### Personal Ratings

Ratings live in account-owned tables:

```text
account_movie_ratings
```

The rating is not public movie metadata and should never live in `movies` or `catalog_movies`.

### Reviews

Reviews live in account-owned content/activity tables:

```text
reviews
```

If the review came through a diary entry, it may be linked to:

```text
diary_entries
watch_events
```

### Watch History

Watch history lives in account-owned event tables:

```text
watch_events
```

It should not use Phase 1 `watched`, because Phase 1 `watched` links only to canonical `movies.id`.

### Future Metadata Enrichment

When metadata sync later runs for Heat:

Simple model:

- Updates `personal_movies`.
- Risk: when Heat later becomes linked to catalog/canonical data, metadata must be moved or merged.

Catalog model:

- Updates `catalog_movies`.
- Account activity remains untouched.
- Any recommendation, analytics, AI, or provider query sees one enriched identity.

## 5. Metadata Synchronization Under Both Architectures

### A. Parallel Personal Library

Rows updated:

- Canonical metadata sync updates `movies`.
- Personal metadata sync updates `personal_movies`.
- Canonical availability sync updates `availability`.
- Personal availability sync needs a new `personal_availability` table or equivalent.

Repositories responsible:

- `DatabaseRepository` remains responsible for canonical `movies`.
- `PersonalLibraryRepository` becomes responsible for `personal_movies`.

Can metadata exist in two places?

- Yes. The same real-world movie can exist in both `movies` and `personal_movies`.

How inconsistency is prevented:

- It is difficult to prevent.
- You need a linker and merge policy.
- You need tests proving metadata updates do not diverge.
- You need rules for which copy wins.

Assessment:

- This is simpler at the beginning and more expensive later.

### B. Shared Catalog

Rows updated:

- Metadata sync updates `catalog_movies`.
- Genres/credits update catalog join tables.
- Availability sync updates catalog availability.
- Canonical `movies` may be updated only for compatibility during migration.

Repositories responsible:

- `CatalogMovieRepository` owns public metadata.
- `CanonicalMovieRepository` owns canonical membership/compatibility.
- `PersonalLibraryRepository` owns account data.
- `AvailabilityRepository` or provider service writes catalog availability.

Can metadata exist in two places?

- During transition, yes: `movies` and `catalog_movies`.
- Long term, no: `catalog_movies` owns public metadata.

How inconsistency is prevented:

- Treat `catalog_movies` as authoritative.
- Treat `movies` metadata as compatibility/derived data.
- Only one service should write authoritative public metadata.
- Add migration tests comparing canonical linked rows to catalog rows.

Assessment:

- More structure early, less confusion later.

## 6. Migration Strategy If `catalog_movies` Is Adopted

### Migration Order

1. Add `catalog_movies`.
2. Add `canonical_movie_links`.
3. Add `external_accounts`.
4. Add account membership and activity tables.
5. Backfill catalog rows from existing `movies`.
6. Backfill canonical links from existing `movies`.
7. Keep existing CLI commands reading from `movies`.
8. Add personal sync writing to catalog/account tables.
9. Gradually migrate metadata and availability services to catalog-aware writes.

### Backfill Strategy

For each row in `movies`:

1. Upsert a `catalog_movies` row using `movies.letterboxd_url`.
2. Copy title/year/TMDb/runtime fields.
3. Create `canonical_movie_links(movie_id, catalog_movie_id)`.
4. Optionally copy genres and credits to catalog tables later.

Backfill must be idempotent.

Natural keys:

- `catalog_movies.letterboxd_url`
- `catalog_movies.tmdb_id` when available
- `canonical_movie_links.movie_id`

### Referential Integrity

Recommended constraints:

```text
canonical_movie_links.movie_id -> movies.id
canonical_movie_links.catalog_movie_id -> catalog_movies.id
account_movies.catalog_movie_id -> catalog_movies.id
watch_events.catalog_movie_id -> catalog_movies.id
reviews.catalog_movie_id -> catalog_movies.id
```

Use `ON DELETE RESTRICT` for catalog movie deletes by default.

Avoid accidental cascades that erase personal history.

### Rollback Considerations

Because the migration is additive:

- Existing Phase 1 commands can continue to work if catalog tables are ignored.
- Rollback can drop new catalog/personal tables without corrupting `movies`.
- Backfilled catalog rows can be regenerated.

Do not remove columns from `movies` in the same migration that introduces catalog tables.

### Expected Repository Changes

Initial changes:

- Add `CatalogMovieRepository`.
- Add `CanonicalMovieLinkRepository`.
- Add `PersonalLibraryRepository`.

Avoid:

- Expanding `DatabaseRepository` into a god object.
- Moving existing canonical reads immediately.

Later changes:

- Metadata sync writes to catalog.
- Availability sync writes to catalog.
- Search can choose canonical scope or personal scope through application use cases.

### Compatibility With Existing CLI Commands

Existing commands should remain unchanged:

- `moviekit sync`
- `moviekit search`
- `moviekit tonight`
- `moviekit sync metadata`
- `moviekit sync availability`

They should continue to operate against `movies` until explicitly migrated.

New personal commands should be separate and explicit.

## 7. Complexity Analysis

| Dimension | Parallel Personal Library | Hybrid Catalog |
| --------- | ------------------------- | -------------- |
| Development complexity | Low initially | Medium initially |
| Migration risk | Low initially | Medium, but additive if staged |
| Long-term maintenance | High | Medium to low |
| Query simplicity | Simple for isolated canonical or personal queries; harder for combined queries | Clearer for combined queries once adopted |
| AI friendliness | Medium to low because movie identity is split | High because movie identity is stable |
| MCP friendliness | Medium to low because tools expose competing IDs | High because resources can use catalog IDs |
| SQLite performance | Good for small/medium use; duplicated joins later | Good with indexes; fewer duplicate entities |
| Future extensibility | Limited by duplicated metadata | Strong for multi-account, recommendations, analytics |
| Phase 1 safety | Very high | High if additive and canonical commands remain on `movies` |
| Metadata consistency | Weak | Stronger with catalog as authority |
| Implementation speed | Fastest | Slower |
| Refactor pressure later | High | Lower |

## 8. Recommendation

Use a phased approach where Sprint 6 starts with the simpler design and migrates to a catalog later.

This is not a rejection of `catalog_movies`. It is a sequencing decision.

The long-term architecture should be catalog-based, but the current MovieKit codebase is still centered on `movies`. Sprint 6 should avoid turning a personal-library feature into a broad metadata identity migration.

Recommended Sprint 6 boundary:

1. Keep `movies` canonical-only.
2. Add account-owned personal-library tables.
3. Do not migrate existing metadata/availability services yet.
4. Design personal tables so they can later point to `catalog_movies`.
5. Add source URIs and stable keys from day one.
6. Keep personal sync separate from Phase 1 sync.

Recommended immediate schema shape:

```text
external_accounts
personal_movies
personal_watches
personal_ratings
personal_reviews
personal_likes
sync_runs
```

But with these constraints:

- `personal_movies` is transitional.
- It must use Letterboxd URL/URI as stable identity.
- It must not be treated as authoritative global movie metadata.
- It should be easy to backfill into `catalog_movies`.

Recommended next architectural checkpoint:

Before implementing metadata or availability enrichment for personal movies, revisit `catalog_movies`. That is the point where shared identity becomes worth the extra complexity.

Final recommendation:

```text
Use a phased approach where Sprint 6 starts with the simpler design and migrates to a catalog later.
```

## Delivery Notes

Files inspected:

- `docs/ARCHITECTURE.md`
- `docs/PERSONAL_LIBRARY_ARCHITECTURE_REVIEW.md`
- `src/moviekit/database.py`
- `src/moviekit/database_repository.py`

Files created:

- `docs/METADATA_OWNERSHIP_DECISION.md`

Files modified:

- `docs/METADATA_OWNERSHIP_DECISION.md`

Validation performed:

- Documentation readback only.
- No tests run because no implementation code was changed.

Git status at creation time:

```text
## main...origin/main [ahead 3]
 M movies.db
?? MovieKit.code-workspace
?? docs/METADATA_OWNERSHIP_DECISION.md
?? docs/PERSONAL_LIBRARY_ARCHITECTURE_REVIEW.md
```

Confirmation:

- No implementation was started.
- No commit occurred.
- No push occurred.
