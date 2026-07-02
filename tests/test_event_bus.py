"""Tests for event bus module."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from myagentwatch.event_bus import EventBus


def test_event_bus_publish_subscribe():
    bus = EventBus()
    received = []

    def reader():
        q = bus.subscribe("test")
        try:
            item = q.get(timeout=2)
            received.append(item)
        except Exception:
            pass

    import threading

    t = threading.Thread(target=reader)
    t.start()
    time.sleep(0.1)
    bus.publish("test", {"msg": "hello"})
    t.join(timeout=3)

    assert len(received) == 1
    assert received[0]["data"]["msg"] == "hello"


def test_event_bus_unsubscribe():
    bus = EventBus()
    q = bus.subscribe("test2")
    bus.unsubscribe("test2", q)
    bus.publish("test2", {"msg": "noone"})
    # Should not crash, ring buffer should have the event
    assert len(bus._ring.get("test2", [])) == 1


def test_event_bus_ring_buffer_limited():
    bus = EventBus()
    for i in range(600):
        bus.publish("test3", {"n": i})
    assert len(bus._ring["test3"]) <= 500
