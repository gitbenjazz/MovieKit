from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.database_repository import MovieCredit, MovieDetails, MovieSummary
from moviekit.recommendation_engine import Recommendation, RecommendationEngine


class FakeRepository:
    def __init__(
        self,
        random_unwatched: list[MovieSummary],
        details: MovieDetails | dict[int, MovieDetails | None] | None,
        providers: dict[int, list[str]] | None = None,
    ):
        self.random_unwatched = random_unwatched
        self.details = details
        self.providers = providers or {}
        self.random_limits: list[int] = []
        self.detail_movie_ids: list[int] = []
        self.provider_movie_ids: list[int] = []

    def get_random_unwatched(self, limit: int = 1) -> list[MovieSummary]:
        self.random_limits.append(limit)
        return self.random_unwatched[:limit]

    def get_movie_details(self, movie_id: int) -> MovieDetails | None:
        self.detail_movie_ids.append(movie_id)
        if isinstance(self.details, dict):
            return self.details.get(movie_id)

        return self.details

    def get_movie_providers(self, movie_id: int) -> list[str]:
        self.provider_movie_ids.append(movie_id)
        return self.providers.get(movie_id, [])


class RecommendationEngineTests(unittest.TestCase):
    def _movie_summary(
        self,
        movie_id: int = 42,
        title: str = "Moonlight",
    ) -> MovieSummary:
        return MovieSummary(
            id=movie_id,
            title=title,
            year=2016,
            letterboxd_url=f"https://letterboxd.com/film/{title.lower().replace(' ', '-')}/",
            tmdb_id=376867,
            tmdb_title=title,
            rating=7.4,
            runtime=111,
        )

    def _movie_details(
        self,
        movie_id: int = 42,
        title: str = "Moonlight",
    ) -> MovieDetails:
        return MovieDetails(
            id=movie_id,
            title=title,
            year=2016,
            letterboxd_url=f"https://letterboxd.com/film/{title.lower().replace(' ', '-')}/",
            tmdb_id=376867,
            tmdb_title=title,
            rating=7.4,
            runtime=111,
            genres=["Drama"],
            credits=[
                MovieCredit(
                    person_id=1,
                    name="Barry Jenkins",
                    role="director",
                    billing_order=1,
                )
            ],
        )

    def test_recommend_tonight_returns_random_unwatched_recommendation(self) -> None:
        summary = self._movie_summary()
        details = self._movie_details()
        repository = FakeRepository([summary], details)

        with self._provider_preferences():
            recommendation = RecommendationEngine(repository).recommend_tonight()

        self.assertIsInstance(recommendation, Recommendation)
        self.assertEqual(recommendation.movie, details)
        self.assertEqual(recommendation.score, 0)
        self.assertEqual(recommendation.reasons, ["Random unwatched movie"])
        self.assertIsNone(recommendation.provider)
        self.assertEqual(repository.random_limits, [1])
        self.assertEqual(repository.detail_movie_ids, [42])
        self.assertEqual(repository.provider_movie_ids, [])

    def test_score_movie_returns_initial_random_reason(self) -> None:
        engine = RecommendationEngine(FakeRepository([], None))

        score, reasons = engine._score_movie(self._movie_details())

        self.assertEqual(score, 0)
        self.assertEqual(reasons, ["Random unwatched movie"])

    def test_recommend_tonight_uses_score_movie_result(self) -> None:
        class TestEngine(RecommendationEngine):
            def __init__(self, database_repository):
                super().__init__(database_repository)
                self.scored_movies = []

            def _score_movie(self, movie: MovieDetails) -> tuple[int, list[str]]:
                self.scored_movies.append(movie)
                return 17, ["Custom scoring reason"]

        summary = self._movie_summary()
        details = self._movie_details()
        engine = TestEngine(FakeRepository([summary], details))

        with self._provider_preferences():
            recommendation = engine.recommend_tonight()

        self.assertEqual(engine.scored_movies, [details])
        self.assertEqual(recommendation.movie, details)
        self.assertEqual(recommendation.score, 17)
        self.assertEqual(recommendation.reasons, ["Custom scoring reason"])

    def test_recommend_tonight_preserves_existing_order_with_empty_preferences(
        self,
    ) -> None:
        first_summary = self._movie_summary(1, "First Movie")
        second_summary = self._movie_summary(2, "Second Movie")
        first_details = self._movie_details(1, "First Movie")
        second_details = self._movie_details(2, "Second Movie")
        repository = FakeRepository(
            [first_summary, second_summary],
            {
                1: first_details,
                2: second_details,
            },
            {
                1: ["Apple TV"],
                2: ["Prime"],
            },
        )

        with self._provider_preferences():
            recommendation = RecommendationEngine(repository).recommend_tonight()

        self.assertEqual(recommendation.movie, first_details)
        self.assertIsNone(recommendation.provider)
        self.assertEqual(repository.random_limits, [1])
        self.assertEqual(repository.detail_movie_ids, [1])
        self.assertEqual(repository.provider_movie_ids, [])

    def test_favorite_provider_outranks_acceptable_provider(self) -> None:
        favorite = self._movie_summary(1, "Favorite Movie")
        acceptable = self._movie_summary(2, "Acceptable Movie")

        recommendation = self._recommend_from_candidates(
            [acceptable, favorite],
            providers={
                1: ["Prime"],
                2: ["Tubi"],
            },
            favorite_providers=["Prime", "YouTube"],
            acceptable_providers=["Tubi"],
        )

        self.assertEqual(recommendation.movie.id, 1)
        self.assertEqual(recommendation.provider, "Prime")

    def test_acceptable_provider_outranks_unknown_provider(self) -> None:
        unknown = self._movie_summary(1, "Unknown Provider Movie")
        acceptable = self._movie_summary(2, "Acceptable Movie")

        recommendation = self._recommend_from_candidates(
            [unknown, acceptable],
            providers={
                1: ["Apple TV"],
                2: ["Tubi"],
            },
            favorite_providers=[],
            acceptable_providers=["Tubi"],
        )

        self.assertEqual(recommendation.movie.id, 2)
        self.assertEqual(recommendation.provider, "Tubi")

    def test_multiple_providers_choose_best_preferred_provider(self) -> None:
        movie = self._movie_summary(1, "Many Providers Movie")

        recommendation = self._recommend_from_candidates(
            [movie],
            providers={
                1: ["Apple TV", "Prime", "Tubi"],
            },
            favorite_providers=["Prime"],
            acceptable_providers=["Tubi"],
        )

        self.assertEqual(recommendation.movie.id, 1)
        self.assertEqual(recommendation.provider, "Prime")

    def test_identical_movie_scores_are_resolved_by_provider_preference(self) -> None:
        unknown = self._movie_summary(1, "Unknown Provider Movie")
        favorite = self._movie_summary(2, "Favorite Movie")

        recommendation = self._recommend_from_candidates(
            [unknown, favorite],
            providers={
                1: ["Apple TV"],
                2: ["YouTube"],
            },
            favorite_providers=["YouTube"],
            acceptable_providers=[],
        )

        self.assertEqual(recommendation.score, 0)
        self.assertEqual(recommendation.movie.id, 2)
        self.assertEqual(recommendation.provider, "YouTube")

    def test_recommend_tonight_returns_none_when_no_unwatched_movies_exist(self) -> None:
        repository = FakeRepository([], None)

        with self._provider_preferences():
            recommendation = RecommendationEngine(repository).recommend_tonight()

        self.assertIsNone(recommendation)
        self.assertEqual(repository.random_limits, [1])
        self.assertEqual(repository.detail_movie_ids, [])

    def test_recommend_tonight_returns_none_when_details_are_missing(self) -> None:
        summary = MovieSummary(
            id=7,
            title="Missing Details",
            year=None,
            letterboxd_url="https://letterboxd.com/film/missing-details/",
            tmdb_id=None,
            tmdb_title=None,
            rating=None,
            runtime=None,
        )
        repository = FakeRepository([summary], None)

        with self._provider_preferences():
            recommendation = RecommendationEngine(repository).recommend_tonight()

        self.assertIsNone(recommendation)
        self.assertEqual(repository.random_limits, [1])
        self.assertEqual(repository.detail_movie_ids, [7])

    def _recommend_from_candidates(
        self,
        summaries: list[MovieSummary],
        providers: dict[int, list[str]],
        favorite_providers: list[str],
        acceptable_providers: list[str],
    ) -> Recommendation:
        details = {
            summary.id: self._movie_details(summary.id, summary.title)
            for summary in summaries
        }
        repository = FakeRepository(summaries, details, providers)

        with self._provider_preferences(
            favorite_providers=favorite_providers,
            acceptable_providers=acceptable_providers,
        ):
            recommendation = RecommendationEngine(repository).recommend_tonight()

        self.assertIsNotNone(recommendation)
        self.assertEqual(repository.random_limits, [20])
        return recommendation

    def _provider_preferences(
        self,
        favorite_providers: list[str] | None = None,
        acceptable_providers: list[str] | None = None,
    ):
        return patch.multiple(
            "moviekit.recommendation_engine",
            get_favorite_providers=lambda: favorite_providers or [],
            get_acceptable_providers=lambda: acceptable_providers or [],
        )


if __name__ == "__main__":
    unittest.main()
