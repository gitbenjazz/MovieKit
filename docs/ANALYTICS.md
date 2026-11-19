# Personal Analytics

MovieKit computes analytics from the local Personal Library.  The commands are
read-only: they do not contact Letterboxd, TMDb, or alter `movies.db`.

```bash
moviekit analytics summary --username your-letterboxd-username
moviekit analytics taste --username your-letterboxd-username
moviekit analytics collections --username your-letterboxd-username
moviekit analytics profile --username your-letterboxd-username --format json
```

Import or refresh the Personal Library first with `moviekit personal sync`.
Metadata coverage in the output reflects the metadata already available in the
local database; it does not infer missing genres or directors.
When a verified universal identity has actor credits, actor statistics and
actor taste groups are reported separately from directors.

## Definitions

- **Unique watched films** are distinct Personal Library movies with at least
  one watch event.  **Viewing events** count every recorded event.
- An **explicit rewatch** is a watch event marked as a rewatch by the imported
  Letterboxd data.  Repeated diary events are reported separately and are not
  silently treated as explicit rewatches.
- Viewing activity uses valid watch dates.  Missing or invalid dates are kept
  in the undated count rather than assigned to a year.
- Release-decade totals in `analytics summary` include watched personal films
  with a known release year.  Unlinked personal films can contribute to this
  total, but cannot contribute canonical genres or directors.
- Ratings are only the account's imported Letterboxd ratings on the 0.5--5.0
  scale.  Public/TMDb ratings are never used as personal preference evidence.
- Likes are reported as a separate favorite signal; MovieKit does not combine
  likes and ratings into an opaque score.
- Taste groups show only groups with at least three rated films.  Three to nine
  ratings are labelled `limited`; ten or more are `supported`.  Smaller groups
  remain in the JSON profile as `insufficient` evidence.

## Collection progress

`letterboxd-1001` represents the canonical collection currently loaded in
`movies`.  `1001-2013` is shown when its editorial CSV has been imported.

For every collection, MovieKit reports editorial entries, resolved identities,
watched and unwatched resolved films, and unresolved/ambiguous/grouped entries.
Coverage is resolved identities divided by editorial entries; progress is
watched resolved films divided by resolved identities.  A grouped editorial
entry is never marked complete from a single watched movie.

## JSON profile

`analytics profile --format json` emits the versioned schema
`moviekit.personal-profile.v1`.  It contains data coverage, viewing behavior,
rating and like evidence, collection progress, and explicit limitations.  It
contains no filesystem paths, API credentials, or external identifiers beyond
the requested username.

The profile is designed as a local, deterministic input for a future
assistant/MCP layer.  Consumers should honor its `evidence` labels and
`limitations`, rather than treating the data as a complete taste model.
