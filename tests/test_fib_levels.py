import pytest

RESISTANCE_KEYS = {f"R{i}" for i in range(1, 11)}
SUPPORT_KEYS = {f"S{i}" for i in range(1, 11)}

_RATIOS = [0.235, 0.382, 0.500, 0.618, 0.728, 1.000, 1.235, 1.328, 1.500, 1.618]
_PREV_HIGH = 4870.56
_PREV_LOW = 4608.56
_PREV_CLOSE = 4700.00
_PP = round((_PREV_HIGH + _PREV_LOW + _PREV_CLOSE) / 3, 5)
_RANGE = _PREV_HIGH - _PREV_LOW


def _r(ratio):
    return round(_PP + _RANGE * ratio, 5)


def _s(ratio):
    return round(_PP - _RANGE * ratio, 5)


FIB_PAYLOAD = {
    "symbol": "GOLD",
    "period": "W",
    "prev_high": "4870.56000",
    "prev_low": "4608.56000",
    "prev_close": "4700.00000",
    "pp": str(_PP),
    "resistance": {f"R{i+1}": _r(_RATIOS[i]) for i in range(10)},
    "support": {f"S{i+1}": _s(_RATIOS[i]) for i in range(10)},
    "computed_at": "2026-05-18T09:00:00Z",
}


@pytest.mark.asyncio
async def test_post_fib_levels_creates_new_row(client):
    response = await client.post("/api/fib-levels", json=FIB_PAYLOAD)

    assert response.status_code == 201
    data = response.json()
    assert data["symbol"] == "GOLD"
    assert data["period"] == "W"
    assert data["prev_high"] == "4870.56000"
    assert data["prev_low"] == "4608.56000"
    assert data["prev_close"] == "4700.00000"
    assert float(data["pp"]) == pytest.approx(_PP)


@pytest.mark.asyncio
async def test_post_fib_levels_upserts_same_symbol_and_period(client):
    await client.post("/api/fib-levels", json=FIB_PAYLOAD)
    updated = {
        **FIB_PAYLOAD,
        "prev_high": "4900.00000",
        "resistance": {**FIB_PAYLOAD["resistance"], "R1": 4777.77},
        "computed_at": "2026-05-18T10:00:00Z",
    }

    response = await client.post("/api/fib-levels", json=updated)
    list_response = await client.get("/api/fib-levels")

    assert response.status_code == 201
    rows = list_response.json()
    assert len(rows) == 1
    assert rows[0]["prev_high"] == "4900.00000"
    assert rows[0]["resistance"]["R1"] == 4777.77


@pytest.mark.asyncio
async def test_get_fib_levels_returns_stored_row_with_levels(client):
    await client.post("/api/fib-levels", json=FIB_PAYLOAD)

    response = await client.get("/api/fib-levels")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "GOLD"
    assert data[0]["resistance"] == FIB_PAYLOAD["resistance"]
    assert data[0]["support"] == FIB_PAYLOAD["support"]


@pytest.mark.asyncio
async def test_fib_levels_have_correct_ratio_keys(client):
    response = await client.post("/api/fib-levels", json=FIB_PAYLOAD)

    assert response.status_code == 201
    data = response.json()
    assert set(data["resistance"].keys()) == RESISTANCE_KEYS
    assert set(data["support"].keys()) == SUPPORT_KEYS


@pytest.mark.asyncio
async def test_post_fib_levels_rejects_missing_ratio(client):
    payload = {
        **FIB_PAYLOAD,
        "resistance": {k: v for k, v in FIB_PAYLOAD["resistance"].items() if k != "R10"},
    }

    response = await client.post("/api/fib-levels", json=payload)

    assert response.status_code == 422
