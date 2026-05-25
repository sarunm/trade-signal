from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_adr = register_indicator(VOLATILITY_SPECS["adr"])
