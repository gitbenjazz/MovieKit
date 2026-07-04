__all__ = ["MovieRepository"]


def __getattr__(name):
    if name == "MovieRepository":
        from .movie_repository import MovieRepository

        return MovieRepository

    raise AttributeError(f"module 'moviekit' has no attribute {name!r}")
