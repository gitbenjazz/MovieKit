from __future__ import annotations

from dataclasses import dataclass

from ..database_repository import MovieSummary
from ..metadata_service import MetadataSyncResult
from ..provider_backend import ProviderAvailability
from ..sync_service import SyncResult


@dataclass(frozen=True)
class SingleMovieMetadataResult:
    movie: MovieSummary | None
    sync_result: MetadataSyncResult | None
    error_message: str | None = None


@dataclass(frozen=True)
class SingleMovieAvailabilityResult:
    movie: MovieSummary | None
    sync_result: SyncResult | None
    availability: list[ProviderAvailability]


class SearchMovies:
    def __init__(self, search_service=None):
        if search_service is None:
            from ..search_service import SearchService

            search_service = SearchService()

        self.search_service = search_service

    def execute(
        self,
        text: str,
        limit: int,
        watched: bool | None = None,
    ):
        return self.search_service.search(
            text,
            limit=limit,
            watched=watched,
        )


class RecommendTonight:
    def __init__(self, recommendation_engine=None):
        if recommendation_engine is None:
            from ..database_repository import DatabaseRepository
            from ..recommendation_engine import RecommendationEngine

            recommendation_engine = RecommendationEngine(DatabaseRepository())

        self.recommendation_engine = recommendation_engine

    def execute(self):
        return self.recommendation_engine.recommend_tonight()


class RecommendTopMovies:
    def __init__(self, recommendation_function=None):
        if recommendation_function is None:
            from ..recommendation_service import top_recommended_unwatched_movies

            recommendation_function = top_recommended_unwatched_movies

        self.recommendation_function = recommendation_function

    def execute(
        self,
        limit: int = 10,
        verbose: bool = True,
        from_year: int | None = None,
        to_year: int | None = None,
    ):
        return self.recommendation_function(
            limit=limit,
            verbose=verbose,
            from_year=from_year,
            to_year=to_year,
        )


class SyncLibrary:
    def __init__(self, sync_service=None):
        if sync_service is None:
            from ..sync_service import SyncService

            sync_service = SyncService()

        self.sync_service = sync_service

    def execute(self):
        return self.sync_service.sync()


class SyncMetadata:
    def __init__(
        self,
        bulk_sync_service=None,
        repository=None,
        search_service=None,
        metadata_service=None,
    ):
        self._bulk_sync_service = bulk_sync_service
        self._repository = repository
        self._search_service = search_service
        self._metadata_service = metadata_service

    def execute(self):
        return self._bulk().sync_metadata()

    def execute_movie(self, title: str) -> SingleMovieMetadataResult:
        repository = self._single_movie_repository()
        search_service = self._search_service
        if search_service is None:
            from ..search_service import SearchService

            search_service = SearchService(repository)

        results = search_service.search(title, limit=1)
        if not results:
            return SingleMovieMetadataResult(
                movie=None,
                sync_result=None,
            )

        movie = results[0].movie
        metadata_service = self._metadata_service
        if metadata_service is None:
            from ..metadata_service import MetadataSyncService

            metadata_service = MetadataSyncService(repository)

        try:
            result = metadata_service.sync_movie(movie)
        except Exception as exc:
            return SingleMovieMetadataResult(
                movie=movie,
                sync_result=None,
                error_message=str(exc),
            )

        return SingleMovieMetadataResult(
            movie=movie,
            sync_result=result,
        )

    def _bulk(self):
        if self._bulk_sync_service is None:
            from ..bulk_sync_service import BulkSyncService

            self._bulk_sync_service = BulkSyncService()

        return self._bulk_sync_service

    def _single_movie_repository(self):
        if self._repository is None:
            from ..database_repository import DatabaseRepository

            self._repository = DatabaseRepository()

        return self._repository


class SyncAvailability:
    def __init__(
        self,
        bulk_sync_service=None,
        repository=None,
        search_service=None,
        provider_service=None,
        sync_service=None,
    ):
        self._bulk_sync_service = bulk_sync_service
        self._repository = repository
        self._search_service = search_service
        self._provider_service = provider_service
        self._sync_service = sync_service

    def execute(self):
        return self._bulk().sync_availability()

    def execute_movie(self, title: str) -> SingleMovieAvailabilityResult:
        repository = self._single_movie_repository()
        search_service = self._search_service
        if search_service is None:
            from ..search_service import SearchService

            search_service = SearchService(repository)

        results = search_service.search(title, limit=1)
        if not results:
            return SingleMovieAvailabilityResult(
                movie=None,
                sync_result=None,
                availability=[],
            )

        movie = results[0].movie
        provider_service = self._provider_service
        if provider_service is None:
            from ..provider_service import ProviderService
            from ..tmdb_provider_backend import TMDbProviderBackend

            provider_service = ProviderService(
                repository,
                backend=TMDbProviderBackend(),
            )

        sync_service = self._sync_service
        if sync_service is None:
            from ..sync_service import SyncService

            sync_service = SyncService(
                database_repository=repository,
                provider_service=provider_service,
            )

        result = sync_service.sync_movie(movie)
        availability = []
        if result.success and result.availability_records_written > 0:
            availability = provider_service.get_movie_availability(movie.id)

        return SingleMovieAvailabilityResult(
            movie=movie,
            sync_result=result,
            availability=availability,
        )

    def _bulk(self):
        if self._bulk_sync_service is None:
            from ..bulk_sync_service import BulkSyncService

            self._bulk_sync_service = BulkSyncService()

        return self._bulk_sync_service

    def _single_movie_repository(self):
        if self._repository is None:
            from ..database_repository import DatabaseRepository

            self._repository = DatabaseRepository()

        return self._repository


class SyncAll:
    def __init__(self, bulk_sync_service=None):
        self._bulk_sync_service = bulk_sync_service

    def execute(self):
        if self._bulk_sync_service is None:
            from ..bulk_sync_service import BulkSyncService

            self._bulk_sync_service = BulkSyncService()

        return self._bulk_sync_service.sync_all()


class InitializeDatabase:
    def __init__(self, database_path=None, initializer=None):
        if database_path is None:
            from ..config import load_config

            database_path = load_config().database_path
        if initializer is None:
            from ..database import initialize_database

            initializer = initialize_database

        self.database_path = database_path
        self.initializer = initializer

    def execute(self):
        return self.initializer(self.database_path)


class SyncPersonalLibrary:
    def __init__(self, service=None):
        if service is None:
            from ..personal_library_sync import PersonalLibrarySyncService

            service = PersonalLibrarySyncService()
        self.service = service

    def execute(self, source, username):
        return self.service.sync(source, username)


@dataclass(frozen=True)
class PersonalLibraryStatus:
    username: str
    movies: int
    canonical_matches: int
    watch_events: int
    ratings: int
    reviews: int
    likes: int
    last_sync: dict | None


class GetPersonalLibraryStatus:
    def __init__(self, repository=None):
        if repository is None:
            from ..personal_library_repository import PersonalLibraryRepository

            repository = PersonalLibraryRepository()
        self.repository = repository

    def execute(self, username):
        account = self.repository.find_account("letterboxd", username.strip().lower())
        if account is None:
            return None
        library = self.repository.get_personal_library(account.id)
        return PersonalLibraryStatus(
            account.username, len(library.movies),
            sum(m.canonical_movie_id is not None for m in library.movies),
            len(library.watch_events), len(library.ratings), len(library.reviews),
            len(library.likes), self.repository.latest_sync_run(account.id),
        )


class GetPersonalStats:
    def __init__(self, service=None):
        if service is None:
            from ..personal_analytics_service import PersonalAnalyticsService

            service = PersonalAnalyticsService()
        self.service = service

    def execute(self, username):
        return self.service.stats(username)
