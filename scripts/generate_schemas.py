"""Regenerate the dataset schema from the stable Page contract."""

import json
from pathlib import Path
from types import UnionType
from typing import get_args, get_origin, get_type_hints

from my_actor.models import Page

ROOT = Path(__file__).resolve().parents[1]


def json_type(annotation):
    origin = get_origin(annotation)
    if origin is UnionType:
        return {"anyOf": [json_type(a) for a in get_args(annotation)]}
    if origin is list:
        return {"type": "array", "items": json_type(get_args(annotation)[0])}
    if origin is dict:
        return {"type": "object", "additionalProperties": json_type(get_args(annotation)[1])}
    return {
        "type": {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            type(None): "null",
        }[annotation]
    }


def build():
    properties = {}
    descriptions = {
        "source_id": "Stable source reference: requested URL or dataset:ID:zero-based-row-index.",
        "url": "Normalized final or supplied source URL; empty when dataset URL is unavailable.",
        "status": "audited for successful analyses; skipped/failed diagnostics are saved separately.",
        "rag_readiness_score": "Sum of six documented components, 0 to 100; not measured retrieval accuracy.",
        "rag_value": "Deterministic retrieval-potential proxy, not semantic business relevance.",
        "recommended_for_rag": "True when the explicit quality, content, uniqueness and profile criteria pass.",
        "estimated_tokens": "Approximate Unicode characters divided by four, rounded up.",
        "duplicate_of": "Representative source_id within this audit, or null.",
        "similarity": "One minus 64-bit SimHash Hamming distance divided by 64; exact matches are 1.",
        "boilerplate_ratio": "Clamped 1 - main_content_chars / max(raw_text_chars, 1).",
        "robots_allowed": "Observed/fallback crawl decision; null if not checked. Not a legal consent signal.",
        "recommended_chunk_size": "Starting chunk size in estimated tokens; evaluate with your retrieval pipeline.",
        "metadata_available": "Whether HTML metadata could be inspected; missing HTML is reported explicitly.",
    }
    for name, annotation in get_type_hints(Page).items():
        properties[name] = {
            **json_type(annotation),
            "title": name.replace("_", " ").capitalize(),
            "description": descriptions.get(name, name.replace("_", " ").capitalize() + "."),
        }
    properties["rag_readiness_score"].update(minimum=0, maximum=100)
    for name, values in {
        "source_type": ["website", "dataset"],
        "status": ["audited", "skipped", "failed"],
        "rag_value": ["high", "medium", "low"],
        "duplicate_status": ["unique", "exact_duplicate", "near_duplicate", "not_checked"],
        "rag_readiness_level": ["excellent", "good", "mixed", "poor"],
        "content_status": [
            "ok",
            "empty",
            "too_short",
            "likely_requires_javascript",
            "unsupported",
            "unavailable",
        ],
    }.items():
        properties[name]["enum"] = values
    columns = {
        "url": ("URL", "link"),
        "rag_readiness_score": ("RAG score", "number"),
        "rag_value": ("RAG value", "text"),
        "recommended_for_rag": ("Recommended", "boolean"),
        "estimated_tokens": ("Est. tokens", "number"),
        "duplicate_status": ("Duplicates", "text"),
        "content_status": ("Content status", "text"),
        "issues": ("Issues", "array"),
    }
    return {
        "actorSpecification": 1,
        "fields": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        "views": {
            "overview": {
                "title": "RAG readiness",
                "transformation": {"fields": list(columns)},
                "display": {
                    "component": "table",
                    "properties": {k: {"label": v[0], "format": v[1]} for k, v in columns.items()},
                },
            }
        },
    }


if __name__ == "__main__":
    (ROOT / ".actor/dataset_schema.json").write_text(
        json.dumps(build(), indent=2) + "\n", encoding="utf-8"
    )
