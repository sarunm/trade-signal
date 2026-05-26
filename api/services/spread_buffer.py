# api/services/spread_buffer.py
from collections import deque
from decimal import Decimal
from typing import Optional


class SpreadBuffer:
    def __init__(self, max_size: int = 2000):
        self._dq: deque[Decimal] = deque(maxlen=max_size)

    def push(self, value: Decimal) -> None:
        if value is None or value < 0:
            return
        self._dq.append(value)

    def p50(self) -> Optional[Decimal]:
        if not self._dq:
            return None
        ordered = sorted(self._dq)
        n = len(ordered)
        mid = n // 2
        if n % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    def size(self) -> int:
        return len(self._dq)

    def values(self) -> list[Decimal]:
        return list(self._dq)

    def clear(self) -> None:
        self._dq.clear()


_buffer = SpreadBuffer()


def push_spread(value: Decimal) -> None:
    _buffer.push(value)


def get_buffer() -> SpreadBuffer:
    return _buffer
