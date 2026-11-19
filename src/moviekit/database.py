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
pragma user_version = 9;

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

create table if not exists film_identities (
    id integer primary key,
    tmdb_id integer not null unique,
    title text,
    original_title text,
    release_year integer,
    metadata_fetched_at text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now'))
);

create table if not exists identity_people (
    id integer primary key,
    tmdb_person_id integer not null unique,
    name text not null,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now'))
);

create table if not exists identity_genres (
    identity_id integer not null,
    genre_id integer not null,
    primary key (identity_id, genre_id),
    foreign key (identity_id) references film_identities(id) on delete cascade,
    foreign key (genre_id) references genres(id) on delete cascade
);

create table if not exists identity_credits (
    identity_id integer not null,
    person_id integer not null,
    role text not null,
    billing_order integer,
    primary key (identity_id, person_id, role),
    foreign key (identity_id) references film_identities(id) on delete cascade,
    foreign key (person_id) references identity_people(id) on delete cascade
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

create table if not exists accounts (
    id integer primary key,
    source text not null,
    username text not null,
    display_name text,
    profile_url text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    unique (source, username)
);

create table if not exists personal_movies (
    id integer primary key,
    account_id integer not null,
    canonical_movie_id integer,
    title text not null,
    year integer,
    letterboxd_url text,
    letterboxd_uri text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    check (letterboxd_url is not null or letterboxd_uri is not null),
    unique (id, account_id),
    unique (account_id, letterboxd_url),
    unique (account_id, letterboxd_uri),
    foreign key (account_id) references accounts(id) on delete cascade,
    foreign key (canonical_movie_id) references movies(id) on delete set null
);

create table if not exists personal_movie_metadata (
    personal_movie_id integer primary key references personal_movies(id) on delete cascade,
    source_title text not null,
    source_year integer,
    status text not null check (status in ('pending', 'complete', 'unmatched', 'ambiguous', 'missing_year')),
    tmdb_id integer,
    genres_json text not null default '[]',
    directors_json text not null default '[]',
    metadata_status text not null default 'pending',
    refresh_order integer not null default 0,
    failure_category text,
    failure_message text,
    failure_count integer not null default 0,
    last_failed_at text,
    fetched_at text not null default (datetime('now'))
);

create table if not exists watch_events (
    id integer primary key,
    account_id integer not null,
    personal_movie_id integer not null,
    watched_date text,
    letterboxd_uri text,
    source text not null default 'letterboxd',
    is_rewatch integer not null default 0,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    unique (id, account_id, personal_movie_id),
    unique (account_id, letterboxd_uri),
    foreign key (account_id) references accounts(id) on delete cascade,
    foreign key (personal_movie_id, account_id)
        references personal_movies(id, account_id) on delete cascade
);

create table if not exists ratings (
    account_id integer not null,
    personal_movie_id integer not null,
    rating real not null,
    rated_at text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    primary key (account_id, personal_movie_id),
    foreign key (account_id) references accounts(id) on delete cascade,
    foreign key (personal_movie_id, account_id)
        references personal_movies(id, account_id) on delete cascade
);

create table if not exists reviews (
    id integer primary key,
    account_id integer not null,
    personal_movie_id integer not null,
    watch_event_id integer,
    review_uri text,
    review_text text,
    rating real,
    reviewed_at text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    unique (account_id, review_uri),
    foreign key (account_id) references accounts(id) on delete cascade,
    foreign key (personal_movie_id, account_id)
        references personal_movies(id, account_id) on delete cascade,
    foreign key (watch_event_id) references watch_events(id) on delete set null
);

create table if not exists likes (
    account_id integer not null,
    personal_movie_id integer not null,
    liked_at text,
    source_uri text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    primary key (account_id, personal_movie_id),
    foreign key (account_id) references accounts(id) on delete cascade,
    foreign key (personal_movie_id, account_id)
        references personal_movies(id, account_id) on delete cascade
);

create table if not exists sync_runs (
    id integer primary key,
    account_id integer,
    source text not null,
    sync_type text not null,
    started_at text not null default (datetime('now')),
    finished_at text,
    status text not null,
    records_seen integer not null default 0,
    records_inserted integer not null default 0,
    records_updated integer not null default 0,
    records_skipped integer not null default 0,
    error_message text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    foreign key (account_id) references accounts(id) on delete set null
);

create table if not exists collections (
    id integer primary key,
    slug text not null unique,
    name text not null,
    edition_year integer,
    source_url text,
    description text,
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now'))
);

create table if not exists collection_entries (
    id integer primary key,
    collection_id integer not null,
    editorial_entry_number integer not null,
    source_title text not null,
    source_year integer,
    source_url text not null,
    verification_status text not null,
    review_reason text,
    editorial_group text,
    tmdb_id integer,
    canonical_movie_id integer,
    match_state text not null,
    match_method text,
    candidate_ids_json text not null default '[]',
    created_at text not null default (datetime('now')),
    updated_at text not null default (datetime('now')),
    unique (collection_id, editorial_entry_number),
    foreign key (collection_id) references collections(id) on delete cascade,
    foreign key (canonical_movie_id) references movies(id) on delete set null
);

create index if not exists idx_movie_credits_person_id
    on movie_credits (person_id);

create index if not exists idx_movie_credits_role
    on movie_credits (role);

create index if not exists idx_movie_genres_genre_id
    on movie_genres (genre_id);

create index if not exists idx_identity_genres_genre_id
    on identity_genres (genre_id);

create index if not exists idx_identity_credits_person_id
    on identity_credits (person_id);

create index if not exists idx_identity_credits_role
    on identity_credits (role);

create index if not exists idx_watched_movie_id
    on watched (movie_id);

create index if not exists idx_list_items_movie_id
    on list_items (movie_id);

create index if not exists idx_availability_movie_id
    on availability (movie_id);

create index if not exists idx_availability_provider_id
    on availability (provider_id);

create index if not exists idx_personal_movies_account_id
    on personal_movies (account_id);

create index if not exists idx_personal_movies_canonical_movie_id
    on personal_movies (canonical_movie_id);

create index if not exists idx_personal_movies_title_year
    on personal_movies (title, year);

create index if not exists idx_watch_events_account_date
    on watch_events (account_id, watched_date);

create index if not exists idx_watch_events_personal_movie_id
    on watch_events (personal_movie_id);

create index if not exists idx_ratings_account_rating
    on ratings (account_id, rating);

create index if not exists idx_ratings_personal_movie_id
    on ratings (personal_movie_id);

create index if not exists idx_reviews_personal_movie_id
    on reviews (personal_movie_id);

create index if not exists idx_reviews_account_reviewed_at
    on reviews (account_id, reviewed_at);

create index if not exists idx_likes_personal_movie_id
    on likes (personal_movie_id);

create index if not exists idx_sync_runs_account_started
    on sync_runs (account_id, started_at);

create index if not exists idx_sync_runs_source_type
    on sync_runs (source, sync_type);

create index if not exists idx_collection_entries_collection
    on collection_entries (collection_id, editorial_entry_number);

create index if not exists idx_collection_entries_canonical
    on collection_entries (canonical_movie_id);
"""


def initialize_database(path: DatabasePath = DEFAULT_DATABASE_PATH) -> Path:
    """Create the MovieKit SQLite database and return its path."""
    database_path = Path(path)

    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute("PRAGMA foreign_keys = ON")
            _drop_incompatible_tables(connection)
            connection.executescript(SCHEMA)
            _upgrade_schema(connection)

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


def _upgrade_schema(connection: sqlite3.Connection) -> None:
    """Apply additive v6 identity columns and safely backfill known TMDb IDs."""
    _add_column(connection, "movies", "identity_id integer references film_identities(id) on delete set null")
    _add_column(connection, "personal_movie_metadata", "identity_id integer references film_identities(id) on delete set null")
    _add_column(connection, "personal_movie_metadata", "metadata_status text not null default 'legacy'")
    _add_column(connection, "personal_movie_metadata", "refresh_order integer not null default 0")
    _add_column(connection, "personal_movie_metadata", "failure_category text")
    _add_column(connection, "personal_movie_metadata", "failure_message text")
    _add_column(connection, "personal_movie_metadata", "failure_count integer not null default 0")
    _add_column(connection, "personal_movie_metadata", "last_failed_at text")
    _add_column(connection, "collection_entries", "identity_id integer references film_identities(id) on delete set null")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_movies_identity ON movies(identity_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_personal_metadata_identity ON personal_movie_metadata(identity_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_collection_entries_identity ON collection_entries(identity_id)")
    connection.execute(
        """INSERT OR IGNORE INTO film_identities (tmdb_id, title, release_year)
           SELECT tmdb_id, coalesce(tmdb_title, title), year FROM movies WHERE tmdb_id IS NOT NULL"""
    )
    connection.execute(
        """UPDATE personal_movie_metadata SET metadata_status = CASE
             WHEN status = 'complete' AND EXISTS (
                 SELECT 1 FROM film_identities i
                 WHERE i.id = personal_movie_metadata.identity_id
                   AND i.metadata_fetched_at IS NOT NULL
             ) THEN 'complete'
             WHEN status = 'complete' THEN 'legacy'
             WHEN status = 'pending' THEN 'pending'
             ELSE 'unavailable' END
           WHERE metadata_status IN ('pending', 'legacy')"""
    )
    connection.execute(
        """INSERT OR IGNORE INTO film_identities (tmdb_id, title, release_year)
           SELECT tmdb_id, source_title, source_year FROM collection_entries WHERE tmdb_id IS NOT NULL"""
    )
    connection.execute(
        """INSERT OR IGNORE INTO film_identities (tmdb_id, title, release_year)
           SELECT tmdb_id, source_title, source_year FROM personal_movie_metadata
           WHERE tmdb_id IS NOT NULL"""
    )
    connection.execute(
        """UPDATE movies SET identity_id = (
               SELECT id FROM film_identities WHERE tmdb_id = movies.tmdb_id)
           WHERE tmdb_id IS NOT NULL AND identity_id IS NULL"""
    )
    connection.execute(
        """UPDATE collection_entries SET identity_id = (
               SELECT id FROM film_identities WHERE tmdb_id = collection_entries.tmdb_id)
           WHERE tmdb_id IS NOT NULL AND identity_id IS NULL"""
    )
    connection.execute(
        """UPDATE collection_entries SET identity_id = (
               SELECT identity_id FROM movies WHERE movies.id = collection_entries.canonical_movie_id)
           WHERE canonical_movie_id IS NOT NULL AND identity_id IS NULL"""
    )
    connection.execute(
        """UPDATE personal_movie_metadata SET identity_id = (
               SELECT id FROM film_identities WHERE tmdb_id = personal_movie_metadata.tmdb_id)
           WHERE tmdb_id IS NOT NULL AND identity_id IS NULL"""
    )


def _add_column(connection: sqlite3.Connection, table: str, definition: str) -> None:
    column = definition.split()[0]
    if column not in _table_columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _has_unique_indexes(connection: sqlite3.Connection, table: str) -> bool:
    return any(row[2] for row in connection.execute(f"PRAGMA index_list({table})"))
