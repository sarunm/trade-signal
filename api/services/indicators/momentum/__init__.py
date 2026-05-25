from importlib import import_module

from services.indicators.common import MOMENTUM_SPECS

for slug in MOMENTUM_SPECS:
    import_module(f"{__name__}.{slug}")

__all__ = sorted(MOMENTUM_SPECS)
