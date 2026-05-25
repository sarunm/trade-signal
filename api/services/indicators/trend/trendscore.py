from services.indicators.common import TREND_SPECS, register_indicator

compute_trendscore = register_indicator(TREND_SPECS["trendscore"])
