from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_stdev = register_indicator(VOLATILITY_SPECS["stdev"])
