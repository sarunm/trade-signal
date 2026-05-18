import pytest

LEVEL_RATIOS = {"0.000", "0.235", "0.382", "0.5", "0.618", "0.728", "1.000", "1.235", "1.328", "1.500", "1.618"}
EXT_RATIOS   = {"0.235", "0.382", "0.5", "0.618", "0.728", "1.000", "1.235", "1.328", "1.500", "1.618"}

# PP = (4870.56 + 4608.56 + 4750.00) / 3 = 4743.04, range = 262.00
_PP    = 4743.04
_RANGE = 262.00

def _r(ratio): return round(_PP + _RANGE * ratio, 5)
def _s(ratio): return round(_PP - _RANGE * ratio, 5)

FIB_PAYLOAD = {
    "symbol": "GOLD",
    "timeframe": "D1",
    "swing_high": "4870.56000",
    "swing_low": "4608.56000",
    "direction": "bullish",
    "levels": {
        "0.000": _PP,
        "0.235": _r(0.235),
        "0.382": _r(0.382),
        "0.5":   _r(0.5),
        "0.618": _r(0.618),
        "0.728": _r(0.728),
        "1.000": _r(1.0),
        "1.235": _r(1.235),
        "1.328": _r(1.328),
        "1.500": _r(1.5),
        "1.618": _r(1.618),
    },
    "extensions": {
        "0.235": _s(0.235),
        "0.382": _s(0.382),
        "0.5":   _s(0.5),
        "0.618": _s(0.618),
        "0.728": _s(0.728),
        "1.000": _s(1.0),
        "1.235": _s(1.235),
        "1.328": _s(1.328),
        "1.500": _s(1.5),
        "1.618": _s(1.618),
    },
    "computed_at": "2026-05-18T09:00:00Z",
}


@pytest.mark.asyncio
async def test_post_fib_levels_creates_new_row(client):
    response = await client.post("/api/fib-levels", json=FIB_PAYLOAD)

    assert response.status_code == 201
    data = response.json()
    assert data["symbol"] == "GOLD"
    assert data["timeframe"] == "D1"
    assert data["direction"] == "bullish"
    assert data["swing_high"] == "4870.56000"
    assert data["swing_low"] == "4608.56000"


@pytest.mark.asyncio
async def test_post_fib_levels_upserts_same_symbol_and_timeframe(client):
    await client.post("/api/fib-levels", json=FIB_PAYLOAD)
    updated = {
        **FIB_PAYLOAD,
        "swing_high": "4900.00000",
        "direction": "bearish",
        "levels": {**FIB_PAYLOAD["levels"], "0.5": 4777.77},
        "computed_at": "2026-05-18T10:00:00Z",
    }

    response = await client.post("/api/fib-levels", json=updated)
    list_response = await client.get("/api/fib-levels")

    assert response.status_code == 201
    rows = list_response.json()
    assert len(rows) == 1
    assert rows[0]["swing_high"] == "4900.00000"
    assert rows[0]["direction"] == "bearish"
    assert rows[0]["levels"]["0.5"] == 4777.77


@pytest.mark.asyncio
async def test_get_fib_levels_returns_stored_row_with_levels(client):
    await client.post("/api/fib-levels", json=FIB_PAYLOAD)

    response = await client.get("/api/fib-levels")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "GOLD"
    assert data[0]["levels"] == FIB_PAYLOAD["levels"]
    assert data[0]["extensions"] == FIB_PAYLOAD["extensions"]


@pytest.mark.asyncio
async def test_fib_levels_have_correct_ratio_keys(client):
    response = await client.post("/api/fib-levels", json=FIB_PAYLOAD)

    assert response.status_code == 201
    data = response.json()
    assert set(data["levels"].keys()) == LEVEL_RATIOS
    assert set(data["extensions"].keys()) == EXT_RATIOS


@pytest.mark.asyncio
async def test_post_fib_levels_rejects_missing_ratio(client):
    payload = {
        **FIB_PAYLOAD,
        "levels": {k: v for k, v in FIB_PAYLOAD["levels"].items() if k != "0.728"},
    }

    response = await client.post("/api/fib-levels", json=payload)

    assert response.status_code == 422
