# Curated collections

MovieKit keeps the original Letterboxd collection in `movies`. It remains the
only owner of the 1,524 canonical movie rows and their existing foreign keys.
Curated editions are stored as separate editorial entries in `collections` and
`collection_entries`; importing an edition never creates canonical movies.

The 2013 source used during development is a transcription of the international
tenth edition, used as an approximation of the French Omnibus ninth revised
edition. The two editions are not asserted to be identical. Its redistribution
rights are not established, so MovieKit does not bundle it. Obtain a collection
CSV you are permitted to use and retain its provenance locally. Every imported
entry retains its source title, year, source URL, verification status, review
reason, and editorial number.

```bash
.venv/bin/moviekit collections import --source /path/to/1001_movies_2013.csv
.venv/bin/moviekit collections list
.venv/bin/moviekit collections show 1001-2013
.venv/bin/moviekit recommend --collection 1001-2013
.venv/bin/moviekit recommend --collection letterboxd-1001
.venv/bin/moviekit recommend --collection intersection
.venv/bin/moviekit recommend --collection all
```

The importer only links an entry to a canonical movie with a unique deterministic
TMDb ID or normalized title-and-year match. Entries with `needs_review`, empty
titles, editorial groups, ambiguous matches, and unmatched titles remain visible
in the audit data but are not recommendations. `all` and `intersection` operate
on those confirmed canonical links, so a film cannot occur twice. Current Prime
availability and recommendation metadata are reused only through that canonical
link.

The development source contained 1,001 editorial entries. Against the present
1,524-film canonical collection, it produced 782 canonical links; 780 were
eligible for recommendation. Six editorial groups, one empty title, and 212
unmatched entries were retained rather than guessed. Results depend on the
legally obtained source supplied by the user.
