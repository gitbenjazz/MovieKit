from __future__ import annotations

from dataclasses import dataclass

from .database_repository import DatabaseRepository
from .metadata_service import MetadataSyncService
from .sync_service import SyncService
from .tmdb_client import TMDbAPIError


@dataclass(frozen=True)
class BulkSyncResult:
    processed: int
    updated: int
    skipped: int
    failed: int


@dataclass(frozen=True)
class BulkSyncRunResult:
    metadata: BulkSyncResult
    availability: BulkSyncResult


class BulkSyncService:
    _METADATA_SKIP_MESSAGES = {
        "Movie year is required to resolve TMDb metadata",
        "No TMDb match found",
        "Multiple TMDb matches found",
    }

    def __init__(
        self,
        repository: DatabaseRepository | None = None,
        metadata_service: MetadataSyncService | None = None,
        availability_service: SyncService | None = None,
    ):
        self.repository = repository or DatabaseRepository()
        self.metadata_service = metadata_service or MetadataSyncService(
            self.repository
        )
        self.availability_service = availability_service or SyncService(
            database_repository=self.repository
        )

    def sync_metadata(self, limit=None, progress=None) -> BulkSyncResult:
        if limit is not None and limit < 1:
            raise ValueError("--limit must be positive")
        processed = 0
        updated = 0
        skipped = 0
        failed = 0

        enriched = self.repository.enriched_metadata_ids()
        attempted = 0
        for movie in self.repository.get_all_movies():
            if movie.id in enriched:
                processed += 1
                skipped += 1
                if progress:
                    progress(movie, "cached", processed)
                continue
            if limit is not None and attempted >= limit:
                break
            attempted += 1
            processed += 1
            if progress:
                progress(movie, "fetching", processed)
            try:
                result = self.metadata_service.sync_movie(movie)
            except TMDbAPIError as exc:
                failed += 1
                if progress:
                    progress(movie, f"failed: {exc}; stopping, rerun to resume", processed)
                break
            except Exception:
                failed += 1
                if progress:
                    progress(movie, "failed: metadata synchronization error", processed)
                continue

            if result.success and result.updated:
                updated += 1
            elif result.success:
                skipped += 1
            elif result.error_message in self._METADATA_SKIP_MESSAGES:
                skipped += 1
            else:
                failed += 1
            if progress:
                status = "updated" if result.success and result.updated else (
                    result.error_message or "unchanged")
                progress(movie, status, processed)

        return BulkSyncResult(
            processed=processed,
            updated=updated,
            skipped=skipped,
            failed=failed,
        )

    def sync_availability(self) -> BulkSyncResult:
        processed = 0
        updated = 0
        skipped = 0
        failed = 0

        for movie in self.repository.get_all_movies():
            processed += 1
            try:
                result = self.availability_service.sync_movie(movie)
            except Exception:
                failed += 1
                continue

            if result.success and result.availability_records_written > 0:
                updated += 1
            elif result.success:
                skipped += 1
            elif result.error_message == "Movie is missing a TMDb ID":
                skipped += 1
            else:
                failed += 1

        return BulkSyncResult(
            processed=processed,
            updated=updated,
            skipped=skipped,
            failed=failed,
        )

    def sync_all(self) -> BulkSyncRunResult:
        metadata_result = self.sync_metadata()
        availability_result = self.sync_availability()

        return BulkSyncRunResult(
            metadata=metadata_result,
            availability=availability_result,
        )
