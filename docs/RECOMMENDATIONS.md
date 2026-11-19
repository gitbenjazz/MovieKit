# Personalized recommendations

`moviekit recommend [--username USER] [--from-year YEAR] [--to-year YEAR]`
returns up to ten unwatched canonical films on Prime Video US. No personal
movies are inserted into the canonical table. Existing Phase 1 watched rows
and the selected account's linked personal watches both exclude candidates.
An explicit unknown username or ambiguous account selection exits with code 2.
No accounts means a neutral ranking; exactly one is selected automatically.

## Evidence and scoring

The read-only analytics repository supplies the selected account's current
ratings, likes, watch events, release years, and linked canonical metadata.
The preference profile groups engaged films by genre, director, and decade.
For each group of N distinct watched, rated, or liked films:

```
signal = sum((rating - account_mean_rating) / 2)
         + 0.50 * liked_films + 0.25 * rewatched_films + 0.05 * watched_films
affinity = signal / (N + 5)
score = 100 * (3 * director_affinity + 2 * genre_affinity + decade_affinity)
```

Only valid half-star ratings from 0.5 to 5 contribute. Five neutral pseudo-films
reduce the influence of small samples. A rewatch is an explicit marker or
multiple diary/review events, excluding the synthetic watched-list marker.
Rewatch evidence is capped at one contribution per film. Each dimension averages
its supported features, so extra genres or directors do not multiply its weight.
Unknown features contribute zero, without inferring tastes from titles, reviews,
or public popularity. Scores are relative affinities, not predicted star ratings
or probabilities; negative scores are possible.

Each result reports signed contributions and the underlying mean rating,
rated count, likes, rewatches, and watches. Era-only evidence is labeled when
candidate genre/director metadata is absent. Equal scores sort by title,
release year, and canonical ID, independently of CSV order.

## Boundaries and limitations

The application/service selects the account and applies inclusive year filters
before the engine ranks candidates. The engine ranks the complete candidate
set before the service checks live availability and takes the first ten eligible
results. The CLI renders structured scores and reasons; repositories own SQL.

Availability uses TMDb's US flatrate provider data for Amazon Prime Video
(including the with-ads plan). Rentals, purchases, add-on channels, and other
countries do not qualify. Stored TMDb IDs are preferred; otherwise a unique
exact normalized title/year search match is required. Ambiguous or unmatched
films are skipped, so translated titles may need metadata correction. Network
or authentication failures return an error, rather than claiming no availability.
TMDb listings can lag the actual Prime catalog. Requests require network access
and `TMDB_API_KEY`; this workflow does not write fetched metadata to the database.

Missing genre/director metadata produces coarse decade preferences and many
ties. Imported non-canonical films still inform decades, but have no canonical
genre/director metadata. Additive personal imports can retain old watches; export
freshness and canonical link coverage determine watched exclusion accuracy.
Phase 1 exclusions remain shared across accounts for compatibility. No account's
personal preference evidence is mixed with another's. The separate `tonight`
command is unchanged.
