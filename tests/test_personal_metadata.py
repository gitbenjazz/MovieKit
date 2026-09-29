from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from moviekit import cli
from moviekit.database import initialize_database
from moviekit.database_repository import DatabaseRepository
from moviekit.models import MovieRecord
from moviekit.personal_analytics_repository import PersonalAnalyticsRepository
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
        self.client.get_json.reset_mock()
        self.client.get_json.side_effect = [details()]
        self.assertEqual(self.service.enrich('user').enriched, 1)
        self.client.get_json.assert_called_once_with('movie/12', params={'append_to_response': 'credits'})

    def test_malformed_refresh_retains_previous_good_data(self):
        self.repo.save(self.movie, 'complete', 12, ['Drama'], ['Director'])
        previous = self.repo.cached(self.movie)
        self.client.get_json.return_value = {'id': 12}
        self.assertEqual(self.service.enrich('user', refresh=True).failed, 1)
        self.assertEqual(self.repo.cached(self.movie), previous)

    def test_identity_change_invalidates_cache_and_analytics(self):
        self.repo.save(self.movie, 'complete', 12, ['Drama'], ['Director'])
        updated = self.repo.library.upsert_personal_movie(PersonalMovieRecord(
            self.account.id, 'Corrected', 1991, self.movie.letterboxd_url))
        self.assertIsNone(self.repo.cached(updated))
        self.assertEqual(PersonalAnalyticsRepository(self.path).snapshot('user').genres, ())
        self.client.get_json.side_effect = [search(14, 'Corrected', 1991), details(14)]
        self.assertEqual(self.service.enrich('user').enriched, 1)

    def test_existing_canonical_metadata_reused_without_network_or_canonical_changes(self):
        db = DatabaseRepository(self.path)
        db.save_movies([MovieRecord('Linked', 1990, 'https://letterboxd.com/film/linked/',
                                   tmdb_id=5, genres='Comedy', director='Existing')])
        canonical = db.get_movie_by_tmdb_id(5)
        linked = self.add_movie('Linked', 1990, canonical.id)
        self.repo.save(self.movie, 'unmatched')
        before = db.get_movie_details(canonical.id)
        self.assertEqual(self.service.enrich('user').enriched, 1)
        self.client.get_json.assert_not_called()
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
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 4)
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
