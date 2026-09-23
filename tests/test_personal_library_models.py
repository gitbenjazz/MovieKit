from dataclasses import FrozenInstanceError
import unittest

from moviekit.personal_library_models import (
    AccountRecord, ImportedLike, ImportedRating, ImportedReview, ImportedWatch,
    LetterboxdImport, MovieIdentity,
)
from moviekit.personal_library_repository import AccountRecord as CompatibilityAccount


class PersonalLibraryModelTests(unittest.TestCase):
    def test_import_objects_need_no_database_ids(self):
        movie = MovieIdentity("Example", 2000, "https://boxd.it/example")
        data = LetterboxdImport(
            watches=(ImportedWatch(movie, "watch"),),
            ratings=(ImportedRating(movie, 4.5),),
            reviews=(ImportedReview(movie, "review", "Text"),),
            likes=(ImportedLike(movie),),
        )
        self.assertIs(data.watches[0].movie, data.ratings[0].movie)
        self.assertFalse(hasattr(movie, "rating"))
        self.assertFalse(hasattr(movie, "liked"))
        with self.assertRaises(FrozenInstanceError):
            movie.title = "Changed"

    def test_existing_repository_imports_remain_compatible(self):
        self.assertIs(AccountRecord, CompatibilityAccount)
        self.assertEqual(LetterboxdImport().issues, ())
