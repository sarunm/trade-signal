from services.indicators.common import TREND_SPECS, register_indicator

compute_sma = register_indicator(TREND_SPECS["sma"])
