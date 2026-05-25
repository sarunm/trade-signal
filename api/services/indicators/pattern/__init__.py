from importlib import import_module

from services.indicators.common import PATTERN_SPECS

for slug in PATTERN_SPECS:
    import_module(f"{__name__}.{slug}")

__all__ = sorted(PATTERN_SPECS)
