from __future__ import annotations

from dataclasses import dataclass
import re

import pandas as pd

from .models import MovieRecord, WatchedRecord


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

    def movie_records(self) -> list[MovieRecord]:
        movies = self._matched_movies()
        return self._to_movie_records(movies)

    def watched_records(self) -> list[WatchedRecord]:
        watched = self.load_watched()
        return self._to_watched_records(watched)

    def update_watched_1001_outputs(self):
        movies = self._matched_movies()
        seen = movies[movies["seen"]]
        unseen = movies[~movies["seen"]]

        seen.to_csv(self.watched_1001_path, index=False)
        unseen.to_csv(self.unwatched_1001_path, index=False)

        return movies, seen, unseen

    def _matched_movies(self) -> pd.DataFrame:
        movies = self.load_movies()
        watched = self.load_watched()

        movies[["match_title", "match_year"]] = movies["title"].apply(
            lambda title: pd.Series(self._split_title_year(title))
        )

        watched["match_title"] = watched["Name"].str.lower().str.strip()
        watched["match_year"] = watched["Year"].fillna(0).astype(int)

        seen_keys = set(zip(watched["match_title"], watched["match_year"]))

        movies["seen"] = movies.apply(
            lambda row: (row["match_title"], row["match_year"]) in seen_keys,
            axis=1,
        )

        return movies

    def _to_movie_records(self, movies: pd.DataFrame) -> list[MovieRecord]:
        records: list[MovieRecord] = []

        for _, movie in movies.iterrows():
            title = movie.get("match_title")
            year = movie.get("match_year")
            letterboxd_url = movie.get("link")

            if pd.isna(title):
                continue

            records.append(
                MovieRecord(
                    title=str(title),
                    year=self._clean_year(year),
                    letterboxd_url=self._clean_string(letterboxd_url),
                )
            )

        return records

    def _to_watched_records(self, watched: pd.DataFrame) -> list[WatchedRecord]:
        records: list[WatchedRecord] = []

        for _, item in watched.iterrows():
            title = item.get("Name")
            year = item.get("Year")
            watched_date = item.get("Date")
            letterboxd_uri = item.get("Letterboxd URI")

            if pd.isna(title):
                continue

            records.append(
                WatchedRecord(
                    title=str(title).strip(),
                    year=self._clean_year(year),
                    watched_date=self._clean_string(watched_date),
                    letterboxd_uri=self._clean_string(letterboxd_uri),
                )
            )

        return records

    def _split_title_year(self, title) -> tuple[str, int | None]:
        if pd.isna(title):
            return "", None

        title = str(title)
        match = re.search(r"\((\d{4})\)$", title)

        if match:
            year = int(match.group(1))
            title = re.sub(r"\(\d{4}\)$", "", title).strip()
        else:
            year = None

        return title.lower(), year

    def _clean_year(self, year) -> int | None:
        if pd.isna(year) or year == 0:
            return None

        return int(year)

    def _clean_string(self, value) -> str | None:
        if pd.isna(value):
            return None

        return str(value).strip()