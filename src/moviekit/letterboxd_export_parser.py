"""Read an extracted Letterboxd export without persistence or network access."""
from __future__ import annotations

import csv
from datetime import date
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from .personal_library_models import (
    ImportedLike, ImportedRating, ImportedReview, ImportedWatch,
    ImportIssue, LetterboxdImport, MovieIdentity,
)


class ExportFormatError(ValueError):
    pass


def normalize_letterboxd_uri(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "letterboxd.com", "www.letterboxd.com", "boxd.it"
    } or not parsed.path.strip("/") or parsed.username or parsed.password:
        raise ValueError("Invalid Letterboxd URI")
    host = "letterboxd.com" if parsed.hostname == "www.letterboxd.com" else parsed.hostname
    return f"https://{host}/{parsed.path.strip('/')}/"


def film_url(uri: str) -> str | None:
    """A long film or user-entry URL exposes a film slug; short URLs do not."""
    parsed = urlsplit(uri)
    if parsed.hostname != "letterboxd.com":
        return None
    match = re.fullmatch(r"/(?:[^/]+/)?film/([^/]+)(?:/\d+)?/", parsed.path)
    return f"https://letterboxd.com/film/{match[1]}/" if match else None


class LetterboxdExportParser:
    FILES = ("watched.csv", "ratings.csv", "diary.csv", "reviews.csv", "likes/films.csv")

    def parse(self, source: str | Path) -> LetterboxdImport:
        root = Path(source)
        if not root.is_dir():
            raise ExportFormatError("Source must be an extracted Letterboxd export directory")
        watches, ratings, reviews, likes, issues, files = [], [], [], [], [], []
        rows_seen = 0
        for filename in self.FILES:
            path = root / filename
            if not path.exists():
                continue
            files.append(filename)
            try:
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle, strict=True)
                    required = {"Name", "Year", "Letterboxd URI"}
                    if filename == "ratings.csv":
                        required.add("Rating")
                    if filename == "reviews.csv":
                        required.add("Review")
                    if not required.issubset(reader.fieldnames or []):
                        raise ExportFormatError(f"{filename}: missing required CSV headers")
                    for row in reader:
                        rows_seen += 1
                        try:
                            if None in row or any(v is None for v in row.values()):
                                raise ValueError("Incorrect CSV field count")
                            record = self._parse_row(filename, row)
                        except ValueError as exc:
                            issues.append(ImportIssue(filename, reader.line_num, str(exc)))
                            continue
                        if isinstance(record, ImportedWatch):
                            watches.append(record)
                        elif isinstance(record, ImportedRating):
                            ratings.append(record)
                        elif isinstance(record, ImportedReview):
                            reviews.append(record)
                        else:
                            likes.append(record)
            except (csv.Error, UnicodeError) as exc:
                raise ExportFormatError(f"{filename}: invalid CSV encoding or structure") from exc
        if not files:
            raise ExportFormatError("No supported Letterboxd CSV files found")
        return LetterboxdImport(tuple(watches), tuple(ratings), tuple(reviews),
                               tuple(likes), tuple(issues), tuple(files), rows_seen)

    def _parse_row(self, filename: str, row: dict[str, str]):
        title = row["Name"].strip()
        if not title:
            raise ValueError("Missing Name")
        raw_year = row["Year"].strip()
        year = int(raw_year) if raw_year else None
        if year is not None and not 1 <= year <= 9999:
            raise ValueError("Invalid Year")
        uri = normalize_letterboxd_uri(row["Letterboxd URI"])
        movie = MovieIdentity(title, year, uri, film_url(uri))
        added = self._date(row.get("Date", ""))
        watched = self._date(row.get("Watched Date", ""))
        if filename == "ratings.csv":
            return ImportedRating(movie, self._rating(row["Rating"], required=True), added)
        if filename == "reviews.csv":
            return ImportedReview(movie, uri, row["Review"], self._rating(row.get("Rating", "")),
                                  added, watched)
        if filename == "likes/films.csv":
            return ImportedLike(movie, added)
        rewatch = row.get("Rewatch", "").strip().lower()
        if rewatch not in {"", "yes", "no", "true", "false"}:
            raise ValueError("Invalid Rewatch value")
        # watched.csv Date is when marked watched, not necessarily a viewing date.
        return ImportedWatch(movie, uri, watched, rewatch in {"yes", "true"},
                             "letterboxd_diary" if filename == "diary.csv" else "letterboxd_watched")

    @staticmethod
    def _date(value: str) -> str | None:
        value = value.strip()
        if not value:
            return None
        return date.fromisoformat(value).isoformat()

    @staticmethod
    def _rating(value: str, required: bool = False) -> float | None:
        if not value.strip() and not required:
            return None
        rating = float(value)
        if not math.isfinite(rating) or not 0.5 <= rating <= 5 or rating * 2 != int(rating * 2):
            raise ValueError("Rating must be a half-star increment between 0.5 and 5")
        return rating
