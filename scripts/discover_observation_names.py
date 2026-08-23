"""
I use this script to search specifically for lipid panel and urinalysis
observation names in my Synthea data, since a plain frequency count didn't
surface them in the top results.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_pipeline.synthea_loader import extract_resources, list_raw_bundles, load_bundle

SEARCH_KEYWORDS = [
    "cholesterol", "ldl", "hdl", "triglyceride",
    "urinalysis", "leukocyte esterase", "nitrite", "urine",
]

found_texts = Counter()

for path in list_raw_bundles():
    try:
        bundle = load_bundle(path)
    except Exception:
        continue

    observations = extract_resources(bundle, "Observation")
    for obs in observations:
        text = obs.get("code", {}).get("text", "")
        if any(kw in text.lower() for kw in SEARCH_KEYWORDS):
            found_texts[text] += 1

print("Matching observation names found:")
for text, count in found_texts.most_common(30):
    print(f"  {count:4d}  {text}")