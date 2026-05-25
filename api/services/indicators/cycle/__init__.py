from importlib import import_module

from services.indicators.common import CYCLE_SPECS

for slug in CYCLE_SPECS:
    import_module(f"{__name__}.{slug}")

__all__ = sorted(CYCLE_SPECS)
