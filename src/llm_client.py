"""
I use this as a thin wrapper around the Anthropic API.

I route reasoning heavy steps like differential diagnosis and treatment
proposals to Sonnet, and cheap structured sub tasks like classifying a lab
value to Haiku. This is a deliberate cost and quality tradeoff I'm making on
purpose, and I document it in my README so the eval harness's cost
breakdown can prove it was worth doing.
"""

import os
import time

from anthropic import Anthropic
from dotenv import load_dotenv

from src.logging_utils import compute_cost

load_dotenv()

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL_REASONING = "claude-sonnet-4-6"
MODEL_LIGHT = "claude-haiku-4-5-20251001"


def call_llm(
    messages: list[dict],
    model: str = MODEL_REASONING,
    tools: list[dict] | None = None,
    system: str | None = None,
    max_tokens: int = 1024,
):
    """
    I call the Anthropic API here and return both the response and a
    metadata dict containing latency_ms and cost_usd, so the caller can log
    both without recomputing anything. I accept an optional system prompt
    since my agent loops need to set persona and behavior instructions
    separately from the conversation messages.
    """
    start = time.perf_counter()

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "tools": tools or [],
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)

    elapsed_ms = (time.perf_counter() - start) * 1000

    cost = compute_cost(
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    metadata = {
        "latency_ms": elapsed_ms,
        "cost_usd": cost,
        "model": model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    return response, metadata