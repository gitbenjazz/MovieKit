from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.provider_backend import ProviderAvailability
from moviekit.provider_service import ProviderService
from moviekit.tmdb_client import TMDbAPIError, TMDbAuthenticationError
from moviekit.tmdb_provider_backend import TMDbProviderBackend


class FakeMovie:
    def __init__(self, tmdb_id=None):
        self.tmdb_id = tmdb_id


class FakeTMDbClient:
    def __init__(self, response=None, error=None):
        self.response = response or {}
        self.error = error
        self.paths = []

    def get_json(self, path: str, params=None) -> dict:
        self.paths.append(path)
        if self.error is not None:
            raise self.error

        return self.response


class TMDbProviderBackendTests(unittest.TestCase):
    def test_backend_name(self) -> None:
        backend = TMDbProviderBackend(client=FakeTMDbClient())

        self.assertEqual(backend.backend_name(), "tmdb")

    def test_successful_us_provider_response(self) -> None:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(
                self._response(
                    "US",
                    flatrate=[
                        {"provider_name": "Prime Video"},
                        {"provider_name": "Hulu"},
                    ],
                )
            )
        )

        availability = backend.search_movie_availability(FakeMovie(tmdb_id=949))

        self.assertEqual(
            availability,
            [
                ProviderAvailability(
                    provider_name="Prime Video",
                    country_code="US",
                    access_type="subscription",
                ),
                ProviderAvailability(
                    provider_name="Hulu",
                    country_code="US",
                    access_type="subscription",
                ),
            ],
        )
        self.assertEqual(
            backend.client.paths,
            ["movie/949/watch/providers"],
        )

    def test_configurable_country_selection(self) -> None:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(
                {
                    "results": {
                        "US": {
                            "flatrate": [{"provider_name": "Hulu"}],
                        },
                        "FR": {
                            "flatrate": [{"provider_name": "LaCinetek"}],
                        },
                    }
                }
            ),
            country_code="fr",
        )

        availability = backend.search_movie_availability(FakeMovie(tmdb_id=123))

        self.assertEqual(
            availability,
            [
                ProviderAvailability(
                    provider_name="LaCinetek",
                    country_code="FR",
                    access_type="subscription",
                )
            ],
        )

    def test_subscription_mapping(self) -> None:
        availability = self._availability_for_category("flatrate")

        self.assertEqual(availability[0].access_type, "subscription")

    def test_free_mapping(self) -> None:
        availability = self._availability_for_category("free")

        self.assertEqual(availability[0].access_type, "free")

    def test_ads_mapping(self) -> None:
        availability = self._availability_for_category("ads")

        self.assertEqual(availability[0].access_type, "ads")

    def test_rent_mapping(self) -> None:
        availability = self._availability_for_category("rent")

        self.assertEqual(availability[0].access_type, "rent")

    def test_buy_mapping(self) -> None:
        availability = self._availability_for_category("buy")

        self.assertEqual(availability[0].access_type, "buy")

    def test_one_provider_in_multiple_access_categories(self) -> None:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(
                self._response(
                    "US",
                    flatrate=[{"provider_name": "Prime Video"}],
                    rent=[{"provider_name": "Prime Video"}],
                )
            )
        )

        availability = backend.search_movie_availability(FakeMovie(tmdb_id=949))

        self.assertEqual(
            availability,
            [
                ProviderAvailability(
                    provider_name="Prime Video",
                    country_code="US",
                    access_type="subscription",
                ),
                ProviderAvailability(
                    provider_name="Prime Video",
                    country_code="US",
                    access_type="rent",
                ),
            ],
        )

    def test_missing_tmdb_id_returns_empty_availability(self) -> None:
        client = FakeTMDbClient(
            self._response("US", flatrate=[{"provider_name": "Hulu"}])
        )
        backend = TMDbProviderBackend(client=client)

        self.assertEqual(backend.search_movie_availability(FakeMovie()), [])
        self.assertEqual(backend.search_movie_availability(object()), [])
        self.assertEqual(client.paths, [])

    def test_no_provider_results_returns_empty_availability(self) -> None:
        backend = TMDbProviderBackend(client=FakeTMDbClient({"results": {}}))

        self.assertEqual(backend.search_movie_availability(FakeMovie(tmdb_id=949)), [])

    def test_country_absent_from_response_returns_empty_availability(self) -> None:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(
                self._response("GB", flatrate=[{"provider_name": "BBC"}])
            )
        )

        self.assertEqual(backend.search_movie_availability(FakeMovie(tmdb_id=949)), [])

    def test_malformed_provider_entries_are_ignored(self) -> None:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(
                self._response(
                    "US",
                    flatrate=[
                        {"provider_name": "Hulu"},
                        {},
                        {"provider_name": ""},
                        {"provider_name": None},
                        "not-a-provider-record",
                    ],
                    mystery=[{"provider_name": "Ignored"}],
                    rent={"provider_name": "Malformed category"},
                )
            )
        )

        availability = backend.search_movie_availability(FakeMovie(tmdb_id=949))

        self.assertEqual(
            availability,
            [
                ProviderAvailability(
                    provider_name="Hulu",
                    country_code="US",
                    access_type="subscription",
                )
            ],
        )

    def test_api_client_failure_is_propagated(self) -> None:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(error=TMDbAPIError("TMDb request failed"))
        )

        with self.assertRaises(TMDbAPIError):
            backend.search_movie_availability(FakeMovie(tmdb_id=949))

    def test_authentication_failure_is_propagated(self) -> None:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(
                error=TMDbAuthenticationError("TMDb authentication failed")
            )
        )

        with self.assertRaises(TMDbAuthenticationError):
            backend.search_movie_availability(FakeMovie(tmdb_id=949))

    def test_provider_service_search_movie_availability_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = TMDbProviderBackend(
                client=FakeTMDbClient(
                    self._response(
                        "US",
                        flatrate=[{"provider_name": "Amazon Prime Video"}],
                    )
                )
            )
            service = ProviderService(Path(directory) / "movies.db", backend=backend)

            availability = service.search_movie_availability(FakeMovie(tmdb_id=949))

            self.assertEqual(
                availability,
                [
                    ProviderAvailability(
                        provider_name="Prime",
                        country_code="US",
                        access_type="subscription",
                    )
                ],
            )

    def _availability_for_category(self, category: str) -> list[ProviderAvailability]:
        backend = TMDbProviderBackend(
            client=FakeTMDbClient(
                self._response(category=category, providers=[{"provider_name": "Hulu"}])
            )
        )

        return backend.search_movie_availability(FakeMovie(tmdb_id=949))

    def _response(
        self,
        country_code: str = "US",
        category: str | None = None,
        providers: list[dict] | None = None,
        **availability,
    ) -> dict:
        if category is not None:
            availability[category] = providers or []

        return {
            "results": {
                country_code: availability,
            }
        }


if __name__ == "__main__":
    unittest.main()
