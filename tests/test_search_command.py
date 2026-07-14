from __future__ import annotations

from contextlib import closing, redirect_stdout
from pathlib import Path
import sqlite3
import sys
import tempfile
from io import StringIO
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit import cli
from moviekit.database_repository import (
    DatabaseRepository,
    MovieCredit,
    MovieDetails,
    MovieSummary,
)
from moviekit.models import MovieRecord, WatchedRecord
from moviekit.recommendation_engine import Recommendation
from moviekit.search_service import MovieSearchResult, SearchService


class SearchCommandTests(unittest.TestCase):
    def test_parser_registers_search_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["search", "heat"])

        self.assertEqual(args.text, "heat")
        self.assertEqual(args.limit, 20)
        self.assertFalse(args.watched)
        self.assertFalse(args.unwatched)
        self.assertIs(args.func, cli.search)

    def test_parser_accepts_search_limit_and_filters(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["search", "heat", "--limit", "5", "--watched"])

        self.assertEqual(args.limit, 5)
        self.assertTrue(args.watched)
        self.assertFalse(args.unwatched)

    def test_parser_registers_tonight_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["tonight"])

        self.assertIs(args.func, cli.tonight)

    def test_search_command_prints_friendly_message_for_no_results(self) -> None:
        with patch("moviekit.search_service.SearchService") as search_service:
            search_service.return_value.search.return_value = []
            output = StringIO()

            with redirect_stdout(output):
                exit_code = cli.search(
                    cli.argparse.Namespace(
                        text="missing",
                        limit=20,
                        watched=False,
                        unwatched=False,
                    )
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), 'No movies found for "missing".\n')

    def test_search_command_prints_result_fields(self) -> None:
        result = MovieSearchResult(
            movie=MovieSummary(
                id=1,
                title="Heat",
                year=1995,
                letterboxd_url="https://letterboxd.com/film/heat-1995/",
                tmdb_id=949,
                tmdb_title="Heat",
                rating=None,
                runtime=None,
            ),
            watched=True,
        )

        with patch("moviekit.search_service.SearchService") as search_service:
            search_service.return_value.search.return_value = [result]
            output = StringIO()

            with redirect_stdout(output):
                exit_code = cli.search(
                    cli.argparse.Namespace(
                        text="heat",
                        limit=20,
                        watched=False,
                        unwatched=False,
                    )
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            output.getvalue(),
            "\n".join(
                [
                    "[Heat]",
                    "Year: 1995",
                    "Status: Watched",
                    "TMDB ID: 949",
                    "Letterboxd URL: https://letterboxd.com/film/heat-1995/",
                    "",
                ]
            ),
        )

    def test_tonight_command_prints_random_unwatched_movie_details(self) -> None:
        summary = MovieSummary(
            id=7,
            title="Everything Everywhere All at Once",
            year=2022,
            letterboxd_url=(
                "https://letterboxd.com/film/everything-everywhere-all-at-once/"
            ),
            tmdb_id=545611,
            tmdb_title="Everything Everywhere All at Once",
            rating=8.0,
            runtime=139,
        )
        details = MovieDetails(
            id=7,
            title="Everything Everywhere All at Once",
            year=2022,
            letterboxd_url=(
                "https://letterboxd.com/film/everything-everywhere-all-at-once/"
            ),
            tmdb_id=545611,
            tmdb_title="Everything Everywhere All at Once",
            rating=8.0,
            runtime=139,
            genres=["Action", "Comedy", "Sci-Fi"],
            credits=[
                MovieCredit(
                    person_id=1,
                    name="Daniel Kwan",
                    role="director",
                    billing_order=1,
                ),
                MovieCredit(
                    person_id=2,
                    name="Daniel Scheinert",
                    role="director",
                    billing_order=2,
                ),
            ],
        )

        with patch("moviekit.recommendation_engine.RecommendationEngine") as engine:
            engine.return_value.recommend_tonight.return_value = Recommendation(
                movie=details,
                score=0,
                reasons=["Random unwatched movie"],
                provider="Prime",
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = cli.tonight(cli.argparse.Namespace())

        self.assertEqual(exit_code, 0)
        engine.return_value.recommend_tonight.assert_called_once_with()
        self.assertEqual(
            output.getvalue(),
            "\n".join(
                [
                    "🎬 Tonight's Movie",
                    "────────────────────────────────",
                    "",
                    "Everything Everywhere All at Once (2022)",
                    "",
                    "⭐ TMDb Rating : 8.0",
                    "⏱ Runtime     : 139 min",
                    "🎬 Director    : Daniel Kwan, Daniel Scheinert",
                    "🎭 Genres      : Action, Comedy, Sci-Fi",
                    "📺 Provider    : Prime",
                    "",
                    "🔗 Letterboxd",
                    "https://letterboxd.com/film/everything-everywhere-all-at-once/",
                    "",
                ]
            ),
        )

    def test_tonight_command_prints_message_for_empty_library(self) -> None:
        with patch("moviekit.recommendation_engine.RecommendationEngine") as engine:
            engine.return_value.recommend_tonight.return_value = None
            output = StringIO()

            with redirect_stdout(output):
                exit_code = cli.tonight(cli.argparse.Namespace())

        self.assertEqual(exit_code, 0)
        engine.return_value.recommend_tonight.assert_called_once_with()
        self.assertEqual(output.getvalue(), "No unwatched movies found.\n")

    def test_tonight_command_omits_unknown_fields(self) -> None:
        summary = MovieSummary(
            id=8,
            title="American Gangster",
            year=2007,
            letterboxd_url="https://letterboxd.com/film/american-gangster/",
            tmdb_id=None,
            tmdb_title=None,
            rating=None,
            runtime=157,
        )
        details = MovieDetails(
            id=8,
            title="American Gangster",
            year=2007,
            letterboxd_url="https://letterboxd.com/film/american-gangster/",
            tmdb_id=None,
            tmdb_title=None,
            rating=None,
            runtime=157,
            genres=[],
            credits=[
                MovieCredit(
                    person_id=1,
                    name="Unknown",
                    role="director",
                    billing_order=1,
                )
            ],
        )

        with patch("moviekit.recommendation_engine.RecommendationEngine") as engine:
            engine.return_value.recommend_tonight.return_value = Recommendation(
                movie=details,
                score=0,
                reasons=["Random unwatched movie"],
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = cli.tonight(cli.argparse.Namespace())

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            output.getvalue(),
            "\n".join(
                [
                    "🎬 Tonight's Movie",
                    "────────────────────────────────",
                    "",
                    "American Gangster (2007)",
                    "",
                    "⏱ Runtime     : 157 min",
                    "",
                    "🔗 Letterboxd",
                    "https://letterboxd.com/film/american-gangster/",
                    "",
                ]
            ),
        )

    def test_tonight_command_formats_database_title_for_display(self) -> None:
        summary = MovieSummary(
            id=9,
            title="i know where i'm going!",
            year=1945,
            letterboxd_url="https://letterboxd.com/film/i-know-where-im-going/",
            tmdb_id=None,
            tmdb_title=None,
            rating=None,
            runtime=None,
        )
        details = MovieDetails(
            id=9,
            title="i know where i'm going!",
            year=1945,
            letterboxd_url="https://letterboxd.com/film/i-know-where-im-going/",
            tmdb_id=None,
            tmdb_title=None,
            rating=None,
            runtime=None,
            genres=[],
            credits=[],
        )

        with patch("moviekit.recommendation_engine.RecommendationEngine") as engine:
            engine.return_value.recommend_tonight.return_value = Recommendation(
                movie=details,
                score=0,
                reasons=["Random unwatched movie"],
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = cli.tonight(cli.argparse.Namespace())

        self.assertEqual(exit_code, 0)
        self.assertIn("I Know Where I'm Going! (1945)", output.getvalue())

    def test_search_service_sorts_by_match_then_year_and_marks_watched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title="Heat",
                        year=1995,
                        letterboxd_url="https://letterboxd.com/film/heat-1995/",
                        tmdb_id=949,
                    ),
                    MovieRecord(
                        title="Heat",
                        year=1986,
                        letterboxd_url="https://letterboxd.com/film/heat-1986/",
                    ),
                    MovieRecord(
                        title="The Heat",
                        year=2013,
                        letterboxd_url="https://letterboxd.com/film/the-heat/",
                    ),
                ]
            )
            repository.save_watched(
                [
                    WatchedRecord(
                        title="Heat",
                        year=1995,
                        watched_date="2026-07-11",
                        letterboxd_uri="https://letterboxd.com/film/heat-1995/",
                    )
                ]
            )

            results = SearchService(repository).search("heat")

        self.assertEqual([result.movie.year for result in results], [1986, 1995, 2013])
        self.assertEqual(
            [result.watched for result in results],
            [False, True, False],
        )

    def test_search_service_supports_case_insensitive_partial_limit_and_filter(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = DatabaseRepository(Path(directory) / "movies.db")
            repository.save_movies(
                [
                    MovieRecord(
                        title="Before Sunrise",
                        year=1995,
                        letterboxd_url="https://letterboxd.com/film/before-sunrise/",
                    ),
                    MovieRecord(
                        title="Before Sunset",
                        year=2004,
                        letterboxd_url="https://letterboxd.com/film/before-sunset/",
                    ),
                    MovieRecord(
                        title="Before Midnight",
                        year=2013,
                        letterboxd_url="https://letterboxd.com/film/before-midnight/",
                    ),
                ]
            )
            repository.save_watched(
                [
                    WatchedRecord(
                        title="Before Sunrise",
                        year=1995,
                        watched_date="2026-07-12",
                        letterboxd_uri="https://letterboxd.com/film/before-sunrise/",
                    )
                ]
            )

            results = SearchService(repository).search(
                "BEFORE",
                limit=1,
                watched=False,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].movie.title, "Before Sunset")
        self.assertFalse(results[0].watched)

    def test_godfather_part_ii_short_watched_uri_marks_canonical_movie_watched(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "movies.db"
            repository = DatabaseRepository(database_path)
            repository.save_movies(
                [
                    MovieRecord(
                        title="the godfather part ii",
                        year=1974,
                        letterboxd_url=(
                            "https://letterboxd.com/film/the-godfather-part-ii/"
                        ),
                    )
                ]
            )
            with closing(sqlite3.connect(database_path)) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO movies (
                            title,
                            year,
                            letterboxd_url
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            "The Godfather Part II",
                            1974,
                            "https://boxd.it/2aNq",
                        ),
                    )
            repository.save_watched(
                [
                    WatchedRecord(
                        title="The Godfather Part II",
                        year=1974,
                        watched_date="2020-08-26",
                        letterboxd_uri="https://boxd.it/2aNq",
                    ),
                    WatchedRecord(
                        title="The Godfather Part II",
                        year=1974,
                        watched_date="2020-08-27",
                        letterboxd_uri="https://boxd.it/2aNq",
                    ),
                ]
            )

            results = SearchService(repository).search("godfather")
            with closing(sqlite3.connect(database_path)) as connection:
                watched_rows = connection.execute(
                    """
                    SELECT watched.movie_id, movies.letterboxd_url
                    FROM watched
                    JOIN movies
                        ON movies.id = watched.movie_id
                    WHERE movies.title = 'the godfather part ii'
                    ORDER BY watched.id
                    """
                ).fetchall()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].movie.title, "the godfather part ii")
        self.assertTrue(results[0].watched)
        self.assertEqual(len(watched_rows), 2)
        self.assertEqual(
            {row[1] for row in watched_rows},
            {"https://letterboxd.com/film/the-godfather-part-ii/"},
        )


if __name__ == "__main__":
    unittest.main()
