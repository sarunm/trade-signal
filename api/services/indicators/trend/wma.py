from services.indicators.common import TREND_SPECS, register_indicator

compute_wma = register_indicator(TREND_SPECS["wma"])
