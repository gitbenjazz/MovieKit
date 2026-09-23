"""Conservative, read-only matching against an existing canonical collection."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import unicodedata

from .letterboxd_export_parser import film_url, normalize_letterboxd_uri
from .personal_library_models import MovieIdentity


def normalized_title(title: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", title).casefold().replace("’", "'").split())


def normalized_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    try:
        return normalize_letterboxd_uri(uri)
    except ValueError:
        return None


class LinkState(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class CanonicalLink:
    state: LinkState
    canonical_movie_id: int | None = None
    method: str | None = None
    candidates: tuple[int, ...] = ()


class CanonicalMovieLinker:
    def __init__(self, canonical_movies):
        self.movies = tuple(canonical_movies)

    def match(self, movie: MovieIdentity, tmdb_id: int | None = None) -> CanonicalLink:
        identifiers = {uri for uri in (
            normalized_uri(movie.letterboxd_url), normalized_uri(movie.letterboxd_uri)
        ) if uri}
        identifiers.update(url for uri in tuple(identifiers) if (url := film_url(uri)))
        by_uri = {m.id for m in self.movies if normalized_uri(m.letterboxd_url) in identifiers}
        by_tmdb = {m.id for m in self.movies if tmdb_id is not None and m.tmdb_id == tmdb_id}
        strong = by_uri | by_tmdb
        if strong:
            return self._result(strong, "letterboxd" if by_uri else "tmdb")
        if movie.year is None:
            return CanonicalLink(LinkState.UNMATCHED)
        matches = {m.id for m in self.movies
                   if m.year == movie.year and normalized_title(m.title) == normalized_title(movie.title)}
        return self._result(matches, "title_year")

    @staticmethod
    def _result(ids: set[int], method: str) -> CanonicalLink:
        candidates = tuple(sorted(ids))
        if len(ids) == 1:
            return CanonicalLink(LinkState.MATCHED, candidates[0], method, candidates)
        if ids:
            return CanonicalLink(LinkState.AMBIGUOUS, method=method, candidates=candidates)
        return CanonicalLink(LinkState.UNMATCHED)
