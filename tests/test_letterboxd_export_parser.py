import csv
from pathlib import Path
import tempfile
import unittest

from moviekit.letterboxd_export_parser import ExportFormatError, LetterboxdExportParser


class LetterboxdParserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.parser = LetterboxdExportParser()

    def write(self, name, headers, rows):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

    def test_standard_files_and_optional_fields(self):
        headers = ["Date", "Name", "Year", "Letterboxd URI"]
        film = ["2026-09-01", " A Film ", "2000", "http://boxd.it/ABC"]
        self.write("watched.csv", headers, [film])
        self.write("ratings.csv", headers + ["Rating"], [film + ["4.5"]])
        self.write("likes/films.csv", headers, [film])
        diary = ["2026-09-02", "A Film", "2000", "https://letterboxd.com/member/film/a-film/2/"]
        self.write("diary.csv", headers + ["Rating", "Rewatch", "Tags", "Watched Date"],
                   [diary + ["", "Yes", "nature", "2026-08-31"]])
        self.write("reviews.csv", headers + ["Rating", "Rewatch", "Review", "Tags", "Watched Date"],
                   [diary + ["4", "Yes", 'Text, with "quotes"\nand a newline.', "", "2026-08-31"]])
        data = self.parser.parse(self.root)
        self.assertEqual(data.rows_seen, 5)
        self.assertEqual(data.issues, ())
        self.assertEqual(data.watches[0].movie.title, "A Film")
        self.assertIsNone(data.watches[0].watched_date)
        self.assertTrue(data.watches[1].is_rewatch)
        self.assertEqual(data.watches[1].watched_date, "2026-08-31")
        self.assertEqual(data.watches[1].movie.letterboxd_url,
                         "https://letterboxd.com/film/a-film/")
        self.assertEqual(data.ratings[0].rating, 4.5)
        self.assertIn("\n", data.reviews[0].text)
        self.assertEqual(len(data.likes), 1)

    def test_bad_rows_reported_without_private_content(self):
        self.write("ratings.csv", ["Name", "Year", "Letterboxd URI", "Rating"], [
            ["Good", "", "https://boxd.it/good", "3"],
            ["", "2000", "https://boxd.it/a", "4"],
            ["Bad", "2000", "https://evil.example/a", "4"],
            ["Bad", "2000", "https://boxd.it/b", "nan"],
            ["Bad", "2000", "https://boxd.it/c", "4.2"],
        ])
        data = self.parser.parse(self.root)
        self.assertEqual(len(data.ratings), 1)
        self.assertIsNone(data.ratings[0].movie.year)
        self.assertEqual(len(data.issues), 4)
        self.assertEqual(data.issues[0].row, 3)

    def test_missing_headers_or_files_fail(self):
        with self.assertRaises(ExportFormatError):
            self.parser.parse(self.root)
        self.write("watched.csv", ["Name"], [["Film"]])
        with self.assertRaises(ExportFormatError):
            self.parser.parse(self.root)

    def test_invalid_date_and_truncated_row_are_skipped(self):
        self.write("watched.csv", ["Date", "Name", "Year", "Letterboxd URI"], [
            ["2026-02-30", "Film", "2000", "https://boxd.it/a"], ["2026-01-01", "Film"]
        ])
        data = self.parser.parse(self.root)
        self.assertEqual(len(data.issues), 2)
        self.assertEqual(data.watches, ())
