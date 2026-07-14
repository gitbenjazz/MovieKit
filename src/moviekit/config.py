from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python < 3.11
    tomllib = None


@dataclass(frozen=True)
class MovieKitConfig:
    database_path: str = "movies.db"
    default_search_limit: int = 20


def config_path() -> Path:
    return Path.home() / ".config" / "moviekit" / "config.toml"


def load_config() -> MovieKitConfig:
    path = config_path()

    if not path.exists():
        config = MovieKitConfig()
        save_config(config)
        return config

    return _config_from_dict(_load_toml(path))


def save_config(config: MovieKitConfig) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(asdict(config)), encoding="utf-8")
    return path


def _config_from_dict(values: dict[str, Any]) -> MovieKitConfig:
    defaults = asdict(MovieKitConfig())
    allowed_fields = {field.name for field in fields(MovieKitConfig)}
    config_values = {
        name: values.get(name, default)
        for name, default in defaults.items()
        if name in allowed_fields
    }
    return MovieKitConfig(**config_values)


def _load_toml(path: Path) -> dict[str, Any]:
    if tomllib is not None:
        with path.open("rb") as handle:
            return tomllib.load(handle)

    return _load_simple_toml(path)


def _load_simple_toml(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        key, separator, value = line.partition("=")
        if not separator:
            continue

        values[key.strip()] = _parse_toml_value(value.strip())

    return values


def _parse_toml_value(value: str) -> Any:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")

    return int(value)


def _to_toml(values: dict[str, Any]) -> str:
    lines = []

    for key, value in values.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{_escape_toml_string(value)}"')
        else:
            lines.append(f"{key} = {value}")

    return "\n".join(lines) + "\n"


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
