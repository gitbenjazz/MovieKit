from contextlib import closing
import sqlite3
from pathlib import Path
from typing import Union

DatabasePath = Union[str, Path]

DEFAULT_DATABASE_PATH = "movies.db"


REQUIRED_COLUMNS = {
    "watched": {"movie_id"},
    "list_items": {"movie_id", "source_list_id"},
    "availability": {"provider_id", "country_code"},
}


SCHEMA = """
pragma foreign_keys = on;
pragma user_version = 2;

create table if not exists movies (
    id integer primary key,
    title text not null,
    year integer,
    letterboxd_url text not null unique,
    tmdb_id integer unique,
    tmdb_title text,
    rating real,
    runtime integer,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now'))
);

create table if not exists people (
    id integer primary key,
    name text not null unique
);

create table if not exists movie_credits (
    movie_id integer not null,
    person_id integer not null,
    role text not null,
    billing_order integer,
    primary key (movie_id, person_id, role),
    foreign key (movie_id) references movies(id) on delete cascade,
    foreign key (person_id) references people(id) on delete cascade
);

create table if not exists genres (
    id integer primary key,
    name text not null unique
);

create table if not exists movie_genres (
    movie_id integer not null,
    genre_id integer not null,
    primary key (movie_id, genre_id),
    foreign key (movie_id) references movies(id) on delete cascade,
    foreign key (genre_id) references genres(id) on delete cascade
);

create table if not exists watched (
    id integer primary key,
    movie_id integer not null,
    watched_date text,
    letterboxd_uri text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    foreign key (movie_id) references movies(id) on delete cascade
);

create table if not exists source_lists (
    id integer primary key,
    name text not null unique
);

create table if not exists list_items (
    id integer primary key,
    movie_id integer not null,
    source_list_id integer not null,
    position integer not null,
    created_at text not null default (datetime('now')),
    unique (source_list_id, movie_id),
    unique (source_list_id, position),
    foreign key (movie_id) references movies(id) on delete cascade,
    foreign key (source_list_id) references source_lists(id) on delete cascade
);

create table if not exists providers (
    id integer primary key,
    name text not null unique
);

create table if not exists countries (
    code text primary key,
    name text
);

create table if not exists availability (
    id integer primary key,
    movie_id integer not null,
    provider_id integer not null,
    country_code text not null,
    access_type text not null,
    fetched_at text not null,
    unique (movie_id, provider_id, country_code, access_type),
    foreign key (movie_id) references movies(id) on delete cascade,
    foreign key (provider_id) references providers(id) on delete cascade,
    foreign key (country_code) references countries(code)
);

create index if not exists idx_movie_credits_person_id
    on movie_credits (person_id);

create index if not exists idx_movie_credits_role
    on movie_credits (role);

create index if not exists idx_movie_genres_genre_id
    on movie_genres (genre_id);

create index if not exists idx_watched_movie_id
    on watched (movie_id);

create index if not exists idx_list_items_movie_id
    on list_items (movie_id);

create index if not exists idx_availability_movie_id
    on availability (movie_id);

create index if not exists idx_availability_provider_id
    on availability (provider_id);
"""


def initialize_database(path: DatabasePath = DEFAULT_DATABASE_PATH) -> Path:
    """Create the MovieKit SQLite database and return its path."""
    database_path = Path(path)

    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute("PRAGMA foreign_keys = ON")
            _drop_incompatible_tables(connection)
            connection.executescript(SCHEMA)

    return database_path


def _drop_incompatible_tables(connection: sqlite3.Connection) -> None:
    for table, required_columns in REQUIRED_COLUMNS.items():
        existing_columns = _table_columns(connection, table)

        if existing_columns and not required_columns.issubset(existing_columns):
            connection.execute(f"DROP TABLE {table}")

    if _table_columns(connection, "watched") and _has_unique_indexes(
        connection,
        "watched",
    ):
        connection.execute("DROP TABLE watched")


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _has_unique_indexes(connection: sqlite3.Connection, table: str) -> bool:
    return any(row[2] for row in connection.execute(f"PRAGMA index_list({table})"))
