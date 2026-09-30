import re
from dataclasses import fields

from .limits import (
    MAX_CONCURRENCY,
    MAX_DEPTH,
    MAX_PAGES,
    MAX_PATTERNS,
    MAX_TIMEOUT_SECS,
    MIN_TIMEOUT_SECS,
)
from .models import AuditInput


def validate_input(data: dict | None) -> AuditInput:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object.")  # noqa: TRY004 - public input error contract
    unknown = data.keys() - {f.name for f in fields(AuditInput)}
    if unknown:
        raise ValueError("Unknown input fields: " + ", ".join(sorted(unknown)))
    values = dict(data)
    for name, default, low, high in (
        ("max_pages", 50, 1, MAX_PAGES),
        ("max_depth", 3, 0, MAX_DEPTH),
        ("max_concurrency", 4, 1, MAX_CONCURRENCY),
        ("request_timeout_secs", 25, MIN_TIMEOUT_SECS, MAX_TIMEOUT_SECS),
    ):
        value = values.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} must be an integer between {low} and {high}.")
    for name in ("respect_robots_txt", "detect_duplicates", "check_ai_metadata"):
        if name in values and type(values[name]) is not bool:
            raise ValueError(f"{name} must be a boolean.")
    for name in ("include_patterns", "exclude_patterns"):
        value = values.get(name, [])
        if not isinstance(value, list) or len(value) > MAX_PATTERNS:
            raise ValueError(f"{name} must be a list of at most {MAX_PATTERNS} URL globs.")
        if any(not isinstance(p, str) or not p or len(p) > 200 for p in value):
            raise ValueError(f"{name} must contain nonempty glob strings up to 200 characters.")
        values[name] = tuple(value)
    for name in ("mode", "start_url", "dataset_id"):
        if name in values and not isinstance(values[name], str):
            raise ValueError(f"{name} must be a string.")
    result = AuditInput(**values)
    if result.mode not in ("website", "dataset"):
        raise ValueError("mode must be website or dataset.")
    if result.mode == "website" and not result.start_url.strip():
        raise ValueError("Provide a website URL.")
    if result.mode == "dataset" and not re.fullmatch(
        r"[A-Za-z0-9_-]{1,100}(?:~[A-Za-z0-9_-]{1,100})?", result.dataset_id
    ):
        raise ValueError("Provide a dataset ID or owner~dataset name, not a URL.")
    return result
