from __future__ import annotations

from pathlib import Path
import sys
import unittest

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
        details: MovieDetails | None,
    ):
        self.random_unwatched = random_unwatched
        self.details = details
        self.random_limits: list[int] = []
        self.detail_movie_ids: list[int] = []

    def get_random_unwatched(self, limit: int = 1) -> list[MovieSummary]:
        self.random_limits.append(limit)
        return self.random_unwatched

    def get_movie_details(self, movie_id: int) -> MovieDetails | None:
        self.detail_movie_ids.append(movie_id)
        return self.details


class RecommendationEngineTests(unittest.TestCase):
    def _movie_summary(self, movie_id: int = 42) -> MovieSummary:
        return MovieSummary(
            id=movie_id,
            title="Moonlight",
            year=2016,
            letterboxd_url="https://letterboxd.com/film/moonlight-2016/",
            tmdb_id=376867,
            tmdb_title="Moonlight",
            rating=7.4,
            runtime=111,
        )

    def _movie_details(self, movie_id: int = 42) -> MovieDetails:
        return MovieDetails(
            id=movie_id,
            title="Moonlight",
            year=2016,
            letterboxd_url="https://letterboxd.com/film/moonlight-2016/",
            tmdb_id=376867,
            tmdb_title="Moonlight",
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

        recommendation = RecommendationEngine(repository).recommend_tonight()

        self.assertIsInstance(recommendation, Recommendation)
        self.assertEqual(recommendation.movie, details)
        self.assertEqual(recommendation.score, 0)
        self.assertEqual(recommendation.reasons, ["Random unwatched movie"])
        self.assertEqual(repository.random_limits, [1])
        self.assertEqual(repository.detail_movie_ids, [42])

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

        recommendation = engine.recommend_tonight()

        self.assertEqual(engine.scored_movies, [details])
        self.assertEqual(recommendation.movie, details)
        self.assertEqual(recommendation.score, 17)
        self.assertEqual(recommendation.reasons, ["Custom scoring reason"])

    def test_recommend_tonight_returns_none_when_no_unwatched_movies_exist(self) -> None:
        repository = FakeRepository([], None)

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

        recommendation = RecommendationEngine(repository).recommend_tonight()

        self.assertIsNone(recommendation)
        self.assertEqual(repository.random_limits, [1])
        self.assertEqual(repository.detail_movie_ids, [7])


if __name__ == "__main__":
    unittest.main()
