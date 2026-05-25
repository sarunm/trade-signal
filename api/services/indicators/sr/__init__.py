from importlib import import_module

from services.indicators.common import SR_SPECS

for slug in SR_SPECS:
    import_module(f"{__name__}.{slug}")

__all__ = sorted(SR_SPECS)
