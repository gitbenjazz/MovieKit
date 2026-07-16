from __future__ import annotations

import os
from typing import Optional

BASE_URL = "https://api.themoviedb.org/3"


class TMDbAPIError(RuntimeError):
    pass


class TMDbAuthenticationError(TMDbAPIError):
    pass


def load_tmdb_api_key() -> Optional[str]:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        pass
    else:
        load_dotenv()

    return os.getenv("TMDB_API_KEY")


class TMDbClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        session=None,
        base_url: str = BASE_URL,
    ):
        self.api_key = api_key if api_key is not None else load_tmdb_api_key()
        self.session = session
        self.base_url = base_url.rstrip("/")

    def get_json(self, path: str, params: Optional[dict] = None) -> dict:
        if not self.api_key:
            raise TMDbAuthenticationError("TMDB_API_KEY is not configured")

        request_params = dict(params or {})
        request_params["api_key"] = self.api_key

        requests_module = None
        session = self.session
        if session is None:
            import requests as requests_module

            session = requests_module

        try:
            response = session.get(
                f"{self.base_url}/{path.lstrip('/')}",
                params=request_params,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except TMDbAPIError:
            raise
        except ValueError as exc:
            raise TMDbAPIError("TMDb response was not valid JSON") from exc
        except Exception as exc:
            if requests_module is not None:
                if isinstance(exc, requests_module.HTTPError):
                    status_code = getattr(exc.response, "status_code", None)
                    if status_code in {401, 403}:
                        raise TMDbAuthenticationError(
                            "TMDb authentication failed"
                        ) from exc
                    raise TMDbAPIError("TMDb request failed") from exc
                if isinstance(exc, requests_module.RequestException):
                    raise TMDbAPIError("TMDb request failed") from exc
            raise

        if not isinstance(data, dict):
            raise TMDbAPIError("TMDb response was malformed")

        return data
