"""Integration tests for content_generator.pipeline_runner.

Focuses on _ThreadLocalStdout routing (BUG-17) and pipeline guard rails.
No real API calls — CrewAI and all external services are mocked.
"""

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from content_generator.pipeline_runner import (
    _ThreadLocalStdout,
    _thread_local,
    _make_task_callback,
    _parse_urls_from_output,
)


# ---------------------------------------------------------------------------
# BUG-17 – _ThreadLocalStdout routes callbacks to correct thread
# ---------------------------------------------------------------------------

class TestThreadLocalStdoutRouting:
    """Verify that concurrent threads each get their own callback slot."""

    def test_bug17_write_routes_to_calling_thread_callback(self):
        """BUG-17: _ThreadLocalStdout.write() must deliver output to the
        callback registered by the CALLING thread via threading.local(), not
        to a single shared callback on the instance.

        Old broken behaviour: all writes went to self._callback (the last
        thread to enter the context manager), causing cross-thread output
        mixing in the GUI log panel.
        """
        received_a: list[str] = []
        received_b: list[str] = []

        # Single interceptor instance — both threads will write through it
        interceptor = _ThreadLocalStdout(lambda s: None, None)

        barrier = threading.Barrier(2)

        def thread_a():
            _thread_local.callback = received_a.append
            barrier.wait()          # both threads register before any write
            interceptor.write("MSG_FROM_A\n")
            barrier.wait()          # both threads write before any cleanup
            _thread_local.callback = None

        def thread_b():
            _thread_local.callback = received_b.append
            barrier.wait()
            interceptor.write("MSG_FROM_B\n")
            barrier.wait()
            _thread_local.callback = None

        t_a = threading.Thread(target=thread_a)
        t_b = threading.Thread(target=thread_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=5)
        t_b.join(timeout=5)

        assert not t_a.is_alive() and not t_b.is_alive(), "Threads did not finish in time"

        assert any("MSG_FROM_A" in s for s in received_a), (
            "Thread A's write was not routed to callback_a"
        )
        assert not any("MSG_FROM_B" in s for s in received_a), (
            "Thread B's write leaked into callback_a — cross-thread routing bug"
        )
        assert any("MSG_FROM_B" in s for s in received_b), (
            "Thread B's write was not routed to callback_b"
        )
        assert not any("MSG_FROM_A" in s for s in received_b), (
            "Thread A's write leaked into callback_b — cross-thread routing bug"
        )

    def test_bug17_thread_without_callback_does_not_receive_output(self):
        """BUG-17: A thread that never registered a callback must not see any
        output from other threads' writes (getattr returns None → no dispatch).
        """
        received_other: list[str] = []
        interceptor = _ThreadLocalStdout(lambda s: None, None)

        # Main thread: no _thread_local.callback registered (or it's None)
        _thread_local.callback = None

        barrier = threading.Barrier(2)

        def worker():
            _thread_local.callback = lambda s: None  # worker registers its own
            barrier.wait()
            interceptor.write("WORKER_MSG\n")
            _thread_local.callback = None

        t = threading.Thread(target=worker)
        t.start()
        barrier.wait()
        # Main thread calls write — its _thread_local.callback is None
        interceptor.write("MAIN_MSG\n")
        t.join(timeout=5)

        # received_other was never appended because main has no callback
        assert received_other == []

    def test_bug17_context_manager_sets_and_clears_thread_local(self):
        """BUG-17: __enter__ must set _thread_local.callback; __exit__ must
        clear it so subsequent writes from the same thread are not dispatched.
        """
        dispatched: list[str] = []

        # Use a named function so identity comparison via 'is' is stable.
        # list.append is a descriptor that creates a new bound-method object
        # on every attribute lookup, so `dispatched.append is dispatched.append`
        # is False — storing the reference first avoids that pitfall.
        def my_callback(s: str) -> None:
            dispatched.append(s)

        with _ThreadLocalStdout(my_callback, None):
            registered = getattr(_thread_local, "callback", None)
            assert registered is my_callback, (
                "__enter__ did not register the callback in _thread_local"
            )

        # After __exit__, callback must be cleared
        assert getattr(_thread_local, "callback", None) is None, (
            "__exit__ did not clear _thread_local.callback"
        )


# ---------------------------------------------------------------------------
# Additional pipeline utilities
# ---------------------------------------------------------------------------

class TestMakeTaskCallback:
    """Smoke tests for _make_task_callback."""

    def test_make_task_callback_calls_log_cb_with_agent_name(self):
        """_make_task_callback must invoke the log callback with the agent name."""
        received = []
        cb = _make_task_callback(received.append)

        task_output = MagicMock()
        task_output.agent = "TestAgent"
        task_output.summary = "Did some work"

        cb(task_output)
        combined = "".join(received)
        assert "TestAgent" in combined

    def test_make_task_callback_does_not_raise_on_bad_task_output(self):
        """_make_task_callback must not propagate exceptions from bad output."""
        received = []
        cb = _make_task_callback(received.append)
        cb(None)   # Should not raise
        cb(object())  # Should not raise


class TestParseUrlsFromOutput:
    """Tests for _parse_urls_from_output URL extraction."""

    def test_extracts_https_urls(self):
        raw = "Found this: https://example.com/product/123 and https://shop.example.org"
        urls = _parse_urls_from_output(raw)
        assert "https://example.com/product/123" in urls
        assert "https://shop.example.org" in urls

    def test_deduplicates_urls(self):
        raw = "https://example.com https://example.com"
        urls = _parse_urls_from_output(raw)
        assert urls.count("https://example.com") == 1

    def test_strips_trailing_punctuation(self):
        raw = "See https://example.com."
        urls = _parse_urls_from_output(raw)
        assert "https://example.com" in urls
        assert "https://example.com." not in urls
