"""Read-only SQL for Personal Library analytics; no schema initialization or writes."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

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
            total = connection.execute("SELECT count(*) FROM movies").fetchone()[0]
        return AnalyticsSnapshot(
            account["username"],
            tuple(AnalyticsMovie(r["id"], r["year"], r["canonical_movie_id"], r["rating"], bool(r["liked"])) for r in movies),
            tuple(AnalyticsWatch(r["personal_movie_id"], r["watched_date"], bool(r["is_rewatch"]), r["source"]) for r in watches),
            tuple((r[0], r[1]) for r in genres), tuple((r[0], r[1]) for r in directors), total,
        )
