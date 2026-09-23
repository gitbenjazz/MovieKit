from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moviekit.personal_library_repository import (
    Account,
    AccountRecord,
    LikeRecord,
    PersonalLibraryRepository,
    PersonalMovie,
    PersonalMovieRecord,
    RatingRecord,
    ReviewRecord,
    WatchEventRecord,
)


class PersonalLibraryRepositoryTests(unittest.TestCase):
    def test_upsert_and_find_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)

            account = repository.upsert_account(
                AccountRecord(
                    source="letterboxd",
                    username="hatim",
                    display_name="Hatim",
                    profile_url="https://letterboxd.com/hatim/",
                )
            )
            found = repository.find_account("letterboxd", "hatim")

        self.assertIsInstance(account, Account)
        self.assertEqual(found, account)

    def test_upsert_account_updates_existing_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)

            first = repository.upsert_account(
                AccountRecord(source="letterboxd", username="hatim")
            )
            second = repository.upsert_account(
                AccountRecord(
                    source="letterboxd",
                    username="hatim",
                    display_name="Updated",
                )
            )
            account_count = self._count(directory, "accounts")

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.display_name, "Updated")
        self.assertEqual(account_count, 1)

    def test_find_account_returns_none_for_missing_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)

            account = repository.find_account("letterboxd", "missing")

        self.assertIsNone(account)

    def test_upsert_and_find_personal_movie_by_letterboxd_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            account = self._account(repository)

            movie = repository.upsert_personal_movie(
                PersonalMovieRecord(
                    account_id=account.id,
                    title="Heat",
                    year=1995,
                    letterboxd_url="https://letterboxd.com/film/heat-1995/",
                )
            )
            found = repository.find_personal_movie(
                account.id,
                letterboxd_url="https://letterboxd.com/film/heat-1995/",
            )

        self.assertIsInstance(movie, PersonalMovie)
        self.assertEqual(found, movie)

    def test_upsert_personal_movie_updates_existing_by_letterboxd_uri(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            account = self._account(repository)

            first = repository.upsert_personal_movie(
                PersonalMovieRecord(
                    account_id=account.id,
                    title="Heat",
                    letterboxd_uri="https://boxd.it/29FA",
                )
            )
            second = repository.upsert_personal_movie(
                PersonalMovieRecord(
                    account_id=account.id,
                    title="Heat",
                    year=1995,
                    letterboxd_url="https://letterboxd.com/film/heat-1995/",
                    letterboxd_uri="https://boxd.it/29FA",
                )
            )
            personal_movie_count = self._count(directory, "personal_movies")

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.year, 1995)
        self.assertEqual(
            second.letterboxd_url,
            "https://letterboxd.com/film/heat-1995/",
        )
        self.assertEqual(personal_movie_count, 1)

    def test_upsert_personal_movie_rejects_missing_external_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            account = self._account(repository)

            with self.assertRaises(sqlite3.IntegrityError):
                repository.upsert_personal_movie(
                    PersonalMovieRecord(account_id=account.id, title="Heat")
                )
            personal_movie_count = self._count(directory, "personal_movies")

        self.assertEqual(personal_movie_count, 0)

    def test_link_personal_movie_to_canonical_movie(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            account = self._account(repository)
            canonical_movie_id = self._insert_canonical_movie(directory)
            personal_movie = self._personal_movie(repository, account.id)

            linked = repository.link_personal_movie_to_canonical(
                personal_movie.id,
                canonical_movie_id,
            )

        self.assertEqual(linked.canonical_movie_id, canonical_movie_id)

    def test_link_personal_movie_to_missing_canonical_movie_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            account = self._account(repository)
            personal_movie = self._personal_movie(repository, account.id)

            with self.assertRaises(sqlite3.IntegrityError):
                repository.link_personal_movie_to_canonical(
                    personal_movie.id,
                    999,
                )

    def test_save_watch_events_inserts_and_updates_by_letterboxd_uri(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)

            first = repository.save_watch_events(
                [
                    WatchEventRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        watched_date="2026-07-01",
                        letterboxd_uri="https://boxd.it/watch",
                    )
                ]
            )[0]
            second = repository.save_watch_events(
                [
                    WatchEventRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        watched_date="2026-07-02",
                        letterboxd_uri="https://boxd.it/watch",
                        is_rewatch=True,
                    )
                ]
            )[0]
            events = repository.get_watch_events(account.id)

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].watched_date, "2026-07-02")
        self.assertTrue(events[0].is_rewatch)

    def test_save_ratings_upserts_current_rating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)

            repository.save_ratings(
                [
                    RatingRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        rating=3.5,
                    )
                ]
            )
            ratings = repository.save_ratings(
                [
                    RatingRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        rating=4.5,
                        rated_at="2026-07-03",
                    )
                ]
            )
            rating = repository.get_rating(account.id, movie.id)
            rating_count = self._count(directory, "ratings")

        self.assertEqual(len(ratings), 1)
        self.assertEqual(rating.rating, 4.5)
        self.assertEqual(rating.rated_at, "2026-07-03")
        self.assertEqual(rating_count, 1)

    def test_save_reviews_inserts_and_updates_by_review_uri(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)

            first = repository.save_reviews(
                [
                    ReviewRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        review_uri="https://letterboxd.com/hatim/film/heat/review/",
                        review_text="Good.",
                    )
                ]
            )[0]
            second = repository.save_reviews(
                [
                    ReviewRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        review_uri="https://letterboxd.com/hatim/film/heat/review/",
                        review_text="Great.",
                        rating=4.5,
                    )
                ]
            )[0]
            reviews = repository.get_reviews(account.id, movie.id)

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].review_text, "Great.")
        self.assertEqual(reviews[0].rating, 4.5)

    def test_save_likes_upserts_like(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)

            repository.save_likes(
                [
                    LikeRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        liked_at="2026-07-01",
                    )
                ]
            )
            likes = repository.save_likes(
                [
                    LikeRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        liked_at="2026-07-02",
                        source_uri="https://boxd.it/like",
                    )
                ]
            )
            like = repository.get_like(account.id, movie.id)
            like_count = self._count(directory, "likes")

        self.assertEqual(len(likes), 1)
        self.assertEqual(like.liked_at, "2026-07-02")
        self.assertEqual(like.source_uri, "https://boxd.it/like")
        self.assertEqual(like_count, 1)

    def test_get_personal_library_returns_normalized_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)
            watch_event = repository.save_watch_events(
                [
                    WatchEventRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        letterboxd_uri="https://boxd.it/watch",
                    )
                ]
            )[0]
            repository.save_ratings(
                [RatingRecord(account_id=account.id, personal_movie_id=movie.id, rating=5)]
            )
            repository.save_reviews(
                [
                    ReviewRecord(
                        account_id=account.id,
                        personal_movie_id=movie.id,
                        watch_event_id=watch_event.id,
                        review_uri="https://letterboxd.com/hatim/film/heat/review/",
                    )
                ]
            )
            repository.save_likes(
                [LikeRecord(account_id=account.id, personal_movie_id=movie.id)]
            )

            library = repository.get_personal_library(account.id)

        self.assertEqual(library.account, account)
        self.assertEqual(library.movies, [movie])
        self.assertEqual(len(library.watch_events), 1)
        self.assertEqual(len(library.ratings), 1)
        self.assertEqual(len(library.reviews), 1)
        self.assertEqual(len(library.likes), 1)

    def test_get_personal_library_returns_none_for_missing_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)

            library = repository.get_personal_library(999)

        self.assertIsNone(library)

    def test_foreign_keys_prevent_activity_for_wrong_account_movie_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self._repository(directory)
            first_account = self._account(repository)
            second_account = repository.upsert_account(
                AccountRecord(source="letterboxd", username="other")
            )
            movie = self._personal_movie(repository, first_account.id)

            with self.assertRaises(sqlite3.IntegrityError):
                repository.save_ratings(
                    [
                        RatingRecord(
                            account_id=second_account.id,
                            personal_movie_id=movie.id,
                            rating=4.0,
                        )
                    ]
                )

    def test_watch_event_batch_rolls_back_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)

            with self.assertRaises(sqlite3.IntegrityError):
                repository.save_watch_events(
                    [
                        WatchEventRecord(
                            account_id=account.id,
                            personal_movie_id=movie.id,
                            letterboxd_uri="https://boxd.it/good",
                        ),
                        WatchEventRecord(
                            account_id=999,
                            personal_movie_id=movie.id,
                            letterboxd_uri="https://boxd.it/bad",
                        ),
                    ]
                )

            events = repository.get_watch_events(account.id)
            watch_event_count = self._count(directory, "watch_events")

        self.assertEqual(events, [])
        self.assertEqual(watch_event_count, 0)

    def test_review_cannot_reference_another_movies_event(self):
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)
            other = repository.upsert_personal_movie(PersonalMovieRecord(
                account_id=account.id, title="Other", letterboxd_uri="https://boxd.it/other"
            ))
            event = repository.save_watch_events([WatchEventRecord(
                account.id, other.id, letterboxd_uri="https://boxd.it/event"
            )])[0]
            with self.assertRaises(sqlite3.IntegrityError):
                repository.save_reviews([ReviewRecord(
                    account.id, movie.id, watch_event_id=event.id, review_uri="review"
                )])
            self.assertEqual(repository.get_reviews(account.id), [])

    def test_conflicting_identities_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)
            repository.upsert_personal_movie(PersonalMovieRecord(
                account.id, "Other", letterboxd_uri="https://boxd.it/other"
            ))
            with self.assertRaises(sqlite3.IntegrityError):
                repository.upsert_personal_movie(PersonalMovieRecord(
                    account.id, "Conflict", letterboxd_url=movie.letterboxd_url,
                    letterboxd_uri="https://boxd.it/other"
                ))
            self.assertEqual(len(repository.get_personal_movies(account.id)), 2)

    def test_partial_identity_update_preserves_known_url(self):
        with tempfile.TemporaryDirectory() as directory:
            repository, account, movie = self._library_subject(directory)
            movie = repository.upsert_personal_movie(PersonalMovieRecord(
                account.id, "Heat", letterboxd_url=movie.letterboxd_url,
                letterboxd_uri="https://boxd.it/heat"
            ))
            updated = repository.upsert_personal_movie(PersonalMovieRecord(
                account.id, "Heat updated", letterboxd_uri="https://boxd.it/heat"
            ))
            self.assertEqual(updated.id, movie.id)
            self.assertEqual(updated.letterboxd_url, movie.letterboxd_url)

    def _repository(self, directory: str) -> PersonalLibraryRepository:
        return PersonalLibraryRepository(Path(directory) / "movies.db")

    def _account(self, repository: PersonalLibraryRepository) -> Account:
        return repository.upsert_account(
            AccountRecord(source="letterboxd", username="hatim")
        )

    def _personal_movie(
        self,
        repository: PersonalLibraryRepository,
        account_id: int,
    ) -> PersonalMovie:
        return repository.upsert_personal_movie(
            PersonalMovieRecord(
                account_id=account_id,
                title="Heat",
                year=1995,
                letterboxd_url="https://letterboxd.com/film/heat-1995/",
            )
        )

    def _library_subject(
        self,
        directory: str,
    ) -> tuple[PersonalLibraryRepository, Account, PersonalMovie]:
        repository = self._repository(directory)
        account = self._account(repository)
        movie = self._personal_movie(repository, account.id)
        return repository, account, movie

    def _insert_canonical_movie(self, directory: str) -> int:
        with closing(sqlite3.connect(Path(directory) / "movies.db")) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO movies (
                        title,
                        year,
                        letterboxd_url
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        "Heat",
                        1995,
                        "https://letterboxd.com/film/heat-1995/",
                    ),
                )
                return int(cursor.lastrowid)

    def _count(self, directory: str, table: str) -> int:
        with closing(sqlite3.connect(Path(directory) / "movies.db")) as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
