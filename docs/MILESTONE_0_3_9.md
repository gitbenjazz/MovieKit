# Milestone 0.3.9

Milestone 0.3.9 completes the first bulk synchronization surface for MovieKit.

## Goals

- Keep synchronization orchestration in reusable services.
- Expose bulk metadata synchronization through the CLI.
- Expose bulk availability synchronization through the CLI.
- Add a single command that runs all supported bulk synchronization steps in order.
- Keep provider, metadata, and repository logic out of CLI command functions.

## Delivered

- `BulkSyncService` coordinates library-wide metadata and availability synchronization.
- `moviekit sync metadata` syncs TMDb metadata for all local movies.
- `moviekit sync availability` syncs streaming availability for all local movies.
- `moviekit sync all` runs metadata synchronization followed by availability synchronization.
- Bulk commands print concise processed, updated, skipped, and failed summaries.
- CLI tests mock service calls so no real TMDb requests are made.

## Verification

Run:

```bash
python3 -m compileall -q src/moviekit tests
python3 -m unittest discover
.venv/bin/python -m unittest discover
```

## Known Follow-Ups

- Add progress reporting for long-running library syncs.
- Add retry and rate-limit handling for provider and metadata backends.
- Add incremental synchronization once stored freshness metadata exists.
- Add scheduling or background execution only after the command behavior is stable.
