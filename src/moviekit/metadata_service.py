from __future__ import annotations

from dataclasses import dataclass

from .database_repository import DatabaseRepository
from .models import MovieRecord
from .tmdb_client import TMDbClient


@dataclass(frozen=True)
class MetadataSyncResult:
    movie_title: str
    movie_id: int | None
    success: bool
    updated: bool
    tmdb_id: int | None = None
    tmdb_title: str | None = None
    runtime: int | None = None
    director: str | None = None
    genres: list[str] | None = None
    error_message: str | None = None


class MetadataSyncService:
    def __init__(
        self,
        database_repository: DatabaseRepository | None = None,
        client=None,
    ):
        self.database_repository = database_repository or DatabaseRepository()
        self.client = client or TMDbClient()

    def sync_movie(self, movie) -> MetadataSyncResult:
        movie_title = getattr(movie, "title", "Unknown")
        movie_id = getattr(movie, "id", None)
        movie_year = getattr(movie, "year", None)

        if movie_year is None:
            return MetadataSyncResult(
                movie_title=movie_title,
                movie_id=movie_id,
                success=False,
                updated=False,
                error_message="Movie year is required to resolve TMDb metadata",
            )

        search_response = self.client.get_json(
            "search/movie",
            params={
                "query": movie_title,
                "year": movie_year,
            },
        )
        candidates = self._matching_candidates(
            search_response.get("results", []),
            movie_title,
            movie_year,
        )

        if not candidates:
            return MetadataSyncResult(
                movie_title=movie_title,
                movie_id=movie_id,
                success=False,
                updated=False,
                error_message="No TMDb match found",
            )
        if len(candidates) > 1:
            return MetadataSyncResult(
                movie_title=movie_title,
                movie_id=movie_id,
                success=False,
                updated=False,
                error_message="Multiple TMDb matches found",
            )

        candidate = candidates[0]
        tmdb_id = candidate["id"]
        details = self.client.get_json(
            f"movie/{tmdb_id}",
            params={"append_to_response": "credits"},
        )
        metadata = self._metadata_from_details(details)

        movie_record = MovieRecord(
            title=movie.title,
            year=movie.year,
            letterboxd_url=movie.letterboxd_url,
            tmdb_id=tmdb_id,
            tmdb_title=metadata["tmdb_title"],
            runtime=metadata["runtime"],
            director=", ".join(metadata["directors"]) or None,
            genres=", ".join(metadata["genres"]) or None,
        )
        self.database_repository.save_movies([movie_record])

        return MetadataSyncResult(
            movie_title=movie_title,
            movie_id=movie_id,
            success=True,
            updated=True,
            tmdb_id=tmdb_id,
            tmdb_title=metadata["tmdb_title"],
            runtime=metadata["runtime"],
            director=", ".join(metadata["directors"]) or None,
            genres=metadata["genres"],
        )

    @classmethod
    def _matching_candidates(
        cls,
        results,
        movie_title: str,
        movie_year: int,
    ) -> list[dict]:
        if not isinstance(results, list):
            return []

        matches = []
        normalized_title = cls._normalize_title(movie_title)
        for candidate in results:
            if not isinstance(candidate, dict):
                continue
            if not isinstance(candidate.get("id"), int):
                continue
            release_year = cls._release_year(candidate.get("release_date"))
            if release_year != movie_year:
                continue

            candidate_titles = [
                candidate.get("title"),
                candidate.get("original_title"),
            ]
            if normalized_title in {
                cls._normalize_title(title)
                for title in candidate_titles
                if isinstance(title, str)
            }:
                matches.append(candidate)

        return matches

    @staticmethod
    def _metadata_from_details(details: dict) -> dict:
        genres = []
        if isinstance(details.get("genres"), list):
            genres = [
                genre["name"]
                for genre in details["genres"]
                if isinstance(genre, dict)
                and isinstance(genre.get("name"), str)
                and genre["name"].strip()
            ]

        credits = details.get("credits", {})
        crew = credits.get("crew", []) if isinstance(credits, dict) else []
        directors = [
            member["name"]
            for member in crew
            if isinstance(member, dict)
            and member.get("job") == "Director"
            and isinstance(member.get("name"), str)
            and member["name"].strip()
        ]

        return {
            "tmdb_title": details.get("title")
            if isinstance(details.get("title"), str)
            else None,
            "runtime": details.get("runtime")
            if isinstance(details.get("runtime"), int)
            else None,
            "genres": genres,
            "directors": directors,
        }

    @staticmethod
    def _normalize_title(title: str) -> str:
        return " ".join(title.casefold().split())

    @staticmethod
    def _release_year(release_date) -> int | None:
        if not isinstance(release_date, str) or len(release_date) < 4:
            return None

        try:
            return int(release_date[:4])
        except ValueError:
            return None
