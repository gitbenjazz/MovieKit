from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.provider_backend import NullProviderBackend, ProviderAvailability


class NullProviderBackendTests(unittest.TestCase):
    def test_null_provider_backend_returns_empty_availability(self) -> None:
        backend = NullProviderBackend()

        self.assertEqual(backend.search_movie_availability(object()), [])

    def test_null_provider_backend_has_stable_name(self) -> None:
        backend = NullProviderBackend()

        self.assertEqual(backend.backend_name(), "null")

    def test_provider_availability_defaults_match_database_defaults(self) -> None:
        availability = ProviderAvailability(provider_name="Prime")

        self.assertEqual(availability.provider_name, "Prime")
        self.assertEqual(availability.country_code, "US")
        self.assertEqual(availability.access_type, "flatrate")
        self.assertIsNone(availability.fetched_at)


if __name__ == "__main__":
    unittest.main()
