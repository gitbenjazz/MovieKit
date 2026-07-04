from playwright.sync_api import sync_playwright
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moviekit import MovieRepository

repository = MovieRepository()
movies = repository.load_unwatched_1001()

movies = movies.head(10)          # <-- test with only 10 movies

with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    for _, movie in movies.iterrows():

        title = movie["title"]

        print("="*60)
        print(title)

        search = title.split("(")[0].strip()

        url = f"https://www.justwatch.com/us/search?q={search}"

        page.goto(url)

        time.sleep(5)

        print(page.title())

    browser.close()
