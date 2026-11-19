"""Read-only SQL for Personal Library analytics; no schema initialization or writes."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import json

from .personal_analytics_models import AnalyticsMovie, AnalyticsSnapshot, AnalyticsWatch


class PersonalAnalyticsRepository:
    def __init__(self, database_path=None):
        if database_path is None:
            from .config import load_config

            database_path = load_config().database_path
        self.database_path = Path(database_path)

    def usernames(self) -> list[str]:
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            return [row[0] for row in connection.execute(
                "SELECT username FROM accounts WHERE source = 'letterboxd' ORDER BY username"
            )]

    def snapshot(self, username: str) -> AnalyticsSnapshot | None:
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            account = connection.execute(
                "SELECT id, username FROM accounts WHERE source = 'letterboxd' AND username = ?",
                (username,),
            ).fetchone()
            if account is None:
                return None
            account_id = account["id"]
            movies = connection.execute(
                """SELECT p.id, p.year, p.canonical_movie_id, r.rating,
                          EXISTS (SELECT 1 FROM likes l WHERE l.account_id = p.account_id
                                  AND l.personal_movie_id = p.id) AS liked
                   FROM personal_movies p
                   LEFT JOIN ratings r ON r.account_id = p.account_id AND r.personal_movie_id = p.id
                   WHERE p.account_id = ? ORDER BY p.id""", (account_id,),
            ).fetchall()
            watches = connection.execute(
                "SELECT personal_movie_id, watched_date, is_rewatch, source FROM watch_events "
                "WHERE account_id = ? ORDER BY id", (account_id,),
            ).fetchall()
            genres = connection.execute(
                """SELECT DISTINCT p.id, g.name FROM personal_movies p
                   JOIN movie_genres mg ON mg.movie_id = p.canonical_movie_id
                   JOIN genres g ON g.id = mg.genre_id WHERE p.account_id = ?
                   AND trim(g.name) != '' ORDER BY p.id, g.name""", (account_id,),
            ).fetchall()
            directors = connection.execute(
                """SELECT DISTINCT p.id, people.name FROM personal_movies p
                   JOIN movie_credits mc ON mc.movie_id = p.canonical_movie_id
                   JOIN people ON people.id = mc.person_id
                   WHERE p.account_id = ? AND lower(mc.role) = 'director'
                   AND trim(people.name) != '' ORDER BY p.id, people.name""", (account_id,),
            ).fetchall()
            actors = connection.execute(
                """SELECT DISTINCT p.id, people.name FROM personal_movies p
                   JOIN movie_credits mc ON mc.movie_id = p.canonical_movie_id
                   JOIN people ON people.id = mc.person_id
                   WHERE p.account_id = ? AND lower(mc.role) = 'actor'
                     AND trim(people.name) != '' ORDER BY p.id, people.name""",
                (account_id,),
            ).fetchall()
            # Older databases remain readable until the next explicit initialization.
            metadata_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(personal_movie_metadata)")
            }
            if metadata_columns:
                identity_column = "m.identity_id" if "identity_id" in metadata_columns else "NULL"
                metadata = connection.execute(
                    f"""SELECT p.id, m.genres_json, m.directors_json, {identity_column}
                       FROM personal_movies p JOIN personal_movie_metadata m
                         ON m.personal_movie_id = p.id
                       WHERE p.account_id = ? AND m.status = 'complete'
                         AND m.source_title = p.title AND m.source_year IS p.year""",
                    (account_id,),
                ).fetchall()
                # A completed personal fetch owns both dimensions, including empty
                # lists. Canonical metadata is the fallback for unenriched films.
                enriched_ids = {r[0] for r in metadata}
                genres = [(r[0], r[1]) for r in genres if r[0] not in enriched_ids]
                directors = [(r[0], r[1]) for r in directors if r[0] not in enriched_ids]
                for row in metadata:
                    genres.extend((row[0], name) for name in json.loads(row[1]))
                    directors.extend((row[0], name) for name in json.loads(row[2]))
                identity_tables = all(connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
                ).fetchone() for name in ("identity_genres", "identity_credits", "identity_people"))
                if identity_tables and "identity_id" in metadata_columns:
                    identity_genres = connection.execute(
                        """SELECT DISTINCT p.id, g.name FROM personal_movies p
                           JOIN personal_movie_metadata m ON m.personal_movie_id = p.id
                           JOIN identity_genres ig ON ig.identity_id = m.identity_id
                           JOIN genres g ON g.id = ig.genre_id
                           WHERE p.account_id = ? AND m.status = 'complete'""",
                        (account_id,),
                    ).fetchall()
                    identity_credits = connection.execute(
                        """SELECT DISTINCT p.id, people.name, credits.role FROM personal_movies p
                           JOIN personal_movie_metadata m ON m.personal_movie_id = p.id
                           JOIN identity_credits credits ON credits.identity_id = m.identity_id
                           JOIN identity_people people ON people.id = credits.person_id
                           WHERE p.account_id = ? AND m.status = 'complete'""",
                        (account_id,),
                    ).fetchall()
                    genres.extend((row[0], row[1]) for row in identity_genres)
                    directors.extend((row[0], row[1]) for row in identity_credits if row[2] == 'director')
                    actors.extend((row[0], row[1]) for row in identity_credits if row[2] == 'actor')
            total = connection.execute("SELECT count(*) FROM movies").fetchone()[0]
        return AnalyticsSnapshot(
            account["username"],
            tuple(AnalyticsMovie(r["id"], r["year"], r["canonical_movie_id"], r["rating"], bool(r["liked"])) for r in movies),
            tuple(AnalyticsWatch(r["personal_movie_id"], r["watched_date"], bool(r["is_rewatch"]), r["source"]) for r in watches),
            tuple(sorted(set((r[0], r[1]) for r in genres))),
            tuple(sorted(set((r[0], r[1]) for r in directors))), total,
            tuple(sorted(set((r[0], r[1]) for r in actors))),
        )
