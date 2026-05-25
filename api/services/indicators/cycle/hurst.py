from services.indicators.common import CYCLE_SPECS, register_indicator

compute_hurst = register_indicator(CYCLE_SPECS["hurst"])
