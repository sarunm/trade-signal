import pytest

LEVEL_RATIOS = {"0.236", "0.382", "0.500", "0.618", "0.786"}
EXT_RATIOS   = {"0.236", "0.382", "0.500", "0.618", "0.786"}

# swing_high = 4870.56, swing_low = 4608.56
_HIGH  = 4870.56
_LOW   = 4608.56
_RANGE = _HIGH - _LOW

def _r(ratio): return round(_LOW + _RANGE * ratio, 5)
def _s(ratio): return round(_LOW - _RANGE * ratio, 5)

FIB_PAYLOAD = {
    "symbol": "GOLD",
    "timeframe": "D1",
    "swing_high": "4870.56000",
    "swing_low": "4608.56000",
    "direction": "bullish",
    "levels": {
        "0.236": _r(0.236),
        "0.382": _r(0.382),
        "0.500": _r(0.5),
        "0.618": _r(0.618),
        "0.786": _r(0.786),
    },
    "extensions": {
        "0.236": _s(0.236),
        "0.382": _s(0.382),
        "0.500": _s(0.5),
        "0.618": _s(0.618),
        "0.786": _s(0.786),
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
        "levels": {**FIB_PAYLOAD["levels"], "0.500": 4777.77},
        "computed_at": "2026-05-18T10:00:00Z",
    }

    response = await client.post("/api/fib-levels", json=updated)
    list_response = await client.get("/api/fib-levels")

    assert response.status_code == 201
    rows = list_response.json()
    assert len(rows) == 1
    assert rows[0]["swing_high"] == "4900.00000"
    assert rows[0]["direction"] == "bearish"
    assert rows[0]["levels"]["0.500"] == 4777.77


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
        "levels": {k: v for k, v in FIB_PAYLOAD["levels"].items() if k != "0.786"},
    }

    response = await client.post("/api/fib-levels", json=payload)

    assert response.status_code == 422
