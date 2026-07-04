import os
from pathlib import Path
import sys
import time
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moviekit import MovieRepository

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")

repository = MovieRepository()
movies = repository.load_unwatched_1001()

BASE = "https://api.themoviedb.org/3"

prime_movies = []

def search_movie(title, year):
    title = title.rsplit("(", 1)[0].strip()

    r = requests.get(
        f"{BASE}/search/movie",
        params={
            "api_key": API_KEY,
            "query": title,
            "year": int(year),
        },
        timeout=20,
    )

    results = r.json().get("results", [])

    if not results:
        return None

    return results[0]["id"]


def has_prime(movie_id):
    r = requests.get(
        f"{BASE}/movie/{movie_id}/watch/providers",
        params={"api_key": API_KEY},
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


for _, row in movies.iterrows():

    title = row["title"]

    year = int(title[-5:-1])

    print("Checking:", title)

    movie_id = search_movie(title, year)

    if movie_id is None:
        continue

    if has_prime(movie_id):
        print("   ✓ Prime")
        prime_movies.append(title)

    if len(prime_movies) == 10:
        break

    time.sleep(0.2)

print("\n========== TOP 10 ==========\n")

for movie in prime_movies:
    print(movie)
