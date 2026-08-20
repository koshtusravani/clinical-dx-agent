"""
Every tool call my agent makes goes through this wrapper. This is the one
place where I handle retries, backoff, and failure classification. Keeping
this logic out of individual tool functions is what makes my failure
taxonomy consistent and easy to evaluate against.
"""

import time
from typing import Callable

from src.failure_taxonomy import MaxRetriesExceeded, PermanentError, TransientError


def backoff(attempt: int, base: float = 0.5) -> float:
    return base * (2 ** attempt)


def call_tool_with_retry(
    tool_fn: Callable,
    args: dict,
    max_retries: int = 2,
    on_log: Callable[[dict], None] | None = None,
) -> dict:
    """
    I call tool_fn(**args) here with retry on transient error semantics.

    If I'm given on_log, I call it with a structured record for every
    attempt, whether it succeeds, retries, or fails. I wire this to a
    StepRecord builder in my agent loop.
    """
    last_error = None

    for attempt in range(max_retries + 1):
        start = time.perf_counter()
        try:
            result = tool_fn(**args)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if on_log:
                on_log({
                    "tool": tool_fn.__name__,
                    "args": args,
                    "result": result,
                    "latency_ms": elapsed_ms,
                    "attempt": attempt,
                    "status": "success",
                })
            return result

        except TransientError as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            last_error = e
            if on_log:
                on_log({
                    "tool": tool_fn.__name__,
                    "args": args,
                    "result": None,
                    "latency_ms": elapsed_ms,
                    "attempt": attempt,
                    "status": "retry",
                    "error": str(e),
                })
            if attempt < max_retries:
                time.sleep(backoff(attempt))
            continue

        except PermanentError as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if on_log:
                on_log({
                    "tool": tool_fn.__name__,
                    "args": args,
                    "result": None,
                    "latency_ms": elapsed_ms,
                    "attempt": attempt,
                    "status": "failed_permanent",
                    "error": str(e),
                })
            raise

    if on_log:
        on_log({
            "tool": tool_fn.__name__,
            "args": args,
            "result": None,
            "latency_ms": 0,
            "attempt": max_retries,
            "status": "failed_exhausted_retries",
            "error": str(last_error) if last_error else "unknown",
        })
    raise MaxRetriesExceeded(tool_fn.__name__)