from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderAvailability:
    provider_name: str
    country_code: str = "US"
    access_type: str = "flatrate"
    fetched_at: str | None = None


class ProviderBackend(Protocol):
    def search_movie_availability(self, movie) -> list[ProviderAvailability]:
        """Return availability records for a movie from this backend."""
        ...

    def backend_name(self) -> str:
        """Return a stable name for this backend."""
        ...


class NullProviderBackend:
    def search_movie_availability(self, movie) -> list[ProviderAvailability]:
        return []

    def backend_name(self) -> str:
        return "null"
