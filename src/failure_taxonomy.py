"""
I define a fixed, closed set of failure categories here. Every non-success
outcome in my agent loop has to fall into exactly one of these categories.
This is what turns error handling into something I can actually analyze in
my eval report, instead of just an afterthought try/except.
"""

from enum import Enum


class FailureCategory(str, Enum):
    TRANSIENT_TOOL_ERROR = "transient_tool_error"      # API timeout or rate limit, I retry these
    DATA_UNAVAILABLE = "data_unavailable"              # no Synthea record for the requested test, my agent has to adapt
    INVALID_TOOL_CALL = "invalid_tool_call"            # malformed or nonexistent test name, I reprompt once
    REASONING_FAILURE = "reasoning_failure"            # wrong diagnosis despite adequate data, I log this but don't retry live
    BUDGET_EXHAUSTED = "budget_exhausted"              # step budget hit without a confident diagnosis, I escalate
    SAFETY_FLAG_SEVERE = "safety_flag_severe"          # severe interaction found, I escalate


class TransientError(Exception):
    """I raise this from a tool for retryable failures like timeouts or rate limits."""


class PermanentError(Exception):
    """I raise this from a tool for failures I know won't fix themselves on retry."""


class MaxRetriesExceeded(Exception):
    def __init__(self, tool_name: str):
        super().__init__(f"I exceeded max retries calling tool: {tool_name}")
        self.tool_name = tool_name