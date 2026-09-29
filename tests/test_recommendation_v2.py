from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from moviekit.database_repository import DatabaseRepository, MovieCredit, MovieDetails
from moviekit.models import MovieRecord
from moviekit.personal_analytics_models import AnalyticsMovie, AnalyticsSnapshot, AnalyticsWatch
from moviekit.personal_library_models import AccountRecord, PersonalMovieRecord, WatchEventRecord
from moviekit.personal_library_repository import PersonalLibraryRepository
from moviekit.personal_preferences import PersonalPreferenceProfile
from moviekit.recommendation_engine import RecommendationEngine
from moviekit.recommendation_service import RecommendationAccountError, has_prime, recommend_unwatched_movies, search_movie
from moviekit.tmdb_client import TMDbAPIError


def candidate(id, title, year=1995, genres=(), directors=()):
    return MovieDetails(id, title, year, f"https://letterboxd.com/film/{id}/", id, None,
                        None, None, list(genres), [MovieCredit(i, n, "director", i) for i, n in enumerate(directors)])


def snapshot(movies=(), watches=(), genres=(), directors=()):
    return AnalyticsSnapshot("user", tuple(movies), tuple(watches), tuple(genres), tuple(directors), 10)


class PreferenceRankingTests(unittest.TestCase):
    def test_ratings_likes_rewatches_change_rank_and_are_explained(self):
        data = snapshot([
            AnalyticsMovie(1, 1990, 1, 5, True), AnalyticsMovie(2, 1990, 2, 1, False),
        ], [AnalyticsWatch(1, "2020-01-01", True, "letterboxd_diary")],
            [(1, "Drama"), (2, "Horror")], [(1, "Favorite"), (2, "Disliked")])
        profile = PersonalPreferenceProfile(data)
        best = candidate(10, "Z first", genres=["Drama"], directors=["Favorite"])
        worst = candidate(11, "A last", genres=["Horror"], directors=["Disliked"])
        ranked = RecommendationEngine.rank([worst, best], profile)
        self.assertEqual([r.movie.id for r in ranked], [10, 11])
        self.assertGreater(ranked[0].score, 0)
        self.assertLess(ranked[1].score, 0)
        self.assertTrue(any("1 liked, 1 rewatched" in r for r in ranked[0].reasons))
        self.assertTrue(any("5.00/5" in r for r in ranked[0].reasons))
        self.assertEqual(profile.watched_canonical_ids, {1})

    def test_duplicate_metadata_and_many_rewatches_do_not_multiply_affinity(self):
        movie = AnalyticsMovie(1, 1990, 1, 5, True)
        watch = AnalyticsWatch(1, "2020-01-01", True, "letterboxd_diary")
        one = PersonalPreferenceProfile(snapshot([movie], [watch], [(1, "Drama")]))
        many = PersonalPreferenceProfile(snapshot([movie], [watch] * 10, [(1, "Drama")] * 3))
        film = candidate(2, "Film", genres=["Drama", "Drama"])
        self.assertEqual(one.score(film), many.score(film))

    def test_era_fallback_is_supported_and_explicit(self):
        profile = PersonalPreferenceProfile(snapshot([
            AnalyticsMovie(1, 1992, None, 5, True), AnalyticsMovie(2, 1972, None, 1, False)
        ]))
        ranked = RecommendationEngine.rank([candidate(3, "Old", 1970), candidate(4, "New", 1995)], profile)
        self.assertEqual(ranked[0].movie.id, 4)
        self.assertIn("Era signal only", ranked[0].reasons[-1])
        self.assertFalse(any("Genre " in r for r in ranked[0].reasons))

    def test_no_history_or_unknown_features_are_neutral_with_deterministic_ties(self):
        profile = PersonalPreferenceProfile()
        movies = [candidate(2, "B"), candidate(1, "A")]
        ranked = RecommendationEngine.rank(movies, profile)
        self.assertEqual([r.movie.id for r in ranked], [1, 2])
        self.assertTrue(all(r.score == 0 for r in ranked))
        self.assertIn("neutral", ranked[0].reasons[0])
        self.assertEqual(ranked, RecommendationEngine.rank(list(reversed(movies)), profile))

    def test_small_samples_are_shrunk_and_unrated_watches_are_weak(self):
        single = PersonalPreferenceProfile(snapshot([AnalyticsMovie(1, 1990, None, None, True)]))
        several = PersonalPreferenceProfile(snapshot([AnalyticsMovie(i, 1990, None, None, True) for i in range(10)]))
        self.assertLess(single.score(candidate(30, "Film"))[0], several.score(candidate(30, "Film"))[0])
        watched = PersonalPreferenceProfile(snapshot([AnalyticsMovie(1, 1990, None, None, False)],
            [AnalyticsWatch(1, None, False, "letterboxd_watched")]))
        self.assertLess(watched.score(candidate(30, "Film"))[0], single.score(candidate(30, "Film"))[0])


class RankedRecommendationIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseRepository(Path(temp.name) / "movies.db")
        self.db.save_movies([MovieRecord("A older", 1970, "https://letterboxd.com/film/older/", tmdb_id=1),
                             MovieRecord("Z newer", 1990, "https://letterboxd.com/film/newer/", tmdb_id=2),
                             MovieRecord("History", 1991, "https://letterboxd.com/film/history/", tmdb_id=3)])
        self.personal = PersonalLibraryRepository(self.db.database_path)
        account = self.personal.upsert_account(AccountRecord("letterboxd", "user"))
        history = self.db.get_movie_by_tmdb_id(3)
        personal_movie = self.personal.upsert_personal_movie(PersonalMovieRecord(
            account.id, "History", 1991, history.letterboxd_url, canonical_movie_id=history.id))
        self.personal.save_watch_events([WatchEventRecord(account.id, personal_movie.id,
            "2020-01-01", "entry", "letterboxd_diary", True)])
        self.account = account
        self.history = history

    def run_recommend(self, **kwargs):
        with patch("moviekit.recommendation_service.time.sleep"), patch(
            "moviekit.recommendation_service.has_prime", return_value=True
        ):
            return recommend_unwatched_movies(repository=self.db, api_key="test", verbose=False, **kwargs)

    def test_ranking_before_limit_and_personal_watched_excluded_without_phase1_sync(self):
        results = self.run_recommend(limit=1)
        self.assertEqual(results[0].movie.title, "Z newer")
        self.assertNotEqual(results[0].movie.id, self.history.id)
        self.assertTrue(results[0].reasons)

    def test_filters_and_automatic_account_selection(self):
        self.assertEqual([r.movie.title for r in self.run_recommend(to_year=1970)], ["A older"])
        self.assertEqual([r.movie.title for r in self.run_recommend(from_year=1990, to_year=1990)], ["Z newer"])
        self.assertEqual(self.run_recommend(from_year=2020), [])

    def test_unavailable_top_candidate_does_not_hide_next_eligible_movie(self):
        with patch("moviekit.recommendation_service.time.sleep"), patch(
            "moviekit.recommendation_service.has_prime", side_effect=[False, True]
        ) as availability:
            results = recommend_unwatched_movies(repository=self.db, api_key="test", verbose=False, limit=1)
        self.assertEqual(results[0].movie.title, "A older")
        self.assertEqual([call.args[0] for call in availability.call_args_list], [2, 1])

    def test_accounts_are_explicit_when_multiple_and_never_blended(self):
        self.personal.upsert_account(AccountRecord("letterboxd", "other"))
        with self.assertRaises(RecommendationAccountError):
            self.run_recommend()
        with self.assertRaises(RecommendationAccountError):
            self.run_recommend(username="missing")
        self.assertEqual(self.run_recommend(username="user", limit=1)[0].movie.title, "Z newer")
        other = self.run_recommend(username="other")
        self.assertTrue(all(r.score == 0 for r in other))
        self.assertIn(self.history.id, {r.movie.id for r in other})

    def test_network_failure_is_not_misreported_as_no_availability(self):
        with patch("moviekit.recommendation_service.has_prime", side_effect=TMDbAPIError("TMDb request failed")):
            with self.assertRaises(TMDbAPIError):
                recommend_unwatched_movies(repository=self.db, api_key="test", verbose=False)


class PrimeFilterTests(unittest.TestCase):
    def test_only_us_prime_subscription_is_accepted(self):
        cases = [
            ({"US": {"flatrate": [{"provider_name": "Amazon Prime Video"}]}}, True),
            ({"US": {"flatrate": [{"provider_name": "Amazon Prime Video with Ads"}]}}, True),
            ({"US": {"rent": [{"provider_name": "Amazon Prime Video"}]}}, False),
            ({"US": {"flatrate": [{"provider_name": "MGM+ Amazon Channel"}]}}, False),
            ({"FR": {"flatrate": [{"provider_name": "Amazon Prime Video"}]}}, False),
        ]
        for data, expected in cases:
            with self.subTest(data=data), patch("moviekit.recommendation_service.TMDbClient") as client:
                client.return_value.get_json.return_value = {"results": data}
                self.assertEqual(has_prime(1, "test"), expected)

    def test_search_rejects_wrong_year_and_ambiguous_matches(self):
        candidate_data = {"id": 1, "title": "Film", "release_date": "1990-01-01"}
        with patch("moviekit.recommendation_service.TMDbClient") as client:
            client.return_value.get_json.return_value = {"results": [candidate_data]}
            self.assertIsNone(search_movie("Film", 1991, "test"))
            self.assertEqual(search_movie("Film", 1990, "test"), 1)
            client.return_value.get_json.return_value = {"results": [candidate_data, dict(candidate_data, id=2)]}
            self.assertIsNone(search_movie("Film", 1990, "test"))
