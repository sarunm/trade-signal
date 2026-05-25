from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_donchian = register_indicator(VOLATILITY_SPECS["donchian"])
