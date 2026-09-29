"""Explainable preference evidence, derived only from imported personal activity."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PreferenceEvidence:
    movies: int
    rated: int
    average_rating: float | None
    liked: int
    rewatched: int
    watched: int
    affinity: float

    def describe(self):
        rating = f"{self.average_rating:.2f}/5 across {self.rated} rated" if self.rated else "no ratings"
        return f"{rating}, {self.liked} liked, {self.rewatched} rewatched, {self.watched} watched"


class PersonalPreferenceProfile:
    def __init__(self, snapshot=None):
        self.username = snapshot.username if snapshot else None
        self.features = {}
        self.watched_canonical_ids = set()
        if snapshot is None:
            return
        watched = {w.movie_id for w in snapshot.watches}
        logged = Counter(w.movie_id for w in snapshot.watches if w.source != "letterboxd_watched")
        rewatched = {w.movie_id for w in snapshot.watches if w.is_rewatch} | {m for m, n in logged.items() if n > 1}
        movies = {m.id: m for m in snapshot.movies}
        ratings = {m.id: m.rating for m in snapshot.movies if m.rating is not None
                   and math.isfinite(m.rating) and 0.5 <= m.rating <= 5
                   and m.rating * 2 == int(m.rating * 2)}
        baseline = sum(ratings.values()) / len(ratings) if ratings else 3.0
        groups = defaultdict(set)
        for movie in snapshot.movies:
            if movie.id in watched and movie.canonical_id is not None:
                self.watched_canonical_ids.add(movie.canonical_id)
            if movie.year is not None and 1 <= movie.year <= 9999:
                groups[("decade", str(movie.year // 10 * 10))].add(movie.id)
        for kind, pairs in (("genre", snapshot.genres), ("director", snapshot.directors)):
            for movie_id, name in pairs:
                if name.strip() and name.strip().lower() != "unknown":
                    groups[(kind, name.casefold())].add(movie_id)
        for key, ids in groups.items():
            ids = {i for i in ids if i in watched or i in ratings or movies[i].liked}
            if not ids:
                continue
            scores = [ratings[i] for i in ids if i in ratings]
            liked = sum(movies[i].liked for i in ids)
            repeats = len(ids & rewatched)
            seen = len(ids & watched)
            # Shrink toward neutral with five virtual neutral films. Rewatches are capped per film.
            signal = sum((r - baseline) / 2 for r in scores) + .5 * liked + .25 * repeats + .05 * seen
            self.features[key] = PreferenceEvidence(len(ids), len(scores),
                sum(scores) / len(scores) if scores else None, liked, repeats, seen,
                signal / (len(ids) + 5))

    def score(self, movie):
        reasons = []
        score = 0.0
        groups = [
            ("director", sorted({c.name for c in movie.credits if c.role.lower() == "director"}), 3.0),
            ("genre", sorted(set(movie.genres)), 2.0),
            ("decade", [str(movie.year // 10 * 10)] if movie.year is not None else [], 1.0),
        ]
        for kind, labels, weight in groups:
            evidence = [(label, self.features[(kind, label.casefold())]) for label in labels
                        if (kind, label.casefold()) in self.features]
            if not evidence:
                continue
            contribution = 100 * weight * sum(e.affinity for _, e in evidence) / len(evidence)
            score += contribution
            descriptions = "; ".join(f"{label}{'s' if kind == 'decade' else ''}: {e.describe()}"
                                     for label, e in evidence)
            reasons.append(f"{kind.capitalize()} {contribution:+.2f}: {descriptions}")
        if not reasons:
            reasons.append("No supported personal preference signal; neutral score")
        elif not movie.genres and not any(c.role.lower() == "director" for c in movie.credits):
            reasons.append("Era signal only: genre/director metadata unavailable")
        return round(score, 6), reasons
