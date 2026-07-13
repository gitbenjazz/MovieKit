from __future__ import annotations

from dataclasses import dataclass

from .database_repository import DatabaseRepository, MovieSummary

DEFAULT_SEARCH_LIMIT = 20


@dataclass(frozen=True)
class MovieSearchResult:
    movie: MovieSummary
    watched: bool


class SearchService:
    def __init__(self, database_repository: DatabaseRepository | None = None):
        self.database_repository = database_repository or DatabaseRepository()

    def search(
        self,
        text: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        watched: bool | None = None,
    ) -> list[MovieSearchResult]:
        query = text.strip()
        if not query or limit <= 0:
            return []

        movies = self.database_repository.search_movies(query)
        watched_ids = self.database_repository.get_watched_movie_ids()
        results = [
            MovieSearchResult(
                movie=movie,
                watched=movie.id in watched_ids,
            )
            for movie in movies
        ]

        if watched is not None:
            results = [result for result in results if result.watched == watched]

        return sorted(
            results,
            key=lambda result: (
                self._match_rank(result.movie, query),
                self._year_sort_key(result.movie),
                result.movie.title.lower(),
            ),
        )[:limit]

    @staticmethod
    def _match_rank(movie: MovieSummary, query: str) -> int:
        normalized_query = query.lower()
        title = movie.title.lower()
        tmdb_title = (movie.tmdb_title or "").lower()
        tmdb_id = str(movie.tmdb_id or "")
        letterboxd_url = movie.letterboxd_url.lower()

        if title == normalized_query:
            return 0
        if title.startswith(normalized_query):
            return 1
        if normalized_query in title:
            return 2
        if tmdb_title == normalized_query:
            return 3
        if tmdb_title.startswith(normalized_query):
            return 4
        if normalized_query in tmdb_title:
            return 5
        if normalized_query == tmdb_id:
            return 6
        if normalized_query in letterboxd_url:
            return 7

        return 8

    @staticmethod
    def _year_sort_key(movie: MovieSummary) -> tuple[int, int]:
        if movie.year is None:
            return (1, 0)

        return (0, movie.year)
