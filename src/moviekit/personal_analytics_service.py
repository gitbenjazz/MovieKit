"""Account analytics. Personal ratings/likes are never inferred from public scores."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import math

from .personal_analytics_models import PersonalStats, PreferenceStats
from .personal_analytics_repository import PersonalAnalyticsRepository


class PersonalAnalyticsService:
    def __init__(self, repository=None):
        self.repository = repository or PersonalAnalyticsRepository()

    def stats(self, username: str) -> PersonalStats | None:
        snapshot = self.repository.snapshot(username.strip().lower())
        if snapshot is None:
            return None
        movies = {movie.id: movie for movie in snapshot.movies}
        watched = {watch.movie_id for watch in snapshot.watches}
        valid_ratings = {m.id: m.rating for m in snapshot.movies
                         if m.rating is not None and math.isfinite(m.rating)
                         and 0.5 <= m.rating <= 5 and m.rating * 2 == int(m.rating * 2)}
        invalid_ratings = sum(m.rating is not None for m in snapshot.movies) - len(valid_ratings)
        distribution = Counter(valid_ratings.values())
        activity = Counter()
        undated = 0
        logged = Counter()
        for watch in snapshot.watches:
            if watch.source != "letterboxd_watched":
                logged[watch.movie_id] += 1
            try:
                year = date.fromisoformat(watch.watched_date or "").year
            except ValueError:
                undated += 1
            else:
                activity[year] += 1
        decades = Counter(m.year // 10 * 10 for m in snapshot.movies
                          if m.year is not None and 1 <= m.year <= 9999)
        genres = self._preferences(snapshot.genres, movies, watched, valid_ratings)
        directors = self._preferences(snapshot.directors, movies, watched, valid_ratings)
        return PersonalStats(
            username=snapshot.username, movies=len(movies), watched=len(watched),
            rated=len(valid_ratings), liked=sum(m.liked for m in snapshot.movies),
            average_rating=self._average(list(valid_ratings.values())),
            rating_distribution=tuple((n / 2, distribution[n / 2]) for n in range(1, 11)),
            invalid_ratings=invalid_ratings, watch_events=len(snapshot.watches),
            activity_by_year=tuple(sorted(activity.items())), undated_events=undated,
            decades=tuple(sorted(decades.items())), unknown_release_year=len(movies) - sum(decades.values()),
            rewatch_events=sum(w.is_rewatch for w in snapshot.watches),
            rewatched_movies=len({w.movie_id for w in snapshot.watches if w.is_rewatch}),
            multiple_logged_watches=sum(count > 1 for count in logged.values()),
            genres=genres, directors=directors,
            genre_coverage=len({m for m, _ in snapshot.genres}),
            director_coverage=len({m for m, _ in snapshot.directors}),
            canonical_watched=len({m.canonical_id for m in snapshot.movies
                                   if m.id in watched and m.canonical_id is not None}),
            canonical_total=snapshot.canonical_total,
        )

    @classmethod
    def _preferences(cls, pairs, movies, watched, ratings):
        groups = defaultdict(set)
        for movie_id, name in pairs:
            groups[name].add(movie_id)
        result = []
        for name, ids in sorted(groups.items()):
            scores = [ratings[movie_id] for movie_id in ids if movie_id in ratings]
            result.append(PreferenceStats(name, len(ids), len(ids & watched), len(scores),
                sum(movies[movie_id].liked for movie_id in ids), cls._average(scores)))
        return tuple(result)

    @staticmethod
    def _average(values):
        return sum(values) / len(values) if values else None

    @staticmethod
    def highest_rated(groups, limit=5):
        return sorted((g for g in groups if g.average_rating is not None),
                      key=lambda g: (-g.average_rating, -g.rated, g.name.casefold()))[:limit]

    @staticmethod
    def favorites(groups, limit=5):
        return sorted((g for g in groups if g.liked),
                      key=lambda g: (-g.liked, -g.watched, g.name.casefold()))[:limit]
