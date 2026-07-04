import sqlite3
from pathlib import Path
from typing import Union

DatabasePath = Union[str, Path]

DEFAULT_DATABASE_PATH = "movies.db"


SCHEMA = """
create table if not exists movies (
    id integer primary key,
    title text,
    year integer,
    letterboxd_url text,
    tmdb_id integer,
    tmdb_title text,
    rating real,
    runtime integer,
    director text,
    genres text,
    created_at text,
    updated_at text
);

create table if not exists watched (
    id integer primary key,
    title text,
    year integer,
    watched_date text,
    letterboxd_uri text
);

create table if not exists list_items (
    id integer primary key,
    movie_title text,
    movie_year integer,
    position integer,
    source_list text
);

create table if not exists availability (
    id integer primary key,
    movie_id integer,
    provider text,
    country text,
    access_type text,
    fetched_at text
);
"""


def initialize_database(path: DatabasePath = DEFAULT_DATABASE_PATH) -> Path:
    """Create the MovieKit SQLite database and return its path."""
    database_path = Path(path)

    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)

    return database_path
