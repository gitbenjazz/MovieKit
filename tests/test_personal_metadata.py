from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from moviekit import cli
from moviekit.config import MovieKitConfig
from moviekit.database import initialize_database
from moviekit.database_repository import DatabaseRepository
from moviekit.models import MovieRecord
from moviekit.personal_analytics_repository import PersonalAnalyticsRepository
from moviekit.personal_analytics_service import PersonalAnalyticsService
from moviekit.personal_library_models import AccountRecord, PersonalMovieRecord, RatingRecord
from moviekit.personal_metadata_repository import PersonalMetadataRepository
from moviekit.personal_metadata_service import PersonalMetadataService
from moviekit.personal_preferences import PersonalPreferenceProfile
from moviekit.tmdb_client import TMDbAPIError
from tests.test_recommendation_v2 import candidate


def search(id=12, title='Outside', year=1990):
    return {'results': [{'id': id, 'title': title, 'release_date': f'{year}-01-01'}]}


def details(id=12, genres=('Drama',), directors=('Director',)):
    return {'id': id, 'title': 'Outside', 'genres': [{'name': n} for n in genres],
            'credits': {'crew': [{'job': 'Director', 'name': n} for n in directors]}}


class PersonalMetadataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'test.db'
        self.repo = PersonalMetadataRepository(self.path)
        self.account = self.repo.library.upsert_account(AccountRecord('letterboxd', 'user'))
        self.movie = self.add_movie('Outside', 1990)
        self.client = Mock()
        self.service = PersonalMetadataService(self.repo, self.client)

    def add_movie(self, title, year, canonical=None, account=None):
        return self.repo.library.upsert_personal_movie(PersonalMovieRecord(
            (account or self.account).id, title, year, f'https://letterboxd.com/film/{title}/',
            canonical_movie_id=canonical))

    def count_canonical(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute('SELECT count(*) FROM movies').fetchone()[0]

    def test_noncanonical_enrichment_is_idempotent_and_informs_preferences(self):
        self.repo.library.save_ratings([RatingRecord(self.account.id, self.movie.id, 5)])
        self.client.get_json.side_effect = [search(), details()]
        self.assertEqual(self.service.enrich(' USER ').enriched, 1)
        cached = self.repo.cached(self.movie)
        self.assertEqual(self.service.enrich('user').skipped, 1)
        self.assertEqual(self.client.get_json.call_count, 2)
        self.assertEqual(self.repo.cached(self.movie), cached)
        self.assertEqual(self.count_canonical(), 0)
        snapshot = PersonalAnalyticsRepository(self.path).snapshot('user')
        self.assertEqual(snapshot.genres, ((self.movie.id, 'Drama'),))
        self.assertEqual(snapshot.directors, ((self.movie.id, 'Director'),))
        score, reasons = PersonalPreferenceProfile(snapshot).score(candidate(99, 'Candidate', genres=['Drama']))
        self.assertTrue(any('Genre' in reason for reason in reasons))
        other = self.repo.library.upsert_account(AccountRecord('letterboxd', 'other'))
        self.assertEqual(PersonalAnalyticsRepository(self.path).snapshot(other.username).genres, ())

    def test_verified_identity_normalizes_cast_without_creating_canonical_movie(self):
        self.repo.library.save_ratings([RatingRecord(self.account.id, self.movie.id, 5)])
        response = {
            'id': 12, 'title': 'Outside', 'original_title': 'Dehors', 'release_date': '1990-01-01',
            'genres': [{'name': 'Drama'}],
            'credits': {
                'crew': [{'id': 101, 'name': 'Director', 'job': 'Director'}],
                'cast': [
                    {'id': 201, 'name': 'Lead', 'order': 0},
                    {'id': 202, 'name': 'Second', 'order': 1},
                ],
            },
        }
        self.client.get_json.side_effect = [search(), response]
        self.assertEqual(self.service.enrich('user').enriched, 1)
        cached = self.repo.cached(self.movie)
        self.assertIsNotNone(cached['identity_id'])
        self.assertEqual(self.count_canonical(), 0)
        with closing(sqlite3.connect(self.path)) as connection:
            identity = connection.execute(
                'SELECT tmdb_id, title, original_title, release_year FROM film_identities'
            ).fetchone()
            credits = connection.execute(
                """SELECT p.tmdb_person_id, p.name, c.role, c.billing_order
                   FROM identity_credits c JOIN identity_people p ON p.id = c.person_id
                   ORDER BY c.role, c.billing_order"""
            ).fetchall()
        self.assertEqual(identity, (12, 'Outside', 'Dehors', 1990))
        self.assertEqual(credits, [(201, 'Lead', 'actor', 0), (202, 'Second', 'actor', 1),
                                   (101, 'Director', 'director', None)])
        snapshot = PersonalAnalyticsRepository(self.path).snapshot('user')
        self.assertEqual(snapshot.actors, ((self.movie.id, 'Lead'), (self.movie.id, 'Second')))
        self.assertEqual(snapshot.directors, ((self.movie.id, 'Director'),))
        stats = PersonalAnalyticsService(PersonalAnalyticsRepository(self.path)).stats('user')
        self.assertEqual([(item.name, item.rated) for item in stats.actors], [('Lead', 1), ('Second', 1)])

    def test_dry_run_never_persists_resolution_or_metadata(self):
        self.client.get_json.side_effect = [search(), details()]
        result = self.service.enrich('user', dry_run=True)
        self.assertEqual((result.enriched, result.processed), (1, 1))
        self.assertIsNone(self.repo.cached(self.movie))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM film_identities').fetchone()[0], 0)

    def test_cached_legacy_metadata_is_pending_until_universal_identity_is_fetched(self):
        self.repo.save(self.movie, 'complete', 12, ['Drama'], ['Director'])
        self.client.get_json.return_value = details(12)
        result = self.service.enrich('user', limit=1)
        self.assertEqual((result.processed, result.enriched, result.metadata_pending), (1, 1, 1))
        self.client.get_json.assert_called_once_with('movie/12', params={'append_to_response': 'credits'})
        cached = self.repo.cached(self.movie)
        self.assertEqual(cached['metadata_status'], 'complete')
        self.assertIsNotNone(cached['identity_metadata_fetched_at'])

    def test_bounded_refresh_batches_advance_without_repeating_first_movie(self):
        self.add_movie('Second', 1991)
        self.client.get_json.side_effect = [search(12, 'Outside', 1990), details(12),
                                            search(13, 'Second', 1991), details(13)]
        self.assertEqual(self.service.enrich('user').enriched, 2)
        self.client.reset_mock()
        self.client.get_json.side_effect = [details(12), details(13)]
        self.assertEqual(self.service.enrich('user', refresh=True, limit=1).enriched, 1)
        self.assertEqual(self.client.get_json.call_args_list[0].args[0], 'movie/12')
        self.client.reset_mock()
        self.assertEqual(self.service.enrich('user', refresh=True, limit=1).enriched, 1)
        self.assertEqual(self.client.get_json.call_args_list[0].args[0], 'movie/13')

    def test_failed_film_is_recorded_then_next_batch_advances_to_following_film(self):
        second = self.add_movie('Second', 1991)
        self.repo.save(self.movie, 'complete', 12, ['Drama'], ['Director'])
        self.repo.save(second, 'complete', 13, ['Drama'], ['Director'])
        self.client.get_json.side_effect = [TMDbAPIError('temporary outage'), details(13)]
        first = self.service.enrich('user', limit=2)
        self.assertEqual((first.processed, first.failed, first.metadata_pending, first.remaining), (1, 1, 2, 1))
        failed = self.repo.cached(self.movie)
        self.assertEqual((failed['metadata_status'], failed['failure_category'], failed['failure_count']),
                         ('failed_retryable', 'tmdb_api', 1))
        unresolved = self.service.identities.unresolved('user')
        self.assertEqual(unresolved[0][0:3], ('Outside', 1990, 'complete'))
        self.assertEqual(unresolved[0][4:6], ('failed_retryable', 'tmdb_api'))
        second_batch = self.service.enrich('user', limit=2)
        self.assertEqual((second_batch.enriched, second_batch.cached_failed, second_batch.remaining), (1, 1, 0))
        self.assertEqual(self.repo.cached(second)['metadata_status'], 'complete')

    def test_identity_status_and_unresolved_cli_are_account_scoped(self):
        self.client.get_json.side_effect = [search(), details()]
        self.service.enrich('user')
        output = StringIO()
        config = MovieKitConfig(database_path=str(self.path))
        with patch('moviekit.config.load_config', return_value=config), redirect_stdout(output):
            args = cli.build_parser().parse_args(['personal', 'identities', '--username', 'user'])
            self.assertEqual(args.func(args), 0)
        self.assertIn('complete/complete: 1', output.getvalue())
        output = StringIO()
        with patch('moviekit.config.load_config', return_value=config), redirect_stdout(output):
            args = cli.build_parser().parse_args(['personal', 'unresolved', '--username', 'user'])
            self.assertEqual(args.func(args), 0)
        self.assertIn('No unresolved personal identities.', output.getvalue())

    def test_limit_and_resume(self):
        self.add_movie('Second', 1990)
        self.client.get_json.side_effect = [search(), details(), search(13, 'Second'), details(13)]
        first = self.service.enrich('user', limit=1)
        self.assertEqual((first.enriched, first.remaining), (1, 1))
        second = self.service.enrich('user', limit=1)
        self.assertEqual((second.enriched, second.skipped, second.remaining), (1, 1, 0))

    def test_unresolved_cached_until_explicit_retry(self):
        self.client.get_json.return_value = {'results': []}
        self.assertEqual(self.service.enrich('user').unresolved, 1)
        self.assertEqual(self.service.enrich('user').skipped, 1)
        self.assertEqual(self.client.get_json.call_count, 1)
        self.client.get_json.side_effect = [search(), details()]
        self.assertEqual(self.service.enrich('user', retry_unresolved=True).enriched, 1)

    def test_ambiguous_and_missing_year_never_fetch_details(self):
        self.add_movie('Undated', None)
        self.client.get_json.return_value = {'results': search()['results'] + search(13)['results']}
        result = self.service.enrich('user')
        self.assertEqual(result.unresolved, 2)
        self.assertEqual(self.repo.cached(self.movie)['status'], 'ambiguous')
        self.assertEqual(self.client.get_json.call_count, 1)

    def test_failure_preserves_completed_work_and_resumes(self):
        second = self.add_movie('Second', 1990)
        self.client.get_json.side_effect = [search(), details(), TMDbAPIError('TMDb request failed')]
        result = self.service.enrich('user')
        self.assertEqual((result.enriched, result.failed), (1, 1))
        self.assertIsNone(self.repo.cached(second))
        self.client.get_json.side_effect = [search(13, 'Second'), details(13)]
        self.assertEqual(self.service.enrich('user').enriched, 1)

    def test_refresh_replaces_metadata_and_uses_known_id(self):
        self.repo.save(self.movie, 'complete', 12, ['Old'], ['Old Director'])
        self.client.get_json.return_value = details(genres=(), directors=())
        self.assertEqual(self.service.enrich('user', refresh=True).enriched, 1)
        self.client.get_json.assert_called_once_with('movie/12', params={'append_to_response': 'credits'})
        self.assertEqual(PersonalAnalyticsRepository(self.path).snapshot('user').genres, ())

    def test_details_failure_resumes_without_repeating_search(self):
        self.client.get_json.side_effect = [search(), TMDbAPIError('TMDb request failed')]
        self.assertEqual(self.service.enrich('user').failed, 1)
        self.assertEqual(self.repo.cached(self.movie)['status'], 'pending')
        self.assertEqual(self.service.enrich('user').cached_failed, 1)
        self.client.get_json.reset_mock()
        self.client.get_json.side_effect = [details()]
        self.assertEqual(self.service.enrich('user', retry_failed=True).enriched, 1)
        self.client.get_json.assert_called_once_with('movie/12', params={'append_to_response': 'credits'})

    def test_malformed_refresh_retains_previous_good_data(self):
        self.repo.save(self.movie, 'complete', 12, ['Drama'], ['Director'])
        previous = self.repo.cached(self.movie)
        self.client.get_json.return_value = {'id': 12}
        self.assertEqual(self.service.enrich('user', refresh=True).failed, 1)
        current = self.repo.cached(self.movie)
        self.assertEqual((current['genres_json'], current['directors_json']),
                         (previous['genres_json'], previous['directors_json']))
        self.assertEqual((current['metadata_status'], current['failure_category']),
                         ('failed_permanent', 'metadata'))

    def test_identity_change_invalidates_cache_and_analytics(self):
        self.repo.save(self.movie, 'complete', 12, ['Drama'], ['Director'])
        updated = self.repo.library.upsert_personal_movie(PersonalMovieRecord(
            self.account.id, 'Corrected', 1991, self.movie.letterboxd_url))
        self.assertIsNone(self.repo.cached(updated))
        self.assertEqual(PersonalAnalyticsRepository(self.path).snapshot('user').genres, ())
        self.client.get_json.side_effect = [search(14, 'Corrected', 1991), details(14)]
        self.assertEqual(self.service.enrich('user').enriched, 1)

    def test_existing_canonical_metadata_is_resolved_but_fetches_universal_credits(self):
        db = DatabaseRepository(self.path)
        db.save_movies([MovieRecord('Linked', 1990, 'https://letterboxd.com/film/linked/',
                                   tmdb_id=5, genres='Comedy', director='Existing')])
        canonical = db.get_movie_by_tmdb_id(5)
        linked = self.add_movie('Linked', 1990, canonical.id)
        self.repo.save(self.movie, 'unmatched')
        before = db.get_movie_details(canonical.id)
        self.client.get_json.return_value = details(id=5, genres=('Comedy',), directors=('Existing',))
        self.assertEqual(self.service.enrich('user').enriched, 1)
        self.client.get_json.assert_called_once_with('movie/5', params={'append_to_response': 'credits'})
        self.assertEqual(self.count_canonical(), 1)
        self.assertEqual(db.get_movie_details(canonical.id), before)
        self.assertEqual(self.repo.cached(linked)['tmdb_id'], 5)

    def test_schema_v3_upgrade_preserves_personal_data_and_legacy_reads(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DROP TABLE personal_movie_metadata')
            connection.execute('PRAGMA user_version=3')
        self.assertEqual(len(PersonalAnalyticsRepository(self.path).snapshot('user').movies), 1)
        initialize_database(self.path)
        initialize_database(self.path)
        self.assertEqual(self.repo.library.get_personal_movies(self.account.id), [self.movie])
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 9)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_cli_reports_progress_and_results_and_forwards_options(self):
        self.client.get_json.side_effect = [search(), details()]
        from moviekit.application import EnrichPersonalMetadata
        output = StringIO()
        with patch('moviekit.application.EnrichPersonalMetadata', return_value=EnrichPersonalMetadata(self.service)), redirect_stdout(output):
            args = cli.build_parser().parse_args(['personal', 'enrich', '--username', 'user', '--limit', '1'])
            self.assertEqual(args.func(args), 0)
        self.assertIn('Outside (1990): complete', output.getvalue())
        self.assertIn('enriched=1', output.getvalue())
        with self.assertRaises(ValueError):
            self.service.enrich('missing')
        with self.assertRaises(ValueError):
            self.service.enrich('user', limit=0)
