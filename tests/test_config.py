from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.config import (
    MovieKitConfig,
    config_path,
    get_acceptable_providers,
    get_favorite_providers,
    load_config,
    save_config,
)


class ConfigTests(unittest.TestCase):
    def test_config_path_uses_user_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)

            with patch("pathlib.Path.home", return_value=home):
                path = config_path()

        self.assertEqual(path, home / ".config" / "moviekit" / "config.toml")

    def test_load_config_creates_default_file_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)

            with patch("pathlib.Path.home", return_value=home):
                config = load_config()
                path = config_path()

                self.assertEqual(config, MovieKitConfig())
                self.assertTrue(path.exists())
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    'database_path = "movies.db"\n'
                    "default_search_limit = 20\n"
                    'favorite_providers = ""\n'
                    'acceptable_providers = ""\n',
                )

    def test_save_config_writes_toml_and_load_config_reads_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                database_path='custom "movies".db',
                default_search_limit=7,
                favorite_providers="Prime,YouTube",
                acceptable_providers="Tubi,Pluto TV",
            )

            with patch("pathlib.Path.home", return_value=home):
                path = save_config(config)
                loaded = load_config()

                self.assertEqual(path, config_path())
                self.assertEqual(loaded, config)
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    'database_path = "custom \\"movies\\".db"\n'
                    "default_search_limit = 7\n"
                    'favorite_providers = "Prime,YouTube"\n'
                    'acceptable_providers = "Tubi,Pluto TV"\n',
                )

    def test_load_config_uses_defaults_for_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / ".config" / "moviekit" / "config.toml"
            path.parent.mkdir(parents=True)
            path.write_text('database_path = "other.db"\n', encoding="utf-8")

            with patch("pathlib.Path.home", return_value=home):
                config = load_config()

        self.assertEqual(
            config,
            MovieKitConfig(
                database_path="other.db",
                default_search_limit=20,
                favorite_providers="",
                acceptable_providers="",
            ),
        )

    def test_load_config_ignores_unknown_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / ".config" / "moviekit" / "config.toml"
            path.parent.mkdir(parents=True)
            path.write_text(
                "\n".join(
                    [
                        'database_path = "movies.db"',
                        "default_search_limit = 3",
                        'future_value = "ignored"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("pathlib.Path.home", return_value=home):
                config = load_config()

        self.assertEqual(
            config,
            MovieKitConfig(
                database_path="movies.db",
                default_search_limit=3,
                favorite_providers="",
                acceptable_providers="",
            ),
        )

    def test_provider_helpers_return_empty_lists_for_missing_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / ".config" / "moviekit" / "config.toml"
            path.parent.mkdir(parents=True)
            path.write_text(
                "\n".join(
                    [
                        'database_path = "movies.db"',
                        "default_search_limit = 20",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("pathlib.Path.home", return_value=home):
                self.assertEqual(get_favorite_providers(), [])
                self.assertEqual(get_acceptable_providers(), [])

    def test_provider_helpers_return_empty_lists_for_empty_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                favorite_providers="",
                acceptable_providers="",
            )

            with patch("pathlib.Path.home", return_value=home):
                save_config(config)

                self.assertEqual(get_favorite_providers(), [])
                self.assertEqual(get_acceptable_providers(), [])

    def test_provider_helpers_parse_one_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                favorite_providers="Prime",
                acceptable_providers="Tubi",
            )

            with patch("pathlib.Path.home", return_value=home):
                save_config(config)

                self.assertEqual(get_favorite_providers(), ["Prime"])
                self.assertEqual(get_acceptable_providers(), ["Tubi"])

    def test_provider_helpers_parse_multiple_providers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                favorite_providers="Prime,YouTube,LaCinetek",
                acceptable_providers="Tubi,Pluto TV,Plex",
            )

            with patch("pathlib.Path.home", return_value=home):
                save_config(config)

                self.assertEqual(
                    get_favorite_providers(),
                    ["Prime", "YouTube", "LaCinetek"],
                )
                self.assertEqual(
                    get_acceptable_providers(),
                    ["Tubi", "Pluto TV", "Plex"],
                )

    def test_provider_helpers_strip_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                favorite_providers="Prime, YouTube , LaCinetek ",
                acceptable_providers=" Tubi , Pluto TV, Plex ",
            )

            with patch("pathlib.Path.home", return_value=home):
                save_config(config)

                self.assertEqual(
                    get_favorite_providers(),
                    ["Prime", "YouTube", "LaCinetek"],
                )
                self.assertEqual(
                    get_acceptable_providers(),
                    ["Tubi", "Pluto TV", "Plex"],
                )

    def test_provider_helpers_ignore_empty_entries_and_trailing_commas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                favorite_providers="Prime,,YouTube,",
                acceptable_providers="Tubi,,Plex,",
            )

            with patch("pathlib.Path.home", return_value=home):
                save_config(config)

                self.assertEqual(get_favorite_providers(), ["Prime", "YouTube"])
                self.assertEqual(get_acceptable_providers(), ["Tubi", "Plex"])

    def test_provider_helpers_preserve_duplicate_provider_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                favorite_providers="Prime,Prime,YouTube",
                acceptable_providers="Tubi,Tubi,Plex",
            )

            with patch("pathlib.Path.home", return_value=home):
                save_config(config)

                self.assertEqual(
                    get_favorite_providers(),
                    ["Prime", "Prime", "YouTube"],
                )
                self.assertEqual(
                    get_acceptable_providers(),
                    ["Tubi", "Tubi", "Plex"],
                )


if __name__ == "__main__":
    unittest.main()
