from dataclasses import dataclass
import re

import pandas as pd


@dataclass
class MovieRepository:
    movies_path: str = "movies.csv"
    watched_path: str = "watched.csv"
    watched_1001_path: str = "watched1001.csv"
    unwatched_1001_path: str = "unwatched1001.csv"

    def load_movies(self):
        return pd.read_csv(self.movies_path)

    def load_watched(self):
        return pd.read_csv(self.watched_path)

    def load_watched_1001(self):
        return pd.read_csv(self.watched_1001_path)

    def load_unwatched_1001(self):
        return pd.read_csv(self.unwatched_1001_path)

    def split_title_year(self, title):
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

    def match_watched_1001(self):
        movies = self.load_movies()
        watched = self.load_watched()

        movies[["match_title", "match_year"]] = movies["title"].apply(
            lambda x: pd.Series(self.split_title_year(x))
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

        return movies, seen, unseen

    def save_watched_1001_outputs(self, seen, unseen):
        seen.to_csv(self.watched_1001_path, index=False)
        unseen.to_csv(self.unwatched_1001_path, index=False)

    def update_watched_1001_outputs(self):
        movies, seen, unseen = self.match_watched_1001()
        self.save_watched_1001_outputs(seen, unseen)
        return movies, seen, unseen
