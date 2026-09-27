"""Guardrails for the Cortex assistant.

- safe_text: strings that came from uploads (ingredient, dish and event names)
  go into the model's context. They are cut short and stripped of control
  characters and code fences, so a crafted name cannot smuggle a long hidden
  instruction or break out of the JSON the model reads.
- RateLimiter: a per-user sliding window, so one account cannot run up the
  Snowflake bill or hammer the API.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque

MAX_NAME_CHARS = 80
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def safe_text(value, limit: int = MAX_NAME_CHARS):
    """A short, single-line, printable version of an uploaded string (None stays None)."""
    if value is None:
        return None
    text = _CONTROL.sub(" ", str(value)).replace("\n", " ").replace("```", "'''")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


class RateLimiter:
    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self.clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def retry_after(self, key: str) -> int:
        hits = self._hits.get(key)
        if not hits:
            return 0
        return max(1, int(self.window_s - (self.clock() - hits[0])) + 1)
