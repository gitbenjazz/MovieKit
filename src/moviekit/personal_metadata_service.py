"""Resumable personal enrichment; public metadata never creates canonical films."""
from __future__ import annotations

from dataclasses import dataclass

from .database_repository import DatabaseRepository
from .metadata_service import MetadataSyncService
from .personal_metadata_repository import PersonalMetadataRepository
from .tmdb_client import TMDbAPIError, TMDbClient


@dataclass
class PersonalMetadataResult:
    total: int = 0
    processed: int = 0
    enriched: int = 0
    skipped: int = 0
    unresolved: int = 0
    failed: int = 0
    remaining: int = 0


class PersonalMetadataService:
    def __init__(self, repository=None, client=None):
        self.repository = repository or PersonalMetadataRepository()
        self.client = client or TMDbClient()
        self.canonical = DatabaseRepository(self.repository.database_path)

    def enrich(self, username, limit=None, retry_unresolved=False, refresh=False, progress=None):
        if limit is not None and limit < 1:
            raise ValueError("--limit must be positive")
        account = self.repository.library.find_account("letterboxd", username.strip().lower())
        if account is None:
            raise ValueError(f"No personal library found for {username}")
        movies = self.repository.library.get_personal_movies(account.id)
        result = PersonalMetadataResult(total=len(movies))
        for movie in movies:
            cached = self.repository.cached(movie)
            if (cached and cached['status'] != 'pending' and not refresh
                    and (cached['status'] == 'complete' or not retry_unresolved)):
                result.skipped += 1
                continue
            if limit is not None and result.processed >= limit:
                result.remaining += 1
                continue
            result.processed += 1
            try:
                status = self._enrich_movie(movie, cached, refresh)
            except TMDbAPIError as exc:
                # Commit per film; a failed request is never marked complete. Stop to
                # avoid hammering TMDb during outages, throttling, or bad credentials.
                result.failed += 1
                result.remaining = result.total - result.skipped - result.processed
                if progress:
                    progress(movie, f"failed: {exc}", result)
                break
            if status == 'complete':
                result.enriched += 1
            else:
                result.unresolved += 1
            if progress:
                progress(movie, status, result)
        return result

    def _enrich_movie(self, movie, cached, refresh):
        linked = self.canonical.get_movie_details(movie.canonical_movie_id) if movie.canonical_movie_id else None
        directors = [c.name for c in linked.credits if c.role.lower() == 'director'] if linked else []
        if linked and linked.genres and directors and not refresh:
            self.repository.save(movie, 'complete', linked.tmdb_id, linked.genres, directors)
            return 'complete'
        tmdb_id = linked.tmdb_id if linked else None
        if tmdb_id is None and cached:
            tmdb_id = cached['tmdb_id']
        if tmdb_id is None:
            if movie.year is None:
                self.repository.save(movie, 'missing_year')
                return 'missing_year'
            response = self.client.get_json('search/movie', params={'query': movie.title, 'year': movie.year})
            matches = MetadataSyncService._matching_candidates(response.get('results', []), movie.title, movie.year)
            if len(matches) != 1:
                status = 'ambiguous' if matches else 'unmatched'
                self.repository.save(movie, status)
                return status
            tmdb_id = matches[0]['id']
        # Save resolution before the second request so a resumed run avoids the
        # search. Preserve a previous complete record during explicit refresh.
        if not cached or cached['status'] != 'complete':
            self.repository.save(movie, 'pending', tmdb_id)
        details = self.client.get_json(f'movie/{tmdb_id}', params={'append_to_response': 'credits'})
        if (details.get('id') != tmdb_id or not isinstance(details.get('genres'), list)
                or not isinstance(details.get('credits'), dict)
                or not isinstance(details['credits'].get('crew'), list)):
            raise TMDbAPIError('TMDb metadata response incomplete or mismatched')
        metadata = MetadataSyncService._metadata_from_details(details)
        self.repository.save(movie, 'complete', tmdb_id, metadata['genres'], metadata['directors'])
        return 'complete'
