# Personal Library Architecture Review

This review evaluates the proposed Sprint 6 Personal Library architecture before implementation.

The proposal under review is:

- Keep `movies` as the canonical 1001 Movies table.
- Add parallel personal-library tables such as `personal_movies`, `personal_watches`, `personal_ratings`, `personal_reviews`, `personal_diary_entries`, and `personal_likes`.
- Link personal movies to canonical movies through a nullable `canonical_movie_id`.

## Executive Summary

The proposal protects the Phase 1 invariant that `movies` contains exactly the canonical 1524 movies from `movies.csv`. That is good.

However, the proposed table design is too event-specific too early. It risks duplicating movie metadata, splitting Letterboxd activity across too many tables, and making future analytics/AI querying harder than necessary.

The better design is a hybrid:

- Keep `movies` canonical-only for Phase 1 compatibility.
- Add a shared movie identity/catalog table for every known movie.
- Represent canonical membership and personal ownership/activity separately.
- Store watches, diary entries, reviews, ratings, and likes as normalized user activity linked to that shared identity.

This preserves Phase 1 while avoiding a parallel universe where canonical movies and personal movies duplicate the same real-world movie metadata.

## Table-by-Table Review of the Original Proposal

### `personal_accounts`

Recommended, but it should be generalized as `accounts` or `letterboxd_accounts`.

Strengths:

- Supports multiple Letterboxd accounts.
- Gives sync jobs a clear ownership boundary.
- Avoids assuming the local user is the only source forever.

Risks:

- If named too broadly as `personal_accounts`, future non-Letterboxd sources may blur semantics.
- If named too narrowly as `letterboxd_accounts`, future imported data from IMDb, TMDb lists, or local files may require parallel account/source tables.

Recommendation:

- Use `accounts` plus a `source` column, or `external_accounts`.
- Enforce uniqueness on `(source, username)`.

### `personal_movies`

This is the weakest part of the original proposal.

Strengths:

- Protects canonical `movies`.
- Allows non-1001 movies to exist.
- Easy to implement incrementally.

Weaknesses:

- Duplicates metadata already present in `movies`: title, year, Letterboxd URL, TMDb ID.
- Creates two identities for the same real-world movie: one canonical row and one personal row.
- Requires every query to decide whether to use `movies`, `personal_movies`, or both.
- Makes metadata enrichment ambiguous: should TMDb metadata update `movies`, `personal_movies`, or both?

Recommendation:

- Do not make `personal_movies` the movie metadata owner.
- Introduce a shared movie identity table instead.

Better model:

```text
catalog_movies
    id
    title
    year
    letterboxd_url
    letterboxd_slug
    tmdb_id
    tmdb_title
    runtime
    created_at
    updated_at

canonical_movies
    catalog_movie_id
    legacy_movie_id
    source_list_id
    position

account_movies
    account_id
    catalog_movie_id
    first_seen_at
    last_activity_at
```

In this model, `movies` can remain untouched during the transition, while `catalog_movies` becomes the long-term identity table.

### `personal_watches`

Recommended conceptually, but it overlaps with diary entries.

Letterboxd watched history and diary history are related but not identical:

- A watched export can represent a watch event.
- A diary entry is also often a watch event with richer fields.
- A film can be watched without a diary entry.
- A diary entry can contain review text, tags, rating, and rewatch metadata.

Risk:

- Separate `personal_watches` and `personal_diary_entries` can duplicate the same watch event if both exports are imported.

Recommendation:

- Create one canonical activity/event table for watch events.
- Let diary-specific data extend that event.

Better model:

```text
watch_events
    id
    account_id
    catalog_movie_id
    watched_date
    source_uri
    source
    is_rewatch
    created_at
    updated_at

diary_entries
    id
    watch_event_id nullable
    account_id
    catalog_movie_id
    diary_uri
    review_text
    rating
    tags
    entry_date
```

This avoids duplicate watch rows while preserving diary detail.

### `personal_ratings`

Useful, but ratings also appear in reviews and diary entries.

Weakness:

- If `personal_ratings.rating`, `personal_reviews.rating`, and `personal_diary_entries.rating` all exist independently, inconsistencies are likely.

Recommendation:

- Store current account-level rating in `account_movie_ratings`.
- Store historical rating attached to an activity entry when the rating came from a diary/review.

Better model:

```text
account_movie_ratings
    account_id
    catalog_movie_id
    rating
    rated_at
    updated_at

activity_ratings
    activity_id
    rating
```

The current rating answers "what is my latest rating for this movie?" Activity ratings answer "what rating was attached to this review/diary entry?"

### `personal_reviews`

Potentially redundant with diary entries.

Letterboxd reviews are frequently attached to diary entries. A separate review table can be correct, but only if it models review identity independently from watches.

Risk:

- Duplicates `review_text`, `rating`, and `watched_date` with diary entries.

Recommendation:

- Use `reviews` as a content table linked to an activity/event.
- Keep one review body per source URI.

Better model:

```text
reviews
    id
    account_id
    catalog_movie_id
    activity_id nullable
    review_uri unique
    review_text
    created_at
    updated_at
```

### `personal_diary_entries`

Recommended, but not as a standalone owner of ratings/reviews/watches.

Weakness:

- A diary entry is a composite concept: watch event, optional rating, optional review, optional tags.
- Treating it as the main owner can duplicate data stored elsewhere.

Recommendation:

- Model diary entries as source-specific activity records, then normalize optional content out where useful.

### `personal_likes`

Needs a clearer target model.

Likes can apply to films, reviews, lists, or other Letterboxd objects depending on export/source capability.

Weakness:

- A simple `personal_likes(personal_movie_id, liked_at)` only supports film likes.
- A generic `target_type`, `target_uri` model is flexible but weakly relational.

Recommendation:

- For Sprint 6, support film likes explicitly.
- Defer review/list likes until the import source requires them.

Better Sprint 6 table:

```text
account_movie_likes
    account_id
    catalog_movie_id
    liked_at
    source_uri
```

Future generic likes can be added later if needed.

## Normalization Review

The original proposal duplicates movie metadata in both `movies` and `personal_movies`.

Duplicated fields include:

- title
- year
- Letterboxd URL
- TMDb ID
- runtime
- genre/director data if later added to personal rows

This can cause inconsistencies:

- Canonical row has `tmdb_id = 348`, personal row has no TMDb ID.
- Canonical row title is lowercase from `movies.csv`, personal row title is title-cased from Letterboxd.
- Personal row has newer metadata than canonical row.
- Availability exists for canonical movie but not personal duplicate.

Better ownership model:

- Movie identity and public metadata belong to a shared catalog movie.
- Canonical 1001 membership belongs to a canonical/list membership table.
- Account-specific facts belong to account/activity tables.

This is the core revision I would make before implementation.

## Architecture Alternatives

### Alternative A: Parallel Personal Library

This was the original proposal.

Advantages:

- Lowest risk to Phase 1.
- Easy to explain.
- Additive schema.
- Minimal immediate migration pressure.

Disadvantages:

- Creates duplicate movie identity.
- Requires linking logic forever.
- Makes cross-library search and recommendations more complex.
- Makes metadata enrichment ambiguous.
- Harder for AI/MCP tools to query cleanly.

Verdict:

- Acceptable as a short-lived bridge.
- Not ideal as the long-term architecture.

### Alternative B: Shared Global Movie Catalog

Use one `catalog_movies` table for all known movies. Canonical 1001 and personal library become memberships.

Advantages:

- Best normalization.
- One identity per real-world movie.
- Easier metadata enrichment.
- Easier search across all known movies.
- Better for AI/LLM querying and analytics.

Disadvantages:

- More migration complexity.
- Requires careful compatibility with existing `movies`.
- Existing code assumes `movies` is central.

Verdict:

- Best long-term model.
- Needs phased adoption to avoid destabilizing Phase 1.

### Alternative C: Hybrid Transitional Model

Keep `movies` canonical-only now, but add `catalog_movies` and link canonical rows into it.

Advantages:

- Preserves Phase 1 invariant.
- Avoids personal/canonical metadata duplication.
- Enables future personal library at scale.
- Allows gradual refactoring of recommendations/search.

Disadvantages:

- Slightly more schema work up front.
- Requires sync code to maintain `movies <-> catalog_movies` mapping.
- Developers must understand two movie identifiers during the transition.

Verdict:

- Best choice for Sprint 6.

## Recommended Revised Data Model

### Identity and Sources

```text
external_accounts
    id
    source
    username
    display_name
    profile_url
    created_at
    updated_at
    unique(source, username)

catalog_movies
    id
    title
    year
    letterboxd_url
    letterboxd_uri
    letterboxd_slug
    tmdb_id
    tmdb_title
    runtime
    created_at
    updated_at
    unique(letterboxd_url)
    unique(tmdb_id)
```

### Canonical Bridge

```text
canonical_movie_links
    movie_id
    catalog_movie_id
    created_at
    primary key(movie_id)
    unique(catalog_movie_id)
```

This keeps existing `movies` unchanged while allowing a shared catalog identity.

### Account Membership

```text
account_movies
    account_id
    catalog_movie_id
    first_imported_at
    last_seen_at
    primary key(account_id, catalog_movie_id)
```

This answers "is this movie in this user's personal library?"

### Activity and User Data

```text
watch_events
    id
    account_id
    catalog_movie_id
    watched_date
    source_uri
    source_import_id
    is_rewatch
    created_at
    updated_at
    unique(account_id, source_uri)

account_movie_ratings
    account_id
    catalog_movie_id
    rating
    rated_at
    updated_at
    primary key(account_id, catalog_movie_id)

diary_entries
    id
    account_id
    catalog_movie_id
    watch_event_id
    diary_uri
    entry_date
    rating
    review_text
    tags
    created_at
    updated_at
    unique(account_id, diary_uri)

reviews
    id
    account_id
    catalog_movie_id
    review_uri
    review_text
    rating
    reviewed_at
    created_at
    updated_at
    unique(account_id, review_uri)

account_movie_likes
    account_id
    catalog_movie_id
    liked_at
    source_uri
    primary key(account_id, catalog_movie_id)
```

Depending on the actual Letterboxd export format, `reviews` and `diary_entries` may be merged initially. Do not create both unless the source data distinguishes them clearly.

## Long-Term Scalability

### 100,000+ Personal Movies

SQLite can handle this easily if indexes are correct.

Key concerns:

- Avoid full scans for account-specific views.
- Use composite indexes on `(account_id, catalog_movie_id)`.
- Keep text-heavy review bodies out of hot list queries.
- Consider FTS5 for title/review search later.

Required indexes:

```text
catalog_movies(letterboxd_url)
catalog_movies(tmdb_id)
catalog_movies(title, year)
account_movies(account_id, catalog_movie_id)
watch_events(account_id, watched_date)
watch_events(catalog_movie_id)
diary_entries(account_id, entry_date)
account_movie_ratings(account_id, rating)
account_movie_likes(account_id, catalog_movie_id)
canonical_movie_links(movie_id)
canonical_movie_links(catalog_movie_id)
```

### Multiple Letterboxd Accounts

The original proposal supports multiple accounts if every table includes `account_id`. That must be non-negotiable.

Weakness to avoid:

- A single global `personal_movies` table without account membership cannot represent two users having different ratings, likes, or watch histories for the same movie.

Recommendation:

- Use `external_accounts`.
- Use account-scoped activity tables.
- Use `catalog_movies` for shared identity.

### Future AI Features

AI features will need clean concepts:

- movie identity
- canonical membership
- account activity
- ratings/reviews text
- providers
- recommendation context

The parallel proposal makes prompts and tool schemas messier because the AI must understand `movies` vs `personal_movies`.

The hybrid catalog model is better because it can expose:

```text
Movie
CanonicalMembership
AccountMovie
WatchEvent
Review
Availability
```

These map naturally to MCP resources and local LLM retrieval.

### Future MCP Integration

MCP tools benefit from stable, simple resource IDs.

Recommended resource identity:

- `catalog_movie_id` for global movie resources.
- `account_id` plus `catalog_movie_id` for account-specific state.
- `movie_id` only for legacy canonical 1001 operations.

Avoid exposing both `movies.id` and `personal_movies.id` as competing movie IDs.

### Local LLM Querying

Local LLM querying will benefit from:

- normalized entities,
- FTS indexes for reviews/diary text,
- precomputed summary tables or views,
- stable source URIs for provenance.

Possible future views:

```text
v_account_movie_profile
v_canonical_progress
v_recent_activity
v_review_corpus
v_recommendation_features
```

### Future Recommendation Engine

Recommendation scoring will want:

- unwatched canonical movies,
- personal ratings,
- favorite genres/directors,
- provider preferences,
- recency,
- review sentiment,
- disliked patterns.

This is much easier if account data is normalized and linked to a shared catalog.

### Statistics and Analytics

Analytics will need efficient grouping by:

- account,
- year,
- rating,
- watched date,
- canonical membership,
- genre,
- director,
- provider.

The hybrid catalog model supports this without duplicating metadata joins.

## Repository Boundary Review

Do not extend `DatabaseRepository` until it becomes a god object.

Current `DatabaseRepository` already owns:

- canonical movie writes,
- watched import,
- search,
- details,
- random unwatched,
- provider bridge helpers.

Adding all personal sync behavior there would make it too large.

Recommended repositories:

```text
CanonicalMovieRepository
    eventually split from current DatabaseRepository

CatalogMovieRepository
    owns catalog identity and public metadata

PersonalLibraryRepository
    owns account membership, ratings, watches, diary, reviews, likes

CanonicalLinkRepository
    owns linking between movies and catalog_movies
```

This does not need to happen all at once. For Sprint 6, at minimum introduce `PersonalLibraryRepository` and avoid stuffing personal behavior into `DatabaseRepository`.

Recommended services:

```text
PersonalLibrarySyncService
    orchestrates import batches

CanonicalMovieLinker
    links catalog movies to canonical movies

LetterboxdExportParser
    parses CSV/export files into domain records

PersonalLibraryImportPlanner
    computes insert/update/delete decisions
```

Application use cases should orchestrate these services, keeping CLI and future MCP entrypoints thin.

## Synchronization Review

### Idempotency

Every import must be idempotent.

Recommended natural keys:

- accounts: `(source, username)`
- catalog movies: `letterboxd_url`, fallback `tmdb_id`
- account movie membership: `(account_id, catalog_movie_id)`
- watch events: `(account_id, source_uri)` if present
- diary entries: `(account_id, diary_uri)`
- reviews: `(account_id, review_uri)`
- ratings: `(account_id, catalog_movie_id)`
- likes: `(account_id, catalog_movie_id)` for film likes

### Duplicate Prevention

The design needs source URI handling from day one.

Letterboxd short URLs such as `boxd.it/...` should be stored, but canonical URLs should be resolved when possible.

Do not rely on title/year as the primary key for personal sync.

### Conflict Resolution

Conflicts will happen:

- title changed on Letterboxd,
- year changed,
- TMDb ID improved,
- review edited,
- rating changed,
- diary entry deleted remotely,
- duplicate imports from different export files.

Recommended policy:

- Source-of-truth fields from Letterboxd can update on import.
- User activity records should be upserted by source URI.
- Missing rows in a partial export should not be deleted.
- Deletions require a full sync marker or explicit reconciliation step.

### Re-Linking After Metadata Improvements

Canonical links should be recomputable.

Do not make `canonical_movie_id` a one-time decision that never changes.

Recommended:

- Store link confidence and method.
- Allow relinking when stronger evidence appears.

Example:

```text
catalog_canonical_links
    catalog_movie_id
    movie_id
    match_method
    confidence
    linked_at
```

### Future Incremental Syncs

Add sync bookkeeping early.

Recommended table:

```text
sync_runs
    id
    account_id
    source
    sync_type
    started_at
    finished_at
    status
    records_seen
    records_inserted
    records_updated
    records_skipped
    error_message
```

This will help both CLI output and future MCP/local LLM diagnostics.

## SQLite Performance Review

SQLite is appropriate for this scope, including 100,000+ movies and hundreds of thousands of activity rows.

Important practices:

- Use transactions for each high-level import.
- Enable `PRAGMA foreign_keys = ON`.
- Add composite indexes for account-scoped queries.
- Avoid cascading deletes from `catalog_movies` unless intentional.
- Use FTS5 later for review/diary text.
- Keep migrations explicit; compatibility-drop guards are not enough for v3+.

Migration complexity is the main risk.

The current schema uses `CREATE TABLE IF NOT EXISTS` and compatibility guards. Personal Library should introduce a real migration path before adding many tables. Otherwise future schema changes will become brittle.

## Weaknesses and Risks in the Original Proposal

- It duplicates movie metadata between `movies` and `personal_movies`.
- It creates competing movie identities.
- It makes metadata enrichment ownership ambiguous.
- It can duplicate watches between `personal_watches` and `personal_diary_entries`.
- It can duplicate ratings across ratings, reviews, and diary entries.
- It under-specifies multiple-account uniqueness.
- It does not define sync run tracking.
- It does not define deletion/reconciliation semantics.
- It does not define link confidence or relinking strategy.
- It may make AI/MCP resource models more confusing.
- It may make future recommendation features join-heavy and error-prone.
- It risks turning `DatabaseRepository` into a god object.

## Recommended Changes Before Implementation

1. Replace `personal_movies` as metadata owner with `catalog_movies`.
2. Keep existing `movies` canonical-only and introduce a bridge from `movies` to `catalog_movies`.
3. Add `external_accounts` or `accounts` before any account-scoped activity table.
4. Add `account_movies` as membership, not metadata.
5. Normalize watch/diary/review/rating ownership to avoid duplicate facts.
6. Add sync run tracking before bulk personal sync.
7. Add link confidence/method for canonical matching.
8. Define indexes before implementation.
9. Introduce `PersonalLibraryRepository` rather than expanding `DatabaseRepository`.
10. Plan an explicit Schema v3 migration instead of continuing with compatibility guards only.

## Final Recommendation

Use the hybrid model.

Do not implement the original parallel `personal_movies` design as the long-term foundation. It is safe but too duplicative.

The revised architecture should be:

```text
movies
    canonical 1001 rows only

catalog_movies
    all known movie identities

canonical_movie_links
    bridge from canonical rows to catalog identities

external_accounts
    Letterboxd account identities

account_movies
    personal library membership

watch_events / diary_entries / reviews / ratings / likes
    account-scoped activity and preference data
```

This protects Phase 1 and gives Sprint 6 a scalable base for personal library sync, AI features, MCP integration, analytics, and future recommendations.

## Conclusion

Approved with recommended revisions
