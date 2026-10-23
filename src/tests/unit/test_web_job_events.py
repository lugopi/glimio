from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

import web.app as web_app
from web.app import (
    JOB_EVENT_LOCK,
    JOB_EVENT_PENDING,
    JOB_EVENT_STOP,
    JOB_EVENT_WAKE,
    _close_job_event_streams,
    _coalesce_job_event_locked,
    _flush_job_events,
)


class _ImmediateLoop:
    """Minimal event loop double that runs callbacks inline, like a live loop."""

    def call_soon_threadsafe(self, callback) -> None:
        callback()


class JobEventCoalescingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._reset_events()
        self.ensure_patcher = patch("web.app._ensure_job_event_flusher")
        self.ensure_flusher = self.ensure_patcher.start()
        self.addCleanup(self.ensure_patcher.stop)
        self.addCleanup(self._reset_events)

    def _reset_events(self) -> None:
        with JOB_EVENT_LOCK:
            JOB_EVENT_PENDING.clear()
            web_app.JOB_EVENT_SUBSCRIBERS.clear()
        JOB_EVENT_STOP.clear()
        JOB_EVENT_WAKE.clear()
        web_app.JOB_EVENT_FLUSHER = None

    def _subscribe(self, subscriber_id: str = "subscriber") -> asyncio.Queue[tuple[str, str]]:
        subscriber_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=16)
        with JOB_EVENT_LOCK:
            web_app.JOB_EVENT_SUBSCRIBERS[subscriber_id] = (_ImmediateLoop(), subscriber_queue)
        return subscriber_queue

    def test_coalesces_repeated_updates_for_the_same_key(self) -> None:
        self._subscribe()
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("job", {"id": "job-1", "state": "queued"}, "job:job-1")
            _coalesce_job_event_locked("job", {"id": "job-1", "state": "running"}, "job:job-1")
            _coalesce_job_event_locked("job", {"id": "job-1", "state": "completed"}, "job:job-1")

        self.assertEqual(list(JOB_EVENT_PENDING), ["job:job-1"])
        event_name, data = JOB_EVENT_PENDING["job:job-1"]
        self.assertEqual(event_name, "job")
        self.assertEqual(data, '{"id":"job-1","state":"completed"}')
        self.assertEqual(self.ensure_flusher.call_count, 3)
        self.assertTrue(JOB_EVENT_WAKE.is_set())

    def test_updated_key_moves_to_the_end_of_the_flush_order(self) -> None:
        self._subscribe()
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("job", {"id": "job-1"}, "job:job-1")
            _coalesce_job_event_locked("job", {"id": "job-2"}, "job:job-2")
            _coalesce_job_event_locked("job", {"id": "job-1", "state": "done"}, "job:job-1")

        self.assertEqual(list(JOB_EVENT_PENDING), ["job:job-2", "job:job-1"])

    def test_flush_empties_pending_and_sends_each_entry_once_in_order(self) -> None:
        self._subscribe()
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("job", {"id": "job-1"}, "job:job-1")
            _coalesce_job_event_locked("artifact", {"session_id": "s-1"}, "artifact:s-1:summary")

        with patch("web.app._send_job_event_locked") as send:
            _flush_job_events()

        self.assertEqual(JOB_EVENT_PENDING, {})
        self.assertEqual(send.call_count, 2)
        self.assertEqual(
            send.call_args_list,
            [
                call("job", '{"id":"job-1"}'),
                call("artifact", '{"session_id":"s-1"}'),
            ],
        )

    def test_no_subscriber_keeps_pending_empty_and_skips_flusher(self) -> None:
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("job", {"id": "job-1"}, "job:job-1")

        self.assertEqual(JOB_EVENT_PENDING, {})
        self.ensure_flusher.assert_not_called()
        self.assertFalse(JOB_EVENT_WAKE.is_set())

    def test_full_queue_drops_the_oldest_event_and_keeps_the_latest(self) -> None:
        subscriber_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=1)
        subscriber_queue.put_nowait(("job", "old"))
        with JOB_EVENT_LOCK:
            web_app.JOB_EVENT_SUBSCRIBERS["subscriber"] = (_ImmediateLoop(), subscriber_queue)

        with JOB_EVENT_LOCK:
            web_app._send_job_event_locked("job", "new")

        self.assertEqual(subscriber_queue.get_nowait(), ("job", "new"))
        self.assertTrue(subscriber_queue.empty())

    def test_close_streams_flushes_pending_before_shutdown_marker(self) -> None:
        subscriber_queue = self._subscribe()
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("job", {"id": "job-1"}, "job:job-1")

        with patch("web.app._send_job_event_locked") as send:
            _close_job_event_streams()

        send.assert_called_once_with("job", '{"id":"job-1"}')
        self.assertEqual(JOB_EVENT_PENDING, {})
        self.assertTrue(JOB_EVENT_STOP.is_set())
        self.assertTrue(JOB_EVENT_WAKE.is_set())
        self.assertEqual(subscriber_queue.get_nowait(), (web_app.JOB_EVENT_SHUTDOWN, ""))

        # Once shutdown began, a late producer must not enqueue an event that
        # would be lost anyway.
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("job", {"id": "job-2"}, "job:job-2")
        self.assertEqual(JOB_EVENT_PENDING, {})

    def test_sse_registration_flushes_pending_before_registering_and_snapshot(self) -> None:
        existing_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=8)
        with JOB_EVENT_LOCK:
            web_app.JOB_EVENT_SUBSCRIBERS["existing"] = (_ImmediateLoop(), existing_queue)
            JOB_EVENT_PENDING["job:job-1"] = ("job", '{"id":"job-1"}')

        async def open_stream():
            response = await web_app.job_events(SimpleNamespace())
            iterator = response.body_iterator
            retry = await iterator.__anext__()
            snapshot = await iterator.__anext__()
            await iterator.aclose()
            return retry, snapshot

        with patch("web.app._initialize_persistence"):
            retry, snapshot = asyncio.run(open_stream())

        self.assertEqual(JOB_EVENT_PENDING, {})
        self.assertEqual(existing_queue.get_nowait(), ("job", '{"id":"job-1"}'))
        self.assertTrue(retry.startswith("retry:"))
        self.assertTrue(snapshot.startswith("event: snapshot\ndata: "))
        self.assertIn('"items"', snapshot)
        self.assertEqual(len(web_app.JOB_EVENT_SUBSCRIBERS), 1)


if __name__ == "__main__":
    unittest.main()
