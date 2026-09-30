import json
from pathlib import Path

import jsonschema

from my_actor.input_validation import validate_input
from my_actor.models import Page
from my_actor.scoring import score
from scripts.generate_schemas import build

ROOT = Path(__file__).resolve().parents[1]


def test_schemas():
    for filename in ("input_schema.json", "output_schema.json"):
        schema = json.loads((ROOT / ".actor" / filename).read_text())
        jsonschema.Draft7Validator.check_schema(schema)
    dataset = json.loads((ROOT / ".actor/dataset_schema.json").read_text())
    assert dataset == build()
    jsonschema.Draft7Validator.check_schema(dataset["fields"])
    jsonschema.validate(score(Page()).to_dict(), dataset["fields"])


def test_default_input():
    data = json.loads((ROOT / ".actor/INPUT.json").read_text())
    schema = json.loads((ROOT / ".actor/input_schema.json").read_text())
    jsonschema.validate(data, schema)
    assert validate_input(data).max_pages == 8


def test_actor_paths():
    actor = json.loads((ROOT / ".actor/actor.json").read_text())
    for key in ("input", "output", "dockerfile"):
        assert (ROOT / ".actor" / actor[key]).is_file()
    assert (ROOT / ".actor" / actor["storages"]["dataset"]).is_file()
