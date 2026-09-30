import pytest

from my_actor.input_validation import validate_input
from my_actor.limits import MAX_PAGES


def test_defaults():
    assert validate_input({}).max_pages == 50


@pytest.mark.parametrize("value", [0, -1, MAX_PAGES + 1, True, "10", 1.5])
def test_page_limits(value):
    with pytest.raises(ValueError):
        validate_input({"max_pages": value})


@pytest.mark.parametrize(
    "data",
    [
        {"mode": "bad"},
        {"mode": "dataset"},
        {"x": 1},
        {"respect_robots_txt": "false"},
        {"max_depth": 11},
        {"max_concurrency": 9},
        {"request_timeout_secs": 61},
        {"include_patterns": ["a" * 201]},
        [],
    ],
)
def test_bad_input(data):
    with pytest.raises(ValueError):
        validate_input(data)
