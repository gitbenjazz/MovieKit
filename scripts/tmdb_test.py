import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")

url = "https://api.themoviedb.org/3/search/movie"

params = {
    "api_key": API_KEY,
    "query": "Seven Samurai"
}

response = requests.get(url, params=params)

print(response.status_code)

data = response.json()

print(data["results"][0]["title"])
print(data["results"][0]["release_date"])
print(data["results"][0]["id"])
