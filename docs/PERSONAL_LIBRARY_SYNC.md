# Personal Library synchronization (Sprint 6)

Personal synchronization is additive and independent from Phase 1. It writes
`accounts`, `personal_movies`, `watch_events`, `ratings`, `reviews`, `likes`, and
`sync_runs`. It never imports personal films into canonical `movies`, modifies
Phase 1 `watched`, or changes recommendation behavior.

## Input and ownership

Use an extracted official Letterboxd export directory. Supported files:

- `watched.csv`: film identity and watched state; `Date` is not assumed to be a viewing date.
- `ratings.csv`: authoritative current film ratings (0.5–5 stars).
- `diary.csv`: dated watches, rewatches, and entry identity when available.
- `reviews.csv`: review text, review date, optional viewing date and historical review rating.
- `likes/films.csv`: film likes only.

Optional files may be absent. Missing required headers and invalid CSV encoding
fail parsing before writes. Invalid rows are skipped with filename, row number,
and an error; valid rows may still import. Only synthetic data is in tests.
The parser never accesses SQLite, TMDb, or Letterboxd over the network.

Sources: [Letterboxd export](https://letterboxd.com/user/exportdata/) and
[account export documentation](https://letterboxd.zendesk.com/hc/en-us/articles/15179196880911-Can-I-get-a-copy-of-my-account-data).
The local watched-export headers were also inspected during implementation.

## Identity and canonical links

Personal identity is account-scoped and uses Letterboxd URL/URI. User-entry
URLs expose a film slug; short URLs are retained without network resolution.
A unique normalized title/year can reconcile short film URLs and activity URLs.
Distinct known long film URLs are not merged by title. When a personal identity
cannot be reconciled uniquely, it stays separate rather than guessing.

Canonical linking is read-only: Letterboxd URL/slug and optional TMDb ID take
precedence over normalized title/year. Ambiguous canonical matches remain
unlinked. Canonical links are recomputed for imported films. No shared catalog
or schema redesign is introduced.

## Watches and idempotency

A watched-only film has an undated `letterboxd_watched` placeholder event.
Diary/review events supersede that placeholder. A review links to a diary event
when a reliable entry URI or unique compatible date makes the relationship
clear. Multiple rewatches are retained.

When the diary provides a film URI rather than a unique entry URI, the import
uses a deterministic internal event key based on personal movie ID, watched
date, and occurrence within that date. Identical reimports therefore do not
multiply events. Without a stable entry URI, changing a date cannot be identified
as an edit with certainty; it may create another event. No remote deletion is
inferred. Tags and historical diary-only ratings have no dedicated Schema v3
storage and are not imported; current ratings come from `ratings.csv`, while
review ratings remain on reviews.

## Transactions and reporting

One SQLite transaction covers all personal data changes and the successful
`sync_runs` record. Failures roll back imported data; a separate failed run is
recorded afterward when the database is writable. Parser failures occur before
this transaction and do not create a run. Other accounts remain isolated.

Reports distinguish imported movie identities, canonical match states, final
account activity totals, inserted/changed entities, and skipped rows. Run
insert/update counts exclude the account and sync-run bookkeeping and ignore
SQLite timestamps. The removal of superseded watched placeholders is not an
insert/update count.

Partial exports update supplied data and retain absent rows. Removing a rating,
like, review, or diary entry remotely does not delete it locally. Explicit
full-export deletion reconciliation is deferred. Personal sync does not replace
`moviekit sync` for refreshing the canonical recommendation workflow.
