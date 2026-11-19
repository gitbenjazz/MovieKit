# Architecture

This document records the current database ownership decisions for MovieKit.

## Phase 1 Scope

Phase 1 manages only the canonical Letterboxd 1001 movie library.

The `movies` table represents the canonical library imported from `movies.csv`. It is not a general personal Letterboxd library table in Phase 1.

After a clean rebuild, the expected `movies` count is exactly **1524 movies**.

## Canonical Movie Import

`moviekit sync` is responsible for importing the canonical library and watched history.

During `moviekit sync`:

1. `movies.csv` is imported into the `movies` table.
2. `watched.csv` is imported into watched history.
3. Watched history is linked to existing canonical movie rows.
4. Watched history must never create additional rows in `movies`.

If a watched entry cannot be linked to an existing canonical movie, it is skipped and reported in the watched import summary.

## Enrichment Commands

Metadata and availability synchronization are enrichment steps only.

- Metadata synchronization may add TMDb IDs, TMDb titles, runtime, directors, and genres to existing movies.
- Availability synchronization may add provider availability for existing movies.
- Neither workflow may create new movies in Phase 1.

This applies to both single-movie and bulk synchronization commands.

## Personal Library

The Personal Library is additive and remains separate from Phase 1. Its
Letterboxd imports write account-scoped rows to `accounts`, `personal_movies`,
`watch_events`, `ratings`, `reviews`, and `likes`. Personal films outside the
canonical collection are never inserted into `movies`.

Optional TMDb-backed universal identities and normalized credits are linked to
canonical, personal, or editorial rows through additive foreign keys. A failed
or ambiguous identity is retained for audit and never silently merged. Personal
analytics and personalized recommendations use these links where available;
missing metadata does not invent a match or alter the canonical collection.
