import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")

movie_id = 346   # Seven Samurai

url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"

response = requests.get(
    url,
    params={"api_key": API_KEY}
)

print(response.status_code)

data = response.json()

print(data)
