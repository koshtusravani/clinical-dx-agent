"""
I load raw Synthea FHIR bundles here from data/synthea_raw/. I generated
these myself by running the Synthea Java tool locally rather than
downloading a fixed dataset, since Synthea is a generator, not a static
file. FHIR bundles are verbose nested JSON, so this module just extracts
the resource lists I care about. The actual simplification into my own
case schema happens in flatten_case.py.
"""

import json
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "synthea_raw"


def load_bundle(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def list_raw_bundles() -> list[Path]:
    return sorted(RAW_DIR.glob("*.json"))


def extract_resources(bundle: dict, resource_type: str) -> list[dict]:
    """
    I pull all resources of a given type out of a FHIR bundle, for example
    'Condition', 'Observation', 'MedicationRequest', or 'Patient'.
    """
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") == resource_type
    ]