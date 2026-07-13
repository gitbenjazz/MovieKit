# Changelog

All notable changes to MovieKit are documented here.

## v0.2.0

Released as Milestone 1.5.

### Added

- `moviekit search "<text>"` for local SQLite-backed movie search.
- Search filters for `--watched`, `--unwatched`, and `--limit`.
- Case-insensitive partial matching across title, TMDB title, TMDB ID, and Letterboxd URL.
- Highlighted search matches in CLI output.
- Normalized SQLite Schema v2 centered on `movies`.
- Repository query layer returning Python objects instead of SQL join rows.
- Regression tests for search behavior and canonical watched detection.

### Changed

- `watched` rows now point to canonical `movies.id` values where title/year matches exist.
- Duplicate watch-history entries are preserved.
- Search watched status now uses `watched.movie_id -> movies.id`.
- SQLite initialization handles incompatible legacy tables before creating Schema v2.

### Fixed

- Fixed `moviekit sync` failures caused by legacy v1 tables missing v2 columns.
- Fixed The Godfather Part II being reported as unwatched when watched history used a short `boxd.it` URL.

