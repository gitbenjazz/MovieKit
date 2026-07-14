from __future__ import annotations

from dataclasses import dataclass

from .config import get_acceptable_providers, get_favorite_providers
from .database_repository import DatabaseRepository, MovieDetails

RECOMMENDATION_CANDIDATE_LIMIT = 20


@dataclass(frozen=True)
class Recommendation:
    movie: MovieDetails
    score: int
    reasons: list[str]
    provider: str | None = None


class RecommendationEngine:
    def __init__(self, database_repository: DatabaseRepository):
        self.database_repository = database_repository

    def recommend_tonight(self) -> Recommendation | None:
        favorite_providers = get_favorite_providers()
        acceptable_providers = get_acceptable_providers()
        has_provider_preferences = bool(favorite_providers or acceptable_providers)
        candidate_limit = (
            RECOMMENDATION_CANDIDATE_LIMIT if has_provider_preferences else 1
        )

        movies = self.database_repository.get_random_unwatched(limit=candidate_limit)
        if not movies:
            return None

        recommendations: list[Recommendation] = []

        for movie_summary in movies:
            movie = self.database_repository.get_movie_details(movie_summary.id)
            if movie is None:
                continue

            score, reasons = self._score_movie(movie)
            preferred_provider = None
            if has_provider_preferences:
                providers = self.database_repository.get_movie_providers(movie.id)
                preferred_provider = self._preferred_provider(
                    providers,
                    favorite_providers,
                    acceptable_providers,
                )

            recommendations.append(
                Recommendation(
                    movie=movie,
                    score=score,
                    reasons=reasons,
                    provider=preferred_provider,
                )
            )

        if not recommendations:
            return None

        return sorted(
            recommendations,
            key=lambda recommendation: self._ranking_key(
                recommendation,
                favorite_providers,
                acceptable_providers,
            ),
        )[0]

    @staticmethod
    def _preferred_provider(
        providers: list[str],
        favorite_providers: list[str],
        acceptable_providers: list[str],
    ) -> str | None:
        for provider in favorite_providers:
            if provider in providers:
                return provider

        for provider in acceptable_providers:
            if provider in providers:
                return provider

        return providers[0] if providers else None

    def _ranking_key(
        self,
        recommendation: Recommendation,
        favorite_providers: list[str],
        acceptable_providers: list[str],
    ) -> tuple[int, int]:
        return (
            -recommendation.score,
            self._provider_rank(
                recommendation.provider,
                favorite_providers,
                acceptable_providers,
            ),
        )

    @staticmethod
    def _provider_rank(
        provider: str | None,
        favorite_providers: list[str],
        acceptable_providers: list[str],
    ) -> int:
        if provider in favorite_providers:
            return 0
        if provider in acceptable_providers:
            return 1
        return 2

    def _score_movie(self, movie: MovieDetails) -> tuple[int, list[str]]:
        return 0, ["Random unwatched movie"]
