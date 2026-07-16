from __future__ import annotations

from typing import Optional

from .provider_backend import ProviderAvailability
from .tmdb_client import TMDbClient


class TMDbProviderBackend:
    _ACCESS_TYPE_BY_TMDB_CATEGORY = {
        "flatrate": "subscription",
        "free": "free",
        "ads": "ads",
        "rent": "rent",
        "buy": "buy",
    }

    def __init__(
        self,
        client=None,
        country_code: str = "US",
        api_key: Optional[str] = None,
    ):
        self.client = client or TMDbClient(api_key=api_key)
        self.country_code = country_code.strip().upper()

    def search_movie_availability(self, movie) -> list[ProviderAvailability]:
        tmdb_id = getattr(movie, "tmdb_id", None)
        if tmdb_id is None:
            return []

        response = self.client.get_json(f"movie/{tmdb_id}/watch/providers")
        country_availability = (
            response.get("results", {}).get(self.country_code, {})
            if isinstance(response.get("results"), dict)
            else {}
        )

        if not isinstance(country_availability, dict):
            return []

        availability = []
        for tmdb_category, access_type in self._ACCESS_TYPE_BY_TMDB_CATEGORY.items():
            providers = country_availability.get(tmdb_category, [])
            if not isinstance(providers, list):
                continue

            for provider in providers:
                provider_name = self._provider_name(provider)
                if provider_name is None:
                    continue

                availability.append(
                    ProviderAvailability(
                        provider_name=provider_name,
                        country_code=self.country_code,
                        access_type=access_type,
                    )
                )

        return availability

    def backend_name(self) -> str:
        return "tmdb"

    @staticmethod
    def _provider_name(provider) -> str | None:
        if not isinstance(provider, dict):
            return None

        provider_name = provider.get("provider_name")
        if not isinstance(provider_name, str) or not provider_name.strip():
            return None

        return provider_name
