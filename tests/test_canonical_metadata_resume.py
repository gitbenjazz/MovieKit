from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from moviekit import cli
from moviekit.application import SyncMetadata
from moviekit.bulk_sync_service import BulkSyncService
from moviekit.database_repository import DatabaseRepository
from moviekit.metadata_service import MetadataSyncService
from moviekit.models import MovieRecord
from moviekit.tmdb_client import TMDbAPIError


class CanonicalMetadataResumeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = DatabaseRepository(Path(temp.name) / 'movies.db')
        self.repo.save_movies([
            MovieRecord('A cached', 1990, 'https://letterboxd.com/film/a/', tmdb_id=1,
                        genres='Drama', director='Director'),
            MovieRecord('B pending', 1991, 'https://letterboxd.com/film/b/', tmdb_id=2),
            MovieRecord('C pending', 1992, 'https://letterboxd.com/film/c/', tmdb_id=3),
        ])
        self.client = Mock()
        self.client.get_json.return_value = {'title': 'Film', 'genres': [{'name': 'Drama'}],
            'credits': {'crew': [{'job': 'Director', 'name': 'Director'}]}}
        self.service = BulkSyncService(self.repo, MetadataSyncService(self.repo, self.client))

    def test_skip_enriched_limit_pending_and_resume_persisted_progress(self):
        events = []
        first = self.service.sync_metadata(limit=1, progress=lambda *args: events.append(args))
        self.assertEqual((first.updated, first.skipped), (1, 1))
        self.client.get_json.assert_called_once_with('movie/2', params={'append_to_response': 'credits'})
        self.assertEqual([e[1] for e in events], ['cached', 'fetching', 'updated'])
        self.client.reset_mock()
        resumed = BulkSyncService(self.repo, MetadataSyncService(self.repo, self.client))
        self.assertEqual(resumed.sync_metadata(limit=1).updated, 1)
        self.client.get_json.assert_called_once_with('movie/3', params={'append_to_response': 'credits'})
        self.client.reset_mock()
        final = resumed.sync_metadata()
        self.assertEqual((final.updated, final.skipped), (0, 3))
        self.client.get_json.assert_not_called()
        self.assertEqual(len(self.repo.get_all_movies()), 3)
        details = self.repo.get_movie_details(self.repo.get_movie_by_tmdb_id(2).id)
        self.assertEqual(details.genres, ['Drama'])
        self.assertEqual([c.name for c in details.credits], ['Director'])

    def test_network_failure_stops_immediately_and_can_resume(self):
        response = self.client.get_json.return_value
        self.client.get_json.side_effect = TMDbAPIError('TMDb request failed')
        events = []
        result = self.service.sync_metadata(progress=lambda *args: events.append(args))
        self.assertEqual(result.failed, 1)
        self.assertEqual(self.client.get_json.call_count, 1)
        self.assertIn('stopping', events[-1][1])
        self.client.get_json.side_effect = None
        self.client.get_json.return_value = response
        self.assertEqual(self.service.sync_metadata().updated, 2)

    def test_cli_progress_is_visible_before_network_and_limit_is_forwarded(self):
        output = StringIO()
        response = self.client.get_json.return_value
        def request(*args, **kwargs):
            self.assertIn('B pending (1991): fetching', output.getvalue())
            return response
        self.client.get_json.side_effect = request
        with patch('moviekit.application.SyncMetadata', return_value=SyncMetadata(bulk_sync_service=self.service)), redirect_stdout(output):
            args = cli.build_parser().parse_args(['sync', 'metadata', '--limit', '1'])
            self.assertEqual(args.func(args), 0)
        self.assertIn('Updated: 1', output.getvalue())
        self.assertIn('cached', output.getvalue())

    def test_invalid_limit_has_no_network_calls(self):
        with self.assertRaises(ValueError):
            self.service.sync_metadata(limit=0)
        self.client.get_json.assert_not_called()

    def test_cli_interrupt_reports_saved_progress(self):
        with patch('moviekit.application.SyncMetadata') as use_case, redirect_stdout(StringIO()) as output:
            use_case.return_value.execute.side_effect = KeyboardInterrupt
            self.assertEqual(cli.sync_metadata(), 130)
        self.assertIn('Rerun to resume', output.getvalue())
