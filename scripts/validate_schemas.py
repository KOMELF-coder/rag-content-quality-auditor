"""Validate local JSON contracts; optionally use downloaded Apify meta-schemas."""

import argparse
import json
from pathlib import Path

from jsonschema import Draft7Validator, validate, validators

from my_actor.models import Page
from my_actor.scoring import score

ROOT = Path(__file__).resolve().parents[1]


def main(directory=None):
    files = {
        "actor": "actor.json",
        "input": "input_schema.json",
        "dataset": "dataset_schema.json",
        "output": "output_schema.json",
    }
    documents = {
        name: json.loads((ROOT / ".actor" / filename).read_text(encoding="utf-8"))
        for name, filename in files.items()
    }
    for name in ("input", "output"):
        Draft7Validator.check_schema(documents[name])
    Draft7Validator.check_schema(documents["dataset"]["fields"])
    validate(json.loads((ROOT / ".actor/INPUT.json").read_text()), documents["input"])
    validate(score(Page()).to_dict(), documents["dataset"]["fields"])
    for row in json.loads((ROOT / "examples/page-results.json").read_text()):
        validate(row, documents["dataset"]["fields"])
    if directory:
        for name, document in documents.items():
            schema = json.loads((Path(directory) / f"{name}-metaschema.json").read_text())
            validators.validator_for(schema)(schema).validate(document)
            print(f"Apify {name} meta-schema: valid")
    print("Local JSON schemas, default input and example rows: valid")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apify-schema-dir")
    main(parser.parse_args().apify_schema_dir)
