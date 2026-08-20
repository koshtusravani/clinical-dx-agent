"""
I use this module to log every tool call and LLM call in a structured way.
Every run produces one JSON trace file under logs/runs/{run_id}.json. This
is the artifact my eval harness reads later, and it's also what I can
display step by step in my demo UI.
"""

import json
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs" / "runs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PRICING = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}


def new_run_id() -> str:
    return str(uuid.uuid4())


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]


def _default(obj):
    if is_dataclass(obj):
        return asdict(obj)
    raise TypeError(f"I don't know how to serialize an object of type {type(obj)}")


def write_run_trace(run_id: str, trace: dict) -> Path:
    path = LOGS_DIR / f"{run_id}.json"
    with open(path, "w") as f:
        json.dump(trace, f, indent=2, default=_default)
    return path


class Timer:
    """I use this as a context manager to measure latency in milliseconds."""

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000