from playwright.sync_api import sync_playwright
import pandas as pd
import time

BASE = "https://letterboxd.com/ruslanboiiko/list/1001-movies-you-must-see-before-you-die-2026/"

movies = []

with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page_number = 1

    while True:

        url = BASE if page_number == 1 else f"{BASE}page/{page_number}/"

        print(f"Opening page {page_number}")

        page.goto(url, wait_until="domcontentloaded")

        time.sleep(2)

        posters = page.locator("div.react-component[data-item-name]")

        count = posters.count()

        print(f"Found {count} movies")

        if count == 0:
            break

        for i in range(count):

            poster = posters.nth(i)

            movies.append({
                "title": poster.get_attribute("data-item-name"),
                "slug": poster.get_attribute("data-item-slug"),
                "link": "https://letterboxd.com" + poster.get_attribute("data-item-link")
            })

        page_number += 1

    browser.close()

df = pd.DataFrame(movies)

df.to_csv("movies.csv", index=False)

print()
print(df.head())
print()
print(f"Saved {len(df)} movies.")
