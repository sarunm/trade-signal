from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_bbands = register_indicator(VOLATILITY_SPECS["bbands"])
