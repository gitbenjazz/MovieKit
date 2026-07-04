from playwright.sync_api import sync_playwright

URL = "https://letterboxd.com/ruslanboiiko/list/1001-movies-you-must-see-before-you-die-2026/"

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False,
        slow_mo=200
    )

    page = browser.new_page(
        viewport={"width": 1600, "height": 1000}
    )

    print("Opening Letterboxd...")
    page.goto(URL, wait_until="domcontentloaded")

    input("\nPress ENTER once the page is completely loaded...")

    print("\nPAGE TITLE")
    print(page.title())

    print("\n==============================")
    print("UL ELEMENTS")
    print("==============================")

    uls = page.locator("ul")

    for i in range(uls.count()):
        cls = uls.nth(i).get_attribute("class")
        print(i, cls)

    print("\n==============================")
    print("FIRST MOVIE GRID HTML")
    print("==============================")

    movie_grid = page.locator("ul.poster-list").first

    print(movie_grid.evaluate("e => e.outerHTML"))

    input("\nPress ENTER to close...")

    browser.close()
