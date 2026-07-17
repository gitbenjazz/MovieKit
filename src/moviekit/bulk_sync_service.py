from __future__ import annotations

from dataclasses import dataclass

from .database_repository import DatabaseRepository
from .metadata_service import MetadataSyncService
from .sync_service import SyncService


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

    def sync_metadata(self) -> BulkSyncResult:
        processed = 0
        updated = 0
        skipped = 0
        failed = 0

        for movie in self.repository.get_all_movies():
            processed += 1
            try:
                result = self.metadata_service.sync_movie(movie)
            except Exception:
                failed += 1
                continue

            if result.success and result.updated:
                updated += 1
            elif result.success:
                skipped += 1
            elif result.error_message in self._METADATA_SKIP_MESSAGES:
                skipped += 1
            else:
                failed += 1

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
