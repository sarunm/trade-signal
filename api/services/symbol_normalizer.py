CANONICAL_SYMBOL = "GOLD#"

_GOLD_ALIASES = {"GOLD#", "GOLD", "XAUUSD", "XAUUSD#", "XAUUSD.", "GOLD."}


def normalize_symbol(symbol: str) -> str:
    if symbol is None:
        return symbol
    upper = symbol.upper()
    if upper in _GOLD_ALIASES:
        return CANONICAL_SYMBOL
    return symbol
