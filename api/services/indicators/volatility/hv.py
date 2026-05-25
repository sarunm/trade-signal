from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_hv = register_indicator(VOLATILITY_SPECS["hv"])
