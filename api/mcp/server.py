import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
mcp = FastMCP("trade-signal")


async def _get(path: str, params: Optional[dict] = None) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_BASE}{path}", params=params or {})
            return response.text
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
async def get_trades(state: str = "closed", limit: int = 50) -> str:
    """Get trades. state='open' or 'closed'. limit max 200."""
    return await _get("/api/trades", {"state": state, "limit": min(limit, 200)})


@mcp.tool()
async def get_trader_profile() -> str:
    """Get trader profile: dominant trading style and Phase 2 candidate rules with progress."""
    return await _get("/api/trader-profile")


@mcp.tool()
async def get_insights() -> str:
    """Get active insights computed by the insight engine."""
    return await _get("/api/insights")


@mcp.tool()
async def get_alerts() -> str:
    """Get currently active unacknowledged alerts."""
    return await _get("/api/alerts")


@mcp.tool()
async def get_account_history(days: int = 7) -> str:
    """Get account equity/balance snapshots for the last N days."""
    return await _get("/api/account-snapshots", {"days": days})


@mcp.tool()
async def get_trade_stats() -> str:
    """Get aggregated trade statistics: win rate, average profit, daily P/L."""
    return await _get("/api/daily-pl", {"days": 30})


@mcp.tool()
async def get_price_context(symbol: str = "XAUUSD", tf: str = "M15", limit: int = 50) -> str:
    """Get recent price bars for a symbol and timeframe."""
    return await _get("/api/price-bars", {"symbol": symbol, "tf": tf, "limit": limit})


if __name__ == "__main__":
    mcp.run()
