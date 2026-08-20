"""
I wrote these tests to verify my retry wrapper handles all four outcomes I
care about: success on the first try, recovering after a transient error,
failing immediately on a permanent error, and giving up after exhausting
retries.
"""

import pytest

from src.failure_taxonomy import MaxRetriesExceeded, PermanentError, TransientError
from src.tools.base import call_tool_with_retry


def test_success_on_first_try():
    def fake_tool(x):
        return {"value": x * 2}

    logs = []
    result = call_tool_with_retry(fake_tool, {"x": 5}, on_log=logs.append)

    assert result == {"value": 10}
    assert logs[0]["status"] == "success"


def test_retries_then_succeeds():
    calls = {"count": 0}

    def flaky_tool():
        calls["count"] += 1
        if calls["count"] < 2:
            raise TransientError("temporary timeout")
        return {"ok": True}

    logs = []
    result = call_tool_with_retry(flaky_tool, {}, max_retries=2, on_log=logs.append)

    assert result == {"ok": True}
    assert logs[0]["status"] == "retry"
    assert logs[-1]["status"] == "success"


def test_permanent_error_does_not_retry():
    calls = {"count": 0}

    def broken_tool():
        calls["count"] += 1
        raise PermanentError("invalid test name")

    logs = []
    with pytest.raises(PermanentError):
        call_tool_with_retry(broken_tool, {}, max_retries=2, on_log=logs.append)

    assert calls["count"] == 1
    assert logs[-1]["status"] == "failed_permanent"


def test_exhausts_retries_and_raises():
    def always_flaky():
        raise TransientError("still down")

    logs = []
    with pytest.raises(MaxRetriesExceeded):
        call_tool_with_retry(always_flaky, {}, max_retries=2, on_log=logs.append)

    assert logs[-1]["status"] == "failed_exhausted_retries"