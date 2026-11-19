"""Resumable personal enrichment; public metadata never creates canonical films."""
from __future__ import annotations

from dataclasses import dataclass

from .database_repository import DatabaseRepository
from .metadata_service import MetadataSyncService
from .personal_metadata_repository import PersonalMetadataRepository
from .tmdb_client import TMDbAPIError, TMDbClient
from .universal_identity_repository import UniversalIdentityRepository


@dataclass
class PersonalMetadataResult:
    total: int = 0
    processed: int = 0
    enriched: int = 0
    skipped: int = 0
    unresolved: int = 0
    failed: int = 0
    remaining: int = 0
    cached_resolved: int = 0
    cached_unresolved: int = 0
    metadata_pending: int = 0
    cached_failed: int = 0


class PersonalMetadataService:
    def __init__(self, repository=None, client=None):
        self.repository = repository or PersonalMetadataRepository()
        self.client = client or TMDbClient()
        self.canonical = DatabaseRepository(self.repository.database_path)
        self.identities = UniversalIdentityRepository(self.repository.database_path)

    def enrich(self, username, limit=None, retry_unresolved=False, retry_failed=False, refresh=False,
               dry_run=False, progress=None):
        if limit is not None and limit < 1:
            raise ValueError("--limit must be positive")
        account = self.repository.library.find_account("letterboxd", username.strip().lower())
        if account is None:
            raise ValueError(f"No personal library found for {username}")
        movies = self.repository.library.get_personal_movies(account.id)
        result = PersonalMetadataResult(total=len(movies))
        candidates = [(movie, self.repository.cached(movie)) for movie in movies]
        if refresh:
            candidates.sort(key=lambda item: (
                (item[1] or {}).get('refresh_order', 0), item[0].title.casefold(), item[0].year or 0, item[0].id
            ))
        elif retry_unresolved:
            candidates.sort(key=lambda item: (
                0 if item[1] and item[1]['status'] not in {'complete', 'pending'} else 1,
                item[0].title.casefold(), item[0].year or 0, item[0].id,
            ))
        elif retry_failed:
            candidates.sort(key=lambda item: (
                0 if item[1] and str(item[1].get('metadata_status', '')).startswith('failed_') else 1,
                item[0].title.casefold(), item[0].year or 0, item[0].id,
            ))
        eligible = []
        for movie, cached in candidates:
            if cached and cached['status'] == 'complete' and not refresh and self.identities.metadata_complete(cached):
                result.skipped += 1
                result.cached_resolved += 1
                continue
            if cached and str(cached.get('metadata_status', '')).startswith('failed_') and not retry_failed:
                result.skipped += 1
                result.cached_failed += 1
                continue
            if cached and cached['status'] != 'complete' and cached['status'] != 'pending' and not retry_unresolved:
                result.skipped += 1
                result.cached_unresolved += 1
                continue
            if cached and cached['status'] == 'complete':
                result.metadata_pending += 1
            eligible.append((movie, cached))
        result.remaining = len(eligible)
        for movie, cached in eligible:
            if limit is not None and result.processed >= limit:
                break
            result.processed += 1
            try:
                status = self._enrich_movie(movie, cached, refresh, dry_run)
            except TMDbAPIError as exc:
                # Commit per film; a failed request is never marked complete. Stop to
                # avoid hammering TMDb during outages, throttling, or bad credentials.
                result.failed += 1
                category = 'metadata' if 'incomplete or mismatched' in str(exc) else 'tmdb_api'
                if not dry_run:
                    self.repository.record_failure(movie, category, str(exc))
                result.remaining = len(eligible) - result.processed
                if progress:
                    progress(movie, f"failed [{category}]: {exc}", result)
                break
            if status == 'complete':
                result.enriched += 1
            else:
                result.unresolved += 1
            if progress:
                progress(movie, status, result)
        if not result.failed:
            result.remaining = len(eligible) - result.processed
        return result

    def _enrich_movie(self, movie, cached, refresh, dry_run=False):
        linked = self.canonical.get_movie_details(movie.canonical_movie_id) if movie.canonical_movie_id else None
        tmdb_id = linked.tmdb_id if linked else None
        if tmdb_id is None and cached:
            tmdb_id = cached['tmdb_id']
        if tmdb_id is None:
            if movie.year is None:
                self._save(movie, 'missing_year', dry_run=dry_run)
                return 'missing_year'
            response = self.client.get_json('search/movie', params={'query': movie.title, 'year': movie.year})
            matches = MetadataSyncService._matching_candidates(response.get('results', []), movie.title, movie.year)
            if len(matches) != 1:
                status = 'ambiguous' if matches else 'unmatched'
                self._save(movie, status, dry_run=dry_run)
                return status
            tmdb_id = matches[0]['id']
        # Save resolution before the second request so a resumed run avoids the
        # search. Preserve a previous complete record during explicit refresh.
        if not cached or cached['status'] != 'complete':
            self._save(movie, 'pending', tmdb_id, metadata_status='pending', dry_run=dry_run)
        details = self.client.get_json(f'movie/{tmdb_id}', params={'append_to_response': 'credits'})
        if (details.get('id') != tmdb_id or not isinstance(details.get('genres'), list)
                or not isinstance(details.get('credits'), dict)
                or not isinstance(details['credits'].get('crew'), list)):
            raise TMDbAPIError('TMDb metadata response incomplete or mismatched')
        metadata = MetadataSyncService._metadata_from_details(details)
        identity_id = None
        if not dry_run:
            identity_id = self.identities.save(
                tmdb_id, metadata['tmdb_title'], self._original_title(details),
                MetadataSyncService._release_year(details.get('release_date')) or movie.year,
                metadata['genres'], self._credits(details),
            )
        self._save(movie, 'complete', tmdb_id, metadata['genres'], metadata['directors'],
                   identity_id=identity_id, metadata_status='complete',
                   refresh_order=self.repository.next_refresh_order() if refresh and not dry_run else None,
                   dry_run=dry_run)
        return 'complete'

    def _save(self, movie, status, tmdb_id=None, genres=(), directors=(), identity_id=None,
              metadata_status=None, refresh_order=None, dry_run=False):
        if not dry_run:
            self.repository.save(movie, status, tmdb_id, genres, directors, identity_id, metadata_status,
                                 refresh_order)

    @staticmethod
    def _original_title(details):
        title = details.get('original_title')
        return title if isinstance(title, str) and title.strip() else None

    @staticmethod
    def _credits(details):
        credits = details.get('credits') if isinstance(details.get('credits'), dict) else {}
        result = []
        for member in credits.get('crew', []):
            if isinstance(member, dict) and member.get('job') == 'Director':
                result.append({'id': member.get('id'), 'name': member.get('name'), 'role': 'director',
                               'billing_order': None})
        actors = [member for member in credits.get('cast', []) if isinstance(member, dict)]
        for member in sorted(
            actors, key=lambda item: item['order'] if isinstance(item.get('order'), int) else 10 ** 9
        )[:10]:
            result.append({'id': member.get('id'), 'name': member.get('name'), 'role': 'actor',
                           'billing_order': member.get('order') if isinstance(member.get('order'), int) else None})
        return result
