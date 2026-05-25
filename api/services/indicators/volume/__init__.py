from importlib import import_module

from services.indicators.common import VOLUME_SPECS

for slug in VOLUME_SPECS:
    import_module(f"{__name__}.{slug}")

__all__ = sorted(VOLUME_SPECS)
