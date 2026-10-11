from __future__ import annotations

from dataclasses import replace
import time

from .database_repository import DatabaseRepository
from .metadata_service import MetadataSyncService
from .personal_analytics_repository import PersonalAnalyticsRepository
from .personal_preferences import PersonalPreferenceProfile
from .recommendation_engine import RecommendationEngine
from .tmdb_client import TMDbClient, load_tmdb_api_key


# TMDb's US provider catalog: base Prime plans, excluding Amazon Video (10),
# free-with-ads (613), and all separately subscribed Amazon Channels.
PRIME_US_PROVIDER_IDS = frozenset({9, 2100})


class InvalidYearRange(ValueError):
    """The requested recommendation year interval is invalid."""


class RecommendationAccountError(ValueError):
    pass


def search_movie(title, year, api_key):
    data = TMDbClient(api_key=api_key).get_json("search/movie", params={"query": title, "year": year})
    matches = MetadataSyncService._matching_candidates(data.get("results", []), title, year)
    return matches[0]["id"] if len(matches) == 1 else None


def has_prime(movie_id, api_key):
    data = TMDbClient(api_key=api_key).get_json(f"movie/{movie_id}/watch/providers")
    if "id" in data and data["id"] != movie_id:
        return False
    regions = data.get("results")
    us = regions.get("US") if isinstance(regions, dict) else None
    providers = us.get("flatrate") if isinstance(us, dict) else None
    if not isinstance(providers, list):
        return False
    return any(isinstance(p, dict) and type(p.get("provider_id")) is int
               and p["provider_id"] in PRIME_US_PROVIDER_IDS for p in providers)


def recommend_unwatched_movies(limit=10, repository=None, api_key=None, verbose=True,
                               from_year=None, to_year=None, username=None, analytics_repository=None):
    if from_year is not None and to_year is not None and from_year > to_year:
        raise InvalidYearRange("--from-year must be less than or equal to --to-year")
    if limit <= 0:
        return []
    repository = repository or DatabaseRepository()
    analytics = analytics_repository or PersonalAnalyticsRepository(repository.database_path)
    usernames = analytics.usernames()
    if username is not None:
        username = username.strip().lower()
        if username not in usernames:
            raise RecommendationAccountError(f"No personal library found for {username}")
    elif len(usernames) > 1:
        raise RecommendationAccountError("Multiple personal accounts: specify --username")
    elif usernames:
        username = usernames[0]
    profile = PersonalPreferenceProfile(analytics.snapshot(username) if username else None)
    candidates = []
    for movie in repository.get_unwatched_movies():
        if movie.id in profile.watched_canonical_ids:
            continue
        if from_year is not None and (movie.year is None or movie.year < from_year):
            continue
        if to_year is not None and (movie.year is None or movie.year > to_year):
            continue
        details = repository.get_movie_details(movie.id)
        if details is not None:
            candidates.append(details)
    ranked = RecommendationEngine.rank(candidates, profile)
    if api_key is None:
        api_key = load_tmdb_api_key()
    if verbose:
        print(f"Preference profile: {username or 'none (neutral ranking)'}")
    results = []
    for recommendation in ranked:
        movie = recommendation.movie
        if verbose:
            print(f"Checking: {movie.title} ({movie.year})")
        movie_id = movie.tmdb_id
        if movie_id is None and movie.year is not None:
            movie_id = search_movie(movie.title, movie.year, api_key)
        if movie_id is None:
            continue
        if has_prime(movie_id, api_key):
            results.append(replace(recommendation, provider=(
                "Amazon Prime Video US (subscription) — reported by TMDb/JustWatch; "
                "confirm on Prime Video")))
            if len(results) == limit:
                break
        time.sleep(0.2)
    return results


def top_recommended_unwatched_movies(limit=10, repository=None, api_key=None, verbose=True,
                                    from_year=None, to_year=None, username=None):
    """Compatibility title-list helper; CLI uses the structured results above."""
    results = recommend_unwatched_movies(limit, repository, api_key, verbose,
                                        from_year, to_year, username)
    return [f"{r.movie.title} ({r.movie.year})" for r in results]
