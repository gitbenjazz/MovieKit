import pandas as pd
import re

# Read data
movies = pd.read_csv("movies.csv")
watched = pd.read_csv("watched.csv")


def split_title_year(title):
    """
    Converts:
        'The Godfather (1972)'
    into:
        ('the godfather', 1972)
    """
    if pd.isna(title):
        return "", None

    title = str(title)

    m = re.search(r"\((\d{4})\)$", title)

    if m:
        year = int(m.group(1))
        title = re.sub(r"\(\d{4}\)$", "", title).strip()
    else:
        year = None

    return title.lower(), year


movies[["match_title", "match_year"]] = movies["title"].apply(
    lambda x: pd.Series(split_title_year(x))
)

watched["match_title"] = watched["Name"].str.lower().str.strip()
watched["match_year"] = watched["Year"].fillna(0).astype(int)

seen_keys = set(
    zip(
        watched["match_title"],
        watched["match_year"],
    )
)

movies["seen"] = movies.apply(
    lambda row: (row["match_title"], row["match_year"]) in seen_keys,
    axis=1,
)

seen = movies[movies["seen"]]
unseen = movies[~movies["seen"]]

seen.to_csv("watched1001.csv", index=False)
unseen.to_csv("unwatched1001.csv", index=False)

print("=" * 50)
print(f"Seen      : {len(seen)}")
print(f"Remaining : {len(unseen)}")
print(f"Progress  : {len(seen)/len(movies):.1%}")
print("=" * 50)
