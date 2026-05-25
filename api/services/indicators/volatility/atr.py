from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_atr = register_indicator(VOLATILITY_SPECS["atr"])
