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

from moviekit.config import MovieKitConfig, config_path, load_config, save_config


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
                    "default_search_limit = 20\n",
                )

    def test_save_config_writes_toml_and_load_config_reads_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = MovieKitConfig(
                database_path='custom "movies".db',
                default_search_limit=7,
            )

            with patch("pathlib.Path.home", return_value=home):
                path = save_config(config)
                loaded = load_config()

                self.assertEqual(path, config_path())
                self.assertEqual(loaded, config)
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    'database_path = "custom \\"movies\\".db"\n'
                    "default_search_limit = 7\n",
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
            ),
        )


if __name__ == "__main__":
    unittest.main()
