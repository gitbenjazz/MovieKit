from __future__ import annotations

from dataclasses import dataclass

from .database_repository import DatabaseRepository, MovieDetails


@dataclass(frozen=True)
class Recommendation:
    movie: MovieDetails
    score: int
    reasons: list[str]


class RecommendationEngine:
    def __init__(self, database_repository: DatabaseRepository):
        self.database_repository = database_repository

    def recommend_tonight(self) -> Recommendation | None:
        movies = self.database_repository.get_random_unwatched(limit=1)
        if not movies:
            return None

        movie = self.database_repository.get_movie_details(movies[0].id)
        if movie is None:
            return None

        score, reasons = self._score_movie(movie)

        return Recommendation(
            movie=movie,
            score=score,
            reasons=reasons,
        )

    def _score_movie(self, movie: MovieDetails) -> tuple[int, list[str]]:
        return 0, ["Random unwatched movie"]
