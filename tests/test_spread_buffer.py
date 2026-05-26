# tests/test_spread_buffer.py
from decimal import Decimal

from services.spread_buffer import SpreadBuffer


def test_buffer_capped_at_max_size():
    buf = SpreadBuffer(max_size=3)
    for v in [Decimal("0.10"), Decimal("0.20"), Decimal("0.30"), Decimal("0.40")]:
        buf.push(v)
    assert buf.size() == 3
    assert buf.values() == [Decimal("0.20"), Decimal("0.30"), Decimal("0.40")]


def test_p50_returns_median():
    buf = SpreadBuffer(max_size=10)
    for v in [Decimal("1"), Decimal("3"), Decimal("5"), Decimal("7"), Decimal("9")]:
        buf.push(v)
    assert buf.p50() == Decimal("5")


def test_p50_returns_none_when_empty():
    buf = SpreadBuffer(max_size=10)
    assert buf.p50() is None


def test_clear():
    buf = SpreadBuffer(max_size=10)
    buf.push(Decimal("1"))
    buf.clear()
    assert buf.size() == 0
