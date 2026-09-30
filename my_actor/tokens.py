import math
import re


def word_units(text: str) -> list[str]:
    """Use the same Unicode units for content size and duplicate fingerprints."""
    return re.findall(
        r"[\u3400-\u9fff\u3040-\u30ff]|[^\W_\u3400-\u9fff\u3040-\u30ff]+", text, re.UNICODE
    )


def estimate_tokens(text: str) -> int:
    """Language-dependent approximation; no model or tokenizer is implied."""
    return math.ceil(len(text) / 4) if text else 0
