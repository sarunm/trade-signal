from services.symbol_normalizer import normalize_symbol, CANONICAL_SYMBOL


def test_canonical_symbol_passes_through():
    assert normalize_symbol("GOLD#") == "GOLD#"


def test_gold_no_hash_normalizes():
    assert normalize_symbol("GOLD") == CANONICAL_SYMBOL


def test_xauusd_normalizes():
    assert normalize_symbol("XAUUSD") == CANONICAL_SYMBOL


def test_lowercase_normalizes():
    assert normalize_symbol("xauusd") == CANONICAL_SYMBOL


def test_unrelated_symbol_unchanged():
    assert normalize_symbol("EURUSD") == "EURUSD"


def test_none_passthrough():
    assert normalize_symbol(None) is None
