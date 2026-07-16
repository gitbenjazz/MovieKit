import time
from typing import List, Optional

import requests

from .movie_repository import MovieRepository
from .tmdb_client import load_tmdb_api_key

BASE = "https://api.themoviedb.org/3"


def search_movie(title: str, year: int, api_key: Optional[str]) -> Optional[int]:
    """Search TMDB for a movie and return the first matching movie id."""
    title = title.rsplit("(", 1)[0].strip()

    r = requests.get(
        f"{BASE}/search/movie",
        params={
            "api_key": api_key,
            "query": title,
            "year": int(year),
        },
        timeout=20,
    )

    results = r.json().get("results", [])

    if not results:
        return None

    return results[0]["id"]


def has_prime(movie_id: int, api_key: Optional[str]) -> bool:
    """Return True when the movie is available on Prime Video flatrate in the US."""
    r = requests.get(
        f"{BASE}/movie/{movie_id}/watch/providers",
        params={"api_key": api_key},
        timeout=20,
    )

    data = r.json()

    us = data.get("results", {}).get("US", {})

    # Only subscription services (NOT rent/buy)
    providers = us.get("flatrate", [])

    for p in providers:
        if p["provider_name"] == "Amazon Prime Video":
            return True

    return False


def top_recommended_unwatched_movies(
    limit: int = 10,
    repository: Optional[MovieRepository] = None,
    api_key: Optional[str] = None,
    verbose: bool = True,
) -> List[str]:
    """Return the first unwatched 1001 movies available on Prime Video."""
    if api_key is None:
        api_key = load_tmdb_api_key()

    if repository is None:
        repository = MovieRepository()

    movies = repository.load_unwatched_1001()
    prime_movies = []

    for _, row in movies.iterrows():

        title = row["title"]

        year = int(title[-5:-1])

        if verbose:
            print("Checking:", title)

        movie_id = search_movie(title, year, api_key)

        if movie_id is None:
            continue

        if has_prime(movie_id, api_key):
            if verbose:
                print("   ✓ Prime")
            prime_movies.append(title)

        if len(prime_movies) == limit:
            break

        time.sleep(0.2)

    return prime_movies
