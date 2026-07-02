"""MyAgentWatch SSE Event Bus.

Thread-safe publish/subscribe with ring-buffer replay and concurrency caps.
Pattern: clawmetry-style SSE streaming with slot-based concurrency limiting.
"""

import contextlib
import json
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Generator

logger = logging.getLogger("myagentwatch.event_bus")

MAX_SUBSCRIBERS_PER_TYPE = 15
RING_BUFFER_SIZE = 500
HEARTBEAT_INTERVAL = 15  # seconds


class EventBus:
    """Publish/subscribe hub with SSE streaming support."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[queue.Queue]] = {}
        # Ring buffer per event type for replay on connect
        self._ring: dict[str, deque] = {}
        self._slots: dict[str, int] = {}

    def publish(self, event_type: str, data: dict):
        """Push an event to all subscribers of the given type."""
        payload = {
            "type": event_type,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        payload_str = json.dumps(payload, ensure_ascii=False)

        with self._lock:
            # Ring buffer
            if event_type not in self._ring:
                self._ring[event_type] = deque(maxlen=RING_BUFFER_SIZE)
            self._ring[event_type].append(payload_str)

            # Push to subscribers
            if event_type in self._subscribers:
                dead_queues = []
                for q in self._subscribers[event_type]:
                    try:
                        q.put_nowait(payload)
                    except queue.Full:
                        with contextlib.suppress(queue.Empty):
                            q.get_nowait()
                        try:
                            q.put_nowait(payload)
                        except queue.Full:
                            dead_queues.append(q)
                for q in dead_queues:
                    self._subscribers[event_type].remove(q)

    def subscribe(self, event_type: str) -> queue.Queue:
        """Register a subscriber queue for the given event type. Returns the queue."""
        q = queue.Queue(maxsize=200)
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(q)
            if event_type not in self._slots:
                self._slots[event_type] = 0
        return q

    def unsubscribe(self, event_type: str, q: queue.Queue):
        """Remove a subscriber queue. Clean up stale ring buffers."""
        with self._lock:
            if event_type in self._subscribers and q in self._subscribers[event_type]:
                self._subscribers[event_type].remove(q)
                if not self._subscribers[event_type]:
                    self._subscribers.pop(event_type, None)
                    self._ring.pop(event_type, None)
                    self._slots.pop(event_type, None)

    def sse_stream(
        self, event_type: str, include_replay: bool = True
    ) -> Generator[str, None, None]:
        """Generate SSE stream for the given event type.

        Yields SSE formatted strings. Call from a Flask route with:
            return Response(event_bus.sse_stream('activity'), mimetype='text/event-stream')
        """
        with self._lock:
            current_slots = self._slots.get(event_type, 0)
            if current_slots >= MAX_SUBSCRIBERS_PER_TYPE:
                yield f"event: error\ndata: {json.dumps({'error': 'Too many subscribers', 'retry_after': 30})}\n\n"
                return
            self._slots[event_type] = current_slots + 1

        q = self.subscribe(event_type)
        last_heartbeat = time.time()

        try:
            # Replay recent events on connect
            if include_replay:
                with self._lock:
                    ring_buffer = list(self._ring.get(event_type, []))
                for item in ring_buffer[-50:]:
                    yield f"event: {event_type}\ndata: {item}\n\n"

            while True:
                try:
                    event = q.get(timeout=HEARTBEAT_INTERVAL)
                    yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    last_heartbeat = time.time()
                except queue.Empty:
                    now = time.time()
                    if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                        yield f": heartbeat {now}\n\n"
                        last_heartbeat = now
        except GeneratorExit:
            pass
        finally:
            self.unsubscribe(event_type, q)
            with self._lock:
                self._slots[event_type] = max(0, self._slots.get(event_type, 1) - 1)


# Global singleton
event_bus = EventBus()
