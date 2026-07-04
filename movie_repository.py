from dataclasses import dataclass

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
