# Universal Movie Identities

Schema v9 adds a verified TMDb identity layer without changing the canonical
meaning of `movies`.  Canonical movies remain the 1,524-film collection;
personal-only films are represented by `personal_movies` and are never copied
into `movies`.

`film_identities` is keyed by a verified TMDb movie ID.  `movies`,
`personal_movie_metadata`, and `collection_entries` can each reference the
same identity with an optional `identity_id`.  Source titles, years, and
Letterboxd identifiers remain on their original source rows.

Identity metadata is normalized in `identity_genres`, `identity_people`, and
`identity_credits`.  People are created only from a TMDb person ID, never by
matching a display name.  Director and actor credits are separate; actors use
TMDb cast billing order and enrichment retains at most the first ten credited
cast members.

## Resolution and enrichment

Use the existing personal workflow:

```bash
moviekit personal enrich --username your-letterboxd-username --dry-run --limit 50
moviekit personal enrich --username your-letterboxd-username --limit 50
moviekit personal enrich --username your-letterboxd-username --retry-failed --limit 10
moviekit personal identities --username your-letterboxd-username
moviekit personal unresolved --username your-letterboxd-username
```

Resolution first reuses a linked canonical TMDb ID.  Otherwise it accepts only
one TMDb search result whose normalized title (title or original title) and
release year exactly match the Letterboxd source.  Zero results are recorded as
`unmatched`; multiple results as `ambiguous`.  Neither case is merged
automatically.  A pending TMDb ID is saved before the metadata fetch, so a
retry avoids repeating a successful search after a later API failure.

Identity resolution and metadata completeness are tracked separately.  A
legacy `complete` resolution without a fetched universal identity remains
eligible for enrichment, while a verified identity with a successful metadata
fetch is cached.  Use
`--retry-unresolved` to retry unresolved states or `--refresh` to refetch a
completed record.  `--dry-run` does not persist resolution results or fetched
metadata (the application may still apply its required additive schema
migration before it runs).

Bounded `--refresh --limit 50` batches advance deterministically: refreshed
films receive a local refresh order and move behind films not refreshed in the
current cycle.  This avoids repeatedly fetching the alphabetically first
batch.

An API failure is retained with a category, message, timestamp, and attempt
count. It is skipped by ordinary batches so it cannot block later films; use
`--retry-failed` for an explicit retry. A malformed TMDb detail response is
recorded as a permanent metadata failure, while other TMDb/API failures remain
retryable.

The identity layer does not write personal ratings, likes, watches, reviews,
or canonical movie rows.  TMDb community ratings are not imported as personal
ratings.
