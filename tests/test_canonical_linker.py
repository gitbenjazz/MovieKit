import unittest

from moviekit.canonical_linker import CanonicalMovieLinker, LinkState
from moviekit.database_repository import MovieSyncTarget
from moviekit.personal_library_models import MovieIdentity


class CanonicalLinkerTests(unittest.TestCase):
    def setUp(self):
        self.movies = [
            MovieSyncTarget(1, "A Film", 2000, "https://letterboxd.com/film/a-film/", 10),
            MovieSyncTarget(2, "A Film", 2010, "https://letterboxd.com/film/a-film-2010/", 20),
        ]
        self.linker = CanonicalMovieLinker(self.movies)

    def test_url_stronger_than_title_or_year(self):
        result = self.linker.match(MovieIdentity("Changed", 1900,
            "http://www.letterboxd.com/film/a-film?x=1"))
        self.assertEqual(result.canonical_movie_id, 1)
        self.assertEqual(result.method, "letterboxd")

    def test_user_entry_slug_matches_film(self):
        result = self.linker.match(MovieIdentity("Unknown", None,
            "https://letterboxd.com/member/film/a-film/2/"))
        self.assertEqual(result.canonical_movie_id, 1)

    def test_tmdb_match_and_conflicting_strong_ids(self):
        movie = MovieIdentity("Other", None, "https://boxd.it/other/")
        self.assertEqual(self.linker.match(movie, 20).canonical_movie_id, 2)
        conflict = MovieIdentity("A Film", 2000, "https://letterboxd.com/film/a-film/")
        result = self.linker.match(conflict, 20)
        self.assertEqual(result.state, LinkState.AMBIGUOUS)
        self.assertIsNone(result.canonical_movie_id)

    def test_short_uri_falls_back_to_normalized_title_and_year(self):
        result = self.linker.match(MovieIdentity(" A  FILM ", 2010, "https://boxd.it/short/"))
        self.assertEqual(result.canonical_movie_id, 2)
        self.assertEqual(result.method, "title_year")

    def test_ambiguous_title_year_never_guessed(self):
        duplicate = MovieSyncTarget(3, "a film", 2000, "https://letterboxd.com/film/another/", None)
        result = CanonicalMovieLinker([*self.movies, duplicate]).match(
            MovieIdentity("A Film", 2000, "https://boxd.it/short/"))
        self.assertEqual(result.state, LinkState.AMBIGUOUS)
        self.assertEqual(result.candidates, (1, 3))

    def test_unmatched_and_missing_year(self):
        for title, year in [("Outside", 2000), ("A Film", None), ("A Film", 2001)]:
            result = self.linker.match(MovieIdentity(title, year, "https://boxd.it/x/"))
            self.assertEqual(result.state, LinkState.UNMATCHED)
        self.assertEqual(len(self.movies), 2)
