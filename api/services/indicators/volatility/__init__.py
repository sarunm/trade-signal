from importlib import import_module

from services.indicators.common import VOLATILITY_SPECS

for slug in VOLATILITY_SPECS:
    import_module(f"{__name__}.{slug}")

__all__ = sorted(VOLATILITY_SPECS)
